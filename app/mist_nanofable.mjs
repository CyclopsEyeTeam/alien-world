#!/usr/bin/env node
// One local NanoFable Mist completion. Request-owned: the Python API helper starts this
// process for exactly one request, writes the chat body on stdin and reaps it afterwards.
// No socket is opened. The system message is used byte for byte; the single Alien user
// message follows in NanoFable's turn format. Greedy decoding stops at a newline/EOS or the
// request's output allowance; there is no template reasoning mode to enable.
// Usage: node mist_nanofable.mjs NANOFABLE_ROOT WEIGHTS_SHA256  (body on stdin, one JSON reply on stdout)
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const EOS = 1;
const CONTEXT = 512;
const fail = message => { process.stderr.write(message + '\n'); process.exit(2); };

const [root, expectedSha] = process.argv.slice(2);
if (!root || !/^[0-9a-f]{64}$/.test(expectedSha ?? '')) fail('usage: mist_nanofable.mjs NANOFABLE_ROOT WEIGHTS_SHA256');
let body;
try {
  const raw = readFileSync(0);
  if (raw.length > 16384) fail('request too large');
  body = JSON.parse(raw.toString('utf8'));
} catch { fail('request is not JSON'); }
const keys = Object.keys(body ?? {}).sort().join(',');
if (keys !== 'chat_template_kwargs,max_tokens,messages,model,stream' || body.model !== 'nanofable' ||
    body.stream !== false || !Number.isInteger(body.max_tokens) || body.max_tokens < 1 || body.max_tokens > 64 ||
    JSON.stringify(body.chat_template_kwargs) !== '{"enable_thinking":false}') fail('unsupported Mist request');
const [system, user] = body.messages ?? [];
if (body.messages.length !== 2 || system?.role !== 'system' || user?.role !== 'user' ||
    typeof system.content !== 'string' || typeof user.content !== 'string' || !user.content.trim()) fail('Mist needs one system and one user message');

const runtime = join(root, 'runtime');
const { parseSafetensors } = await import(pathToFileURL(join(runtime, 'js/runtime.mjs')));
const { Model } = await import(pathToFileURL(join(runtime, 'js/model.mjs')));
const { Tokenizer } = await import(pathToFileURL(join(runtime, 'js/tokenizer.mjs')));
const bytes = readFileSync(join(root, 'checkpoint/model.safetensors'));
const sha = createHash('sha256').update(bytes).digest('hex');
// The weights actually loaded must be the ones the caller verified against the manifest.
if (sha !== expectedSha) fail('NanoFable weights changed after verification');
const arch = JSON.parse(readFileSync(join(root, 'checkpoint/architecture.json'), 'utf8'));
const n_layer = arch.n_layer ?? 4;
if (arch.context !== CONTEXT || arch.vocab !== 4096 || !Number.isInteger(n_layer) || n_layer < 4 || n_layer > 12 ||
    arch.mlp_widths?.length !== n_layer || arch.mlp_widths.some(w => w !== 384)) fail('unsupported NanoFable architecture');
const tensors = parseSafetensors(bytes);
if (tensors.size !== 2 + n_layer * 9) fail('unexpected NanoFable checkpoint');
const model = new Model({ header: { config: { n_layer, n_embd: 128, n_head: 4, ctx: CONTEXT, vocab: 4096 } }, tensors });
const tok = new Tokenizer(JSON.parse(readFileSync(join(runtime, 'original/tokenizer.json'), 'utf8')));

const prompt = `${system.content}\nUser: ${user.content}\nAlien:`;
// Plain-text encoding: literal special-token names in speech stay ordinary text.
const ids = tok.encodeText(prompt);
if (ids.length + body.max_tokens > CONTEXT) fail('Mist prompt leaves no room for its reply');
model.reset();
let logits;
for (const id of ids) logits = model.step(id);
const reply = [];
const decoder = tok.streamDecoder();
let text = '', ended = false;
for (let n = 0; n < body.max_tokens; n++) {
  // The same light repetition penalty as NanoFable's Companion decoder.
  const l = Float32Array.from(logits);
  for (const id of new Set(reply)) l[id] = l[id] > 0 ? l[id] / 1.1 : l[id] * 1.1;
  let next = 0;
  for (let j = 1; j < l.length; j++) if (l[j] > l[next]) next = j;
  if (next === EOS) break;
  const piece = decoder.push(next);
  if (piece.includes('\n')) { text += piece.split('\n')[0]; ended = true; break; }
  reply.push(next); text += piece; logits = model.step(next);
}
if (!ended) text += decoder.flush().split('\n')[0];
const content = text.trim();
if (!content) fail('NanoFable produced an empty reply');
process.stdout.write(JSON.stringify({
  object: 'chat.completion', model: `nanofable-r16-${sha.slice(0, 12)}`,
  choices: [{ index: 0, message: { role: 'assistant', content }, finish_reason: reply.length >= body.max_tokens ? 'length' : 'stop' }],
  usage: { prompt_tokens: ids.length, completion_tokens: reply.length },
}));
