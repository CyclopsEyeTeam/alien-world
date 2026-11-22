// Cyclops Living Buffer — contract.
//
// Schema identities, fragment validation and the compact binary batch codec.
// Mirrors the ecosystem's conventions (exact fields, fail closed, string schema
// ids that change when meaning changes) without importing any sibling project.
//
// A *fragment* is the smallest useful unit of visual change an application can
// submit. A *batch* is an ordered list of fragments that together form one
// source generation. The engine never publishes a frame that reflects part of a
// generation.

export const BATCH_SCHEMA = 'CLB_BATCH_V0';
export const SNAPSHOT_SCHEMA = 'CLB_SNAPSHOT_V0';

// Fragment kinds. Numeric codes are the wire values of the binary codec.
export const KIND = Object.freeze({
  UPSERT: 1, // create or replace one element (id, layer, shape, bounds, colour)
  REMOVE: 2, // remove one element
  LAYER: 3,  // change a layer's presentation parameters (opacity, blur)
  CLEAR: 4,  // remove every element (complete scene replacement starts here)
});
export const KIND_NAME = Object.freeze({ 1: 'UPSERT', 2: 'REMOVE', 3: 'LAYER', 4: 'CLEAR' });

export const SHAPE = Object.freeze({ RECT: 0, DISC: 1 });
export const SHAPE_NAME = Object.freeze({ 0: 'rect', 1: 'disc' });

export const LIMITS = Object.freeze({
  maxLayers: 8,
  maxBlur: 32,
  maxDimension: 8192,
  maxFragmentsPerBatch: 1 << 20,
  recordBytes: 24,
  headerBytes: 16,
});

const U32 = 0xffffffff;
const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;

export class ContractError extends Error {
  constructor(code, message) { super(`${code}: ${message}`); this.code = code; }
}

// Validate one fragment object. Returns a normalised copy or throws ContractError.
export function validateFragment(f, index = 0) {
  if (!f || typeof f !== 'object') throw new ContractError('FRAGMENT_SHAPE', `fragment ${index} is not an object`);
  const kind = typeof f.kind === 'string' ? KIND[f.kind] : f.kind;
  if (!KIND_NAME[kind]) throw new ContractError('FRAGMENT_KIND', `fragment ${index} has unknown kind ${String(f.kind)}`);
  switch (kind) {
    case KIND.UPSERT: {
      if (!isInt(f.id, 0, U32)) throw new ContractError('FRAGMENT_ID', `fragment ${index}: id must be an integer 0..2^32-1`);
      if (!isInt(f.layer, 0, LIMITS.maxLayers - 1)) throw new ContractError('FRAGMENT_LAYER', `fragment ${index}: layer out of range`);
      const shape = typeof f.shape === 'string' ? SHAPE[f.shape.toUpperCase()] : f.shape;
      if (!SHAPE_NAME[shape]) throw new ContractError('FRAGMENT_SHAPE_KIND', `fragment ${index}: unknown shape`);
      if (!isInt(f.x, -32768, 32767) || !isInt(f.y, -32768, 32767)) throw new ContractError('FRAGMENT_POSITION', `fragment ${index}: x/y must be int16`);
      if (!isInt(f.w, 1, 65535) || !isInt(f.h, 1, 65535)) throw new ContractError('FRAGMENT_SIZE', `fragment ${index}: w/h must be 1..65535`);
      const c = f.rgba;
      if (!Array.isArray(c) || c.length !== 4 || !c.every((v) => isInt(v, 0, 255))) throw new ContractError('FRAGMENT_COLOUR', `fragment ${index}: rgba must be four integers 0..255`);
      return { kind, id: f.id, layer: f.layer, shape, x: f.x, y: f.y, w: f.w, h: f.h, rgba: [c[0], c[1], c[2], c[3]] };
    }
    case KIND.REMOVE:
      if (!isInt(f.id, 0, U32)) throw new ContractError('FRAGMENT_ID', `fragment ${index}: id must be an integer 0..2^32-1`);
      return { kind, id: f.id };
    case KIND.LAYER: {
      if (!isInt(f.layer, 0, LIMITS.maxLayers - 1)) throw new ContractError('FRAGMENT_LAYER', `fragment ${index}: layer out of range`);
      const out = { kind, layer: f.layer };
      if (f.opacity !== undefined) { if (!isInt(f.opacity, 0, 255)) throw new ContractError('FRAGMENT_OPACITY', `fragment ${index}: opacity must be 0..255`); out.opacity = f.opacity; }
      if (f.blur !== undefined) { if (!isInt(f.blur, 0, LIMITS.maxBlur)) throw new ContractError('FRAGMENT_BLUR', `fragment ${index}: blur must be 0..${LIMITS.maxBlur}`); out.blur = f.blur; }
      return out;
    }
    case KIND.CLEAR:
      return { kind };
    default:
      throw new ContractError('FRAGMENT_KIND', `fragment ${index} has unknown kind`);
  }
}

export function validateBatch(batch) {
  if (!batch || typeof batch !== 'object') throw new ContractError('BATCH_SHAPE', 'batch is not an object');
  if (batch.schema !== BATCH_SCHEMA) throw new ContractError('BATCH_SCHEMA', `expected ${BATCH_SCHEMA}`);
  if (!isInt(batch.generation, 1, U32)) throw new ContractError('BATCH_GENERATION', 'generation must be an integer 1..2^32-1');
  if (!Array.isArray(batch.fragments)) throw new ContractError('BATCH_FRAGMENTS', 'fragments must be an array');
  if (batch.fragments.length > LIMITS.maxFragmentsPerBatch) throw new ContractError('BATCH_TOO_LARGE', 'too many fragments');
  return { schema: BATCH_SCHEMA, generation: batch.generation, fragments: batch.fragments.map(validateFragment) };
}

