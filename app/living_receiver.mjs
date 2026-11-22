// Host adapter for native AFL1. Structural format labels do not assign meaning.
// No CLB rasterisation, source events, clocks or model calls occur here.
import net from 'node:net';
import { readFileSync } from 'node:fs';
import { MirrorPool } from './vendor/living_buffer/src/mirrors.js';

const MAX_RAW = 512 * 1024, MAX_META = 64 * 1024, MAX_INPUT_META = 1024;
const MAX_ENVELOPE = MAX_RAW + MAX_INPUT_META + 4;
const [major, minor] = process.versions.node.split('.').map(Number);
if (major < 22 || (major === 22 && minor < 13)) throw new Error('Node 22.13 or later required');
const provenance = JSON.parse(readFileSync(new URL('./vendor/living_buffer/provenance.json', import.meta.url), 'utf8'));
const fd = Number(process.argv[process.argv.indexOf('--fd') + 1]);
if (!Number.isInteger(fd) || fd < 3) throw new Error('private socket required');
let owned = null, lastSequence = 0n, currentSequence = 0n;

function inspect(raw, glyphs = true) {
  if (raw.length < 59 || raw.length > MAX_RAW || raw.toString('ascii', 0, 4) !== 'AFL1') throw new Error('invalid AFL1 length/format');
  const sequence = raw.readBigUInt64BE(4), stamp = raw.readDoubleBE(12);
  const cols = raw.readUInt16BE(20), rows = raw.readUInt16BE(22);
  const entropy = raw.readDoubleBE(27), colour = raw.readDoubleBE(35);
  if (sequence <= lastSequence || cols < 20 || cols > 512 || rows < 8 || rows > 128 ||
      raw.length !== 59 + cols * rows * 7 || !Number.isFinite(stamp) || stamp < 0 || stamp > 1e12 ||
      !Number.isFinite(entropy) || entropy < 0 || entropy > 1 ||
      !Number.isFinite(colour) || colour < 0 || colour > 1.5) throw new Error('invalid AFL1 fields');
  for (let at = 59; glyphs && at < raw.length; at += 7) {
    const code = raw.readUInt32BE(at);
    if (code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) throw new Error('invalid AFL1 glyph');
  }
  return { sequence, cols, rows };
}

function unpack(bytes, glyphs = true) {
  const body = Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (body.length < 4) throw new Error('short envelope');
  const length = body.readUInt32BE(0);
  if (length < 2 || length > MAX_INPUT_META || length + 4 >= body.length) throw new Error('invalid envelope metadata');
  const meta = JSON.parse(body.toString('utf8', 4, 4 + length)), raw = body.subarray(4 + length);
  const native = inspect(raw, glyphs);
  if (!Number.isSafeInteger(meta.order) || meta.order < 1 || meta.category !== 'native.field' ||
      meta.pattern !== 'AFL1:grid') throw new Error('invalid structural host label');
  return { meta, raw, native };
}

const pool = new MirrorPool({ elastic: true, poolCount: 1, sharedCategories: true, requireCohesion: true,
  demandWindow: 'learned', blanket: true, burstRetention: true, blockBytes: 8192,
  readyBlocks: 128, minReadyBlocks: 1, maxPayloadBytes: MAX_ENVELOPE, maxLogicalBytes: 1024 * 1024,
  maxMirrors: 2, maxPatterns: 128, maxCategories: 1, maxCoverageRanges: 4 }, bytes => {
  const { raw, native } = unpack(bytes);
  // Borrowed pages end at callback return. Only this owned byte copy escapes.
  owned = Buffer.from(raw); currentSequence = native.sequence;
  return { accepted: true };
});

function statistics() {
  const s = pool.statistics(), category = pool.categoryStatus('native.field');
  return { allocatedBytes: s.allocatedBytes, readyBytes: s.readyBytes, gatherBytes: s.gatherBytes,
    configuredReadyBytes: s.configuredReadyBytes, physicalArrayAllocations: s.physicalArrayAllocations,
    pagesGrown: s.pagesGrown, pagesDropped: s.pagesDropped, gatheredBytes: s.gatheredBytes,
    categoriesRegistered: s.categoriesRegistered, patternsRegistered: s.patternsRegistered,
    retention: s.retention, burstPressure: s.burstPressure, blankets: s.blankets,
    category: 'native.field', patterns: category.accepted ? category.retention : [], recipes_used: false };
}

const socket = new net.Socket({ fd, readable: true, writable: true });
function send(meta, raw = Buffer.alloc(0)) {
  const json = Buffer.from(JSON.stringify(meta));
  if (json.length > MAX_META) throw new Error('oversized diagnostic metadata');
  const head = Buffer.allocUnsafe(8); head.writeUInt32BE(4 + json.length + raw.length, 0); head.writeUInt32BE(json.length, 4);
  socket.cork(); socket.write(head); socket.write(json); if (raw.length) socket.write(raw); socket.uncork();
}
function receive(body) {
  const { meta } = unpack(body, false);
  let handle;
  try {
    const prepared = pool.prepareMirror(body.length, { category: meta.category, pattern: meta.pattern });
    if (!prepared.accepted) throw new Error(prepared.reason); handle = prepared.handle;
    for (const result of [pool.armMirror(handle, 0, body.length), pool.writeMirror(handle, 0, body), pool.sealMirror(handle, body.length)]) {
      if (!result.accepted) throw new Error(result.reason);
    }
    const result = pool.submitMirror(handle);
    if (!result?.accepted || !owned) throw new Error(result?.reason || 'native receiving refused');
    lastSequence = currentSequence;
    send({ ok: true, order: meta.order, library_revision: provenance.runtime_revision, library_accepted_revision: provenance.accepted_revision,
      library: statistics() }, owned); owned = null;
  } finally { if (handle) pool.releaseMirror(handle); }
}

// One length-framed request at a time; the host waits for its owned reply.
let header = Buffer.alloc(4), headerUsed = 0, body = null, bodyUsed = 0;
socket.on('data', chunk => {
  try {
    for (let at = 0; at < chunk.length;) {
      if (!body) {
        const count = Math.min(4 - headerUsed, chunk.length - at); chunk.copy(header, headerUsed, at, at + count); at += count; headerUsed += count;
        if (headerUsed < 4) continue;
        const length = header.readUInt32BE(0);
        if (length < 4 || length > MAX_ENVELOPE) throw new Error('invalid request size');
        body = Buffer.allocUnsafe(length); bodyUsed = 0;
      }
      const count = Math.min(body.length - bodyUsed, chunk.length - at); chunk.copy(body, bodyUsed, at, at + count); at += count; bodyUsed += count;
      if (bodyUsed === body.length) { receive(body); body = null; headerUsed = 0; }
    }
  } catch { socket.destroy(); }
});
socket.on('error', () => {});
socket.on('close', () => { pool.close(); process.exitCode = 0; });
socket.on('end', () => socket.end());
process.on('SIGTERM', () => { pool.close(); socket.destroy(); });
send({ ok: true, ready: true, order: 0, library_revision: provenance.runtime_revision, library_accepted_revision: provenance.accepted_revision, library: statistics() });