// ---------------------------------------------------------------------------
// Binary codec. One batch = 16-byte header + N fixed 24-byte records.
//
// header: magic 'CLB0' (4) | generation u32 | count u32 | reserved u32
// record: kind u8 | layer u8 | shape u8 | flags u8 | id u32 | x i16 | y i16 |
//         w u16 | h u16 | r u8 g u8 b u8 a u8 | reserved u32
// LAYER records reuse: flags bit0 = has opacity, bit1 = has blur; r = opacity,
// g = blur. Every reserved bit and word must be zero; a decoder refuses otherwise
// (fail closed), so a future flag cannot silently decode as a V0 record.
//
// Fixed records are deliberately simple: they can be appended into a shared
// ring, mapped into a GPU-side struct-of-arrays later, and counted exactly.
// Byte counts reported by the engine are *these* bytes.
const MAGIC = 0x30424c43; // 'CLB0' little-endian

export function encodedBatchBytes(count) { return LIMITS.headerBytes + count * LIMITS.recordBytes; }

export function encodeBatch(batch) {
  const b = validateBatch(batch);
  const buf = new ArrayBuffer(encodedBatchBytes(b.fragments.length));
  const dv = new DataView(buf);
  dv.setUint32(0, MAGIC, true); dv.setUint32(4, b.generation, true); dv.setUint32(8, b.fragments.length, true); dv.setUint32(12, 0, true);
  let o = LIMITS.headerBytes;
  for (const f of b.fragments) {
    dv.setUint8(o, f.kind);
    if (f.kind === KIND.UPSERT) {
      dv.setUint8(o + 1, f.layer); dv.setUint8(o + 2, f.shape); dv.setUint8(o + 3, 0);
      dv.setUint32(o + 4, f.id, true);
      dv.setInt16(o + 8, f.x, true); dv.setInt16(o + 10, f.y, true);
      dv.setUint16(o + 12, f.w, true); dv.setUint16(o + 14, f.h, true);
      dv.setUint8(o + 16, f.rgba[0]); dv.setUint8(o + 17, f.rgba[1]); dv.setUint8(o + 18, f.rgba[2]); dv.setUint8(o + 19, f.rgba[3]);
    } else if (f.kind === KIND.REMOVE) {
      dv.setUint32(o + 4, f.id, true);
    } else if (f.kind === KIND.LAYER) {
      dv.setUint8(o + 1, f.layer);
      let flags = 0; if (f.opacity !== undefined) { flags |= 1; dv.setUint8(o + 16, f.opacity); } if (f.blur !== undefined) { flags |= 2; dv.setUint8(o + 17, f.blur); }
      dv.setUint8(o + 3, flags);
    }
    o += LIMITS.recordBytes;
  }
  return new Uint8Array(buf);
}

export function decodeBatch(bytes) {
  if (!(bytes instanceof Uint8Array)) throw new ContractError('CODEC_INPUT', 'expected Uint8Array');
  if (bytes.byteLength < LIMITS.headerBytes) throw new ContractError('CODEC_SHORT', 'batch shorter than header');
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (dv.getUint32(0, true) !== MAGIC) throw new ContractError('CODEC_MAGIC', 'bad magic');
  const generation = dv.getUint32(4, true); const count = dv.getUint32(8, true);
  if (bytes.byteLength !== encodedBatchBytes(count)) throw new ContractError('CODEC_LENGTH', 'length does not match record count');
  if (dv.getUint32(12, true) !== 0) throw new ContractError('CODEC_RESERVED', 'reserved header word is not zero');
  const fragments = new Array(count);
  let o = LIMITS.headerBytes;
  for (let i = 0; i < count; i++) {
    const kind = dv.getUint8(o);
    if (dv.getUint32(o + 20, true) !== 0) throw new ContractError('CODEC_RESERVED', `record ${i} has a non-zero reserved word`);
    if (kind === KIND.UPSERT) {
      if (dv.getUint8(o + 3) !== 0) throw new ContractError('CODEC_RESERVED', `record ${i} has reserved flag bits set`);
      fragments[i] = { kind, layer: dv.getUint8(o + 1), shape: dv.getUint8(o + 2), id: dv.getUint32(o + 4, true), x: dv.getInt16(o + 8, true), y: dv.getInt16(o + 10, true), w: dv.getUint16(o + 12, true), h: dv.getUint16(o + 14, true), rgba: [dv.getUint8(o + 16), dv.getUint8(o + 17), dv.getUint8(o + 18), dv.getUint8(o + 19)] };
    } else if (kind === KIND.REMOVE) {
      fragments[i] = { kind, id: dv.getUint32(o + 4, true) };
    } else if (kind === KIND.LAYER) {
      const flags = dv.getUint8(o + 3); if (flags & ~3) throw new ContractError('CODEC_RESERVED', `record ${i} has reserved flag bits set`);
      const f = { kind, layer: dv.getUint8(o + 1) };
      if (flags & 1) f.opacity = dv.getUint8(o + 16); if (flags & 2) f.blur = dv.getUint8(o + 17);
      fragments[i] = f;
    } else if (kind === KIND.CLEAR) {
      fragments[i] = { kind };
    } else throw new ContractError('CODEC_KIND', `record ${i} has unknown kind ${kind}`);
    o += LIMITS.recordBytes;
  }
  return validateBatch({ schema: BATCH_SCHEMA, generation, fragments });
}
