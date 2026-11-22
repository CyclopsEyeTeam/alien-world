// Empty receiving space, never a source event. All payload storage stays private;
// the engine's synchronous decoder copies real bytes before a lease is returned.
import { ContractError } from './contract.js';
import { RetentionPolicy } from './retention.js';

export const MIRROR_DEFAULTS = Object.freeze({
  blockBytes: 64 * 1024, readyBlocks: 16, maxMirrors: 64,
  maxLogicalBytes: 2 ** 30, maxCoverageRanges: 1024, poolCount: 3, maxPayloadBytes: null,
  requireCohesion: false, maxPatterns: 512,
  elastic: false, minReadyBlocks: 1, sharedCategories: false, maxCategories: 100, demandWindow: 'learned',
  blanket: false,
  burstRetention: false,
});
export const MIRROR_LIMITS = Object.freeze({
  minBlockBytes: 256, maxBlockBytes: 2 ** 20, maxReadyBlocks: 256,
  maxReadyBytes: 16 * 2 ** 20, maxMirrors: 4096,
  maxLogicalBytes: 2 ** 40, maxCoverageRanges: 65536, maxPoolCount: 100,
  maxPatterns: 4096, maxLabelUnits: 64, maxCategories: 4096, maxDemandWindow: 64,
});

const integer = (n, lo, hi) => Number.isSafeInteger(n) && n >= lo && n <= hi;
const refused = (reason) => ({ accepted: false, reason });
const now = () => globalThis.performance ? performance.now() : Date.now();
const typedArray = Object.getPrototypeOf(Uint8Array.prototype);
const bufferOf = Object.getOwnPropertyDescriptor(typedArray, 'buffer').get;
const offsetOf = Object.getOwnPropertyDescriptor(typedArray, 'byteOffset').get;
const lengthOf = Object.getOwnPropertyDescriptor(typedArray, 'byteLength').get;
const tagOf = Object.getOwnPropertyDescriptor(typedArray, Symbol.toStringTag).get;
const bufferLengthOf = Object.getOwnPropertyDescriptor(ArrayBuffer.prototype, 'byteLength').get;
const resizable = Object.getOwnPropertyDescriptor(ArrayBuffer.prototype, 'resizable')?.get;
const label = (value) => typeof value === 'string' && value.length > 0 && value.length <= MIRROR_LIMITS.maxLabelUnits;

function normaliseLabels(selector) {
  try {
    if (Array.isArray(selector)) return null;
    const keys = Reflect.ownKeys(selector);
    if (keys.length !== 2 || !keys.includes('category') || !keys.includes('pattern')) return null;
    const category = selector.category, pattern = selector.pattern;
    return label(category) && label(pattern) ? { category, pattern } : null;
  } catch { return null; }
}

function configuration(options) {
  if (!options || typeof options !== 'object' || Array.isArray(options) ||
      Reflect.ownKeys(options).some((k) => !Object.hasOwn(MIRROR_DEFAULTS, k))) {
    throw new ContractError('MIRROR_OPTIONS', 'unknown or invalid pool options');
  }
  const o = { ...MIRROR_DEFAULTS, ...options }, l = MIRROR_LIMITS;
  if (!integer(o.blockBytes, l.minBlockBytes, l.maxBlockBytes) ||
      !integer(o.poolCount, 1, l.maxPoolCount) ||
      !integer(o.readyBlocks, o.poolCount, l.maxReadyBlocks)) {
    throw new ContractError('MIRROR_OPTIONS', 'pool limits must be finite bounded integers');
  }
  const readyBytes = o.blockBytes * o.readyBlocks;
  if (o.maxPayloadBytes === null) o.maxPayloadBytes = readyBytes;
  if (readyBytes > l.maxReadyBytes ||
      !integer(o.maxPayloadBytes, 1, readyBytes) ||
      typeof o.elastic !== 'boolean' || typeof o.sharedCategories !== 'boolean' ||
      typeof o.blanket !== 'boolean' || (o.blanket && (!o.elastic || o.poolCount !== 1)) ||
      typeof o.burstRetention !== 'boolean' || (o.burstRetention && (!o.elastic || o.poolCount !== 1 || o.demandWindow !== 'learned')) ||
      ((o.elastic || o.sharedCategories) && o.poolCount !== 1) ||
      !integer(o.minReadyBlocks, 1, o.readyBlocks) || !integer(o.maxCategories, 1, l.maxCategories) ||
      (o.demandWindow !== 'learned' && !integer(o.demandWindow, 1, l.maxDemandWindow)) ||
      typeof o.requireCohesion !== 'boolean' || !integer(o.maxPatterns, 1, l.maxPatterns) ||
      !integer(o.maxMirrors, 1, l.maxMirrors) || !integer(o.maxLogicalBytes, 1, l.maxLogicalBytes) ||
      !integer(o.maxCoverageRanges, 1, l.maxCoverageRanges)) {
    throw new ContractError('MIRROR_OPTIONS', 'pool limits must be finite bounded integers');
  }
  return Object.freeze(o);
}

// Internal engine component. Not a transferable/borrowed-buffer API: consumers
// must be the engine's synchronous submit decoder, never retain this scratch.
export class MirrorPool {
  #options; #submit; #pools; #freeBlocks; #nextPool = 0; #gather; #handles = new Map(); #closed = false; #busy = false;
  #logicalBytes = 0; #coverageRanges = 0; #validBytes = 0;
  #warmupMs; #writtenBytes = 0; #gatheredBytes = 0; #clearedBytes = 0;
  #homeGrants = 0; #borrowedGrants = 0; #donorScans = 0; #armRefusals = 0;
  #directSubmissions = 0; #gatherSubmissions = 0; #pageClearedBytes; #gatherClearedBytes;
  #categories = new Map(); #patternsRegistered = 0;
  #readyBlocks = 0; #pagesGrown = 0; #pagesDropped = 0;
  #gatherGrowths = 0; #gatherShrinks = 0; #allocationRefusals = 0; #trims = 0;
  #peakAllocatedBytes = 0; #peakTransientBytes = 0; #peakReadyBytes = 0; #peakGatherBytes = 0;
  #demands = []; #demandCursor = 0;
  #retention = null;
  #blankets = new Set(); #blanketAllocations = 0; #blanketReuses = 0; #blanketDirect = 0; #blanketFallbacks = 0; #blanketDropped = 0;
  #physicalArrayAllocations = 0;
  #burstSnapshots = 0; #burstLastReady = 0; #burstPeakReady = 0; #burstFailures = 0;

  constructor(options = {}, submit) {
    this.#options = configuration(options);
    if (typeof submit !== 'function') throw new ContractError('MIRROR_OPTIONS', 'synchronous submit callback required');
    this.#submit = submit;
    if (this.#options.elastic && this.#options.demandWindow === 'learned') this.#retention = new RetentionPolicy(this.#options.maxPatterns, MIRROR_LIMITS.maxDemandWindow, this.#options.readyBlocks);
    const start = now(), { blockBytes, poolCount, maxPayloadBytes, elastic, minReadyBlocks } = this.#options;
    const readyBlocks = elastic ? minReadyBlocks : this.#options.readyBlocks;
    // Fixed mode warms its whole allowance; elastic mode warms only the floor.
    // Owned ArrayBuffers are not a promise of physical RAM residency.
    this.#pools = Array.from({ length: poolCount }, (_, id) => {
      const capacityBlocks = Math.floor(readyBlocks / poolCount) + Number(id < readyBlocks % poolCount);
      const home = { id, category: null, capacityBlocks, free: [], ownedLeasedBlocks: 0, borrowedInBlocks: 0,
        loanedOutBlocks: 0, handles: 0, homeGrants: 0, borrowedGrants: 0, donorScans: 0, armRefusals: 0 };
      for (let n = 0; n < capacityBlocks; n++) {
        home.free.push(this.#newPage(id, elastic && this.#options.blanket));
      }
      return home;
    });
    this.#readyBlocks = this.#freeBlocks = readyBlocks;
    this.#gather = elastic ? null : new Uint8Array(maxPayloadBytes).fill(0);
    if (this.#gather) this.#physicalArrayAllocations++;
    this.#pageClearedBytes = blockBytes * readyBlocks;
    this.#gatherClearedBytes = this.#gather?.byteLength ?? 0;
    this.#clearedBytes = this.#pageClearedBytes + this.#gatherClearedBytes;
    this.#warmupMs = now() - start;
    this.#observePeak();
  }

  #newPage(homePool, floor = false) {
    const block = this.#options.blockBytes;
    const bytes = new Uint8Array(block).fill(0); this.#physicalArrayAllocations++;
    const page = { bytes, borrower: null, dirtyLo: block, dirtyHi: 0, floor };
    Object.defineProperty(page, 'homePool', { value: homePool });
    return page;
  }

  #observePeak(extraBytes = 0) {
    const ready = this.#readyBlocks * this.#options.blockBytes, gather = this.#gather?.byteLength ?? 0;
    this.#peakReadyBytes = Math.max(this.#peakReadyBytes, ready);
    this.#peakGatherBytes = Math.max(this.#peakGatherBytes, gather);
    this.#peakAllocatedBytes = Math.max(this.#peakAllocatedBytes, ready + gather);
    this.#peakTransientBytes = Math.max(this.#peakTransientBytes, ready + gather + extraBytes);
  }

  #growPages(count) {
    const pages = [], block = this.#options.blockBytes;
    try {
      for (let n = 0; n < count; n++) {
        pages.push(this.#newPage(0));
        this.#pageClearedBytes += block; this.#clearedBytes += block;
        this.#observePeak(pages.length * block);
      }
    } catch { this.#allocationRefusals++; return false; }
    // Publish new backing only after every requested page exists.
    const home = this.#pools[0];
    home.free.push(...pages); home.capacityBlocks += count;
    this.#freeBlocks += count; this.#readyBlocks += count; this.#pagesGrown += count;
    this.#observePeak(); return true;
  }

  #armBlanket(item, count) {
    let blanket = null;
    for (const candidate of this.#blankets) {
      if (candidate.pages.length >= count && candidate.pages.every((page) => page.borrower === null) &&
          (!blanket || candidate.pages.length < blanket.pages.length)) blanket = candidate;
    }
    if (blanket) this.#blanketReuses++;
    else {
      const rounded = Math.ceil(Math.sqrt(count)) ** 2, block = this.#options.blockBytes;
      if (rounded > this.#options.readyBlocks - this.#readyBlocks) return null; // ordinary paged fallback
      try {
        const bytes = new Uint8Array(rounded * block).fill(0); this.#physicalArrayAllocations++;
        this.#observePeak(bytes.byteLength);
        this.#pageClearedBytes += bytes.byteLength; this.#clearedBytes += bytes.byteLength;
        blanket = { bytes, pages: [], prefixBlocks: count };
        for (let i = 0; i < rounded; i++) {
          const page = { bytes: new Uint8Array(bytes.buffer, i * block, block), borrower: null,
            dirtyLo: block, dirtyHi: 0, blanket, floor: false };
          Object.defineProperty(page, 'homePool', { value: 0 }); blanket.pages.push(page);
        }
      } catch { this.#allocationRefusals++; return refused('MIRROR_ALLOCATION'); }
      // The whole physical region, including padding, is published atomically.
      this.#blankets.add(blanket); this.#blanketAllocations++;
      const home = this.#pools[0]; home.free.push(...blanket.pages); home.capacityBlocks += rounded;
      this.#freeBlocks += rounded; this.#readyBlocks += rounded; this.#pagesGrown += rounded; this.#observePeak();
    }
    blanket.prefixBlocks = count;
    const home = this.#pools[0];
    for (let i = 0; i < count; i++) {
      const page = blanket.pages[i]; home.free.splice(home.free.indexOf(page), 1);
      item.pages.set(i, this.#leasePage(page, item.poolId));
    }
    return { accepted: true, armedBytes: count * this.#options.blockBytes };
  }

  #blanketPrefix(item, length) {
    const block = this.#options.blockBytes, count = Math.ceil(length / block), first = item.pages.get(0);
    if (!first?.blanket) return null;
    const buffer = first.bytes.buffer, start = first.bytes.byteOffset;
    for (let i = 1; i < count; i++) {
      const page = item.pages.get(i);
      if (!page || page.bytes.buffer !== buffer || page.bytes.byteOffset !== start + i * block) return null;
    }
    try { return { bytes: new Uint8Array(buffer, start, length) }; }
    catch { this.#allocationRefusals++; return refused('MIRROR_ALLOCATION'); }
  }

  #dropBlanket(blanket) {
    const count = blanket.pages.length, home = this.#pools[0];
    home.free = home.free.filter((page) => page.blanket !== blanket);
    home.capacityBlocks -= count; this.#readyBlocks -= count; this.#freeBlocks -= count; this.#pagesDropped += count;
    for (const page of blanket.pages) page.bytes = null;
    blanket.pages.length = 0; blanket.bytes = null; this.#blankets.delete(blanket); this.#blanketDropped++;
  }

  #shrinkBlankets(target, minimum) {
    const home = this.#pools[0];
    for (let i = home.free.length - 1; i >= 0 && this.#readyBlocks > target; i--) {
      const page = home.free[i];
      if (page.blanket || page.floor) continue;
      home.free.splice(i, 1); home.capacityBlocks--; this.#readyBlocks--; this.#freeBlocks--; this.#pagesDropped++;
    }
    for (const blanket of this.#blankets) {
      if (this.#readyBlocks <= target) break;
      if (this.#readyBlocks - blanket.pages.length >= minimum && blanket.pages.every((page) => page.borrower === null)) this.#dropBlanket(blanket);
    }
  }

  #gatherSize(length) {
    let size = 1;
    while (size < length) size *= 2;
    return Math.min(size, this.#options.maxPayloadBytes);
  }

  #resizeGather(size) {
    const oldSize = this.#gather?.byteLength ?? 0;
    if (oldSize === size) return true;
    let next = null;
    if (size) {
      try { next = new Uint8Array(size).fill(0); }
      catch { this.#allocationRefusals++; return false; }
      this.#observePeak(size); // old and replacement coexist during allocation.
      this.#physicalArrayAllocations++;
      this.#gatherClearedBytes += size; this.#clearedBytes += size;
    }
    this.#gather = next;
    if (size > oldSize) this.#gatherGrowths++; else this.#gatherShrinks++;
    this.#observePeak(); return true;
  }

  #maintain(demandBytes = 0, force = false, speculative = false) {
    const o = this.#options;
    if (!o.elastic) return;
    if (force) { this.#demands.length = 0; this.#demandCursor = 0; this.#retention?.resetWorking(); }
    else if (!this.#retention && !speculative && demandBytes > 0) {
      this.#demands[this.#demandCursor] = demandBytes;
      this.#demandCursor = (this.#demandCursor + 1) % o.demandWindow;
    }
    // Remember only a bounded window of actual use sizes. Empty reservations
    // neither invent zero-demand samples nor evict real working-set history.
    const recent = this.#retention ? this.#retention.demandBytes() : Math.max(0, ...this.#demands);
    const live = this.#readyBlocks - this.#freeBlocks;
    const demand = Math.max(Math.ceil(recent / o.blockBytes), o.burstRetention ? this.#retention.demandReadyBlocks() : 0);
    const minimum = Math.max(o.minReadyBlocks, live, demand);
    const target = Math.max(minimum,
      force || speculative ? 0 : Math.ceil(this.#readyBlocks / 2));
    const home = this.#pools[0];
    if (o.blanket) this.#shrinkBlankets(target, minimum);
    else while (this.#readyBlocks > target && home.free.length) {
      home.free.pop(); home.capacityBlocks--; this.#readyBlocks--; this.#freeBlocks--; this.#pagesDropped++;
    }
    const current = this.#gather?.byteLength ?? 0;
    const needed = recent > o.blockBytes ? this.#gatherSize(recent) : 0;
    if (current > needed) {
      let next = force || speculative ? needed : Math.max(needed, Math.floor(current / 2));
      if (!needed && next <= o.blockBytes) next = 0;
      this.#resizeGather(next);
    }
  }

  trimMirrors() {
    if (this.#closed) return refused('CLOSED');
    if (this.#busy) return refused('MIRROR_BUSY');
    const before = this.#readyBlocks * this.#options.blockBytes + (this.#gather?.byteLength ?? 0);
    this.#maintain(0, true); this.#trims++;
    const after = this.#readyBlocks * this.#options.blockBytes + (this.#gather?.byteLength ?? 0);
    return { accepted: true, trimmed: before - after };
  }

  #get(handle) {
    if (this.#closed) return refused('CLOSED');
    const item = this.#handles.get(handle);
    return item ?? refused('INVALID_MIRROR');
  }

  prepareMirror(capacityBytes, selector) {
    if (this.#closed) return refused('CLOSED');
    if (this.#busy) return refused('MIRROR_BUSY');
    if (!integer(capacityBytes, 1, MIRROR_LIMITS.maxLogicalBytes)) return refused('MIRROR_RANGE');
    // Producer getters/proxies may close, reset, or recursively prepare. Capture
    // only primitive labels, then read every registry/resource decision afresh.
    const labelled = selector !== null && typeof selector === 'object';
    const labels = labelled ? normaliseLabels(selector) : null;
    if (this.#closed) return refused('CLOSED');
    if (this.#busy) return refused('MIRROR_BUSY');
    if ((labelled && labels === null) || (!labelled && selector !== undefined && typeof selector !== 'number')) return refused('MIRROR_SELECTOR');
    const o = this.#options;
    if (o.requireCohesion && !labels) return refused('MIRROR_COHESION_REQUIRED');
    if (this.#handles.size >= o.maxMirrors || capacityBytes > o.maxLogicalBytes - this.#logicalBytes) return refused('MIRROR_BACKPRESSURE');
    let poolId, record, newCategory = false, newPattern = false;
    const automatic = !labels && selector === undefined;
    if (labels) {
      record = this.#categories.get(labels.category);
      if (!record && this.#categories.size >= o.maxCategories) return refused('MIRROR_CATEGORY_BACKPRESSURE');
      if (record) poolId = record.poolId;
      else if (o.sharedCategories) {
        if (this.#categories.size >= o.maxCategories || (!this.#categories.size && this.#pools[0].handles)) return refused('MIRROR_CATEGORY_BACKPRESSURE');
        poolId = 0; newCategory = true;
      }
      else {
        const home = this.#pools.find((candidate) => candidate.category === null && candidate.handles === 0);
        if (!home) return refused('MIRROR_CATEGORY_BACKPRESSURE');
        poolId = home.id; newCategory = true;
      }
      newPattern = !record?.patterns.has(labels.pattern);
      if (newPattern && this.#patternsRegistered >= o.maxPatterns) return refused('MIRROR_PATTERN_BACKPRESSURE');
    } else if (automatic) {
      if (o.sharedCategories && this.#categories.size) return refused('MIRROR_CATEGORY_BACKPRESSURE');
      for (let n = 0; n < o.poolCount; n++) {
        const id = (this.#nextPool + n) % o.poolCount;
        if (this.#pools[id].category === null) { poolId = id; break; }
      }
      if (poolId === undefined) return refused('MIRROR_CATEGORY_BACKPRESSURE');
    } else {
      poolId = selector;
      if (!integer(poolId, 0, o.poolCount - 1)) return refused('MIRROR_POOL');
      if (o.sharedCategories && this.#categories.size) return refused('MIRROR_CATEGORY_ASSIGNED');
      if (this.#pools[poolId].category !== null) return refused('MIRROR_CATEGORY_ASSIGNED');
    }
    // All refusal paths finish before publishing any category, pattern or handle.
    if (newCategory) {
      record = { poolId, patterns: new Set() }; this.#categories.set(labels.category, record);
      if (!o.sharedCategories) this.#pools[poolId].category = labels.category;
    }
    if (newPattern) { record.patterns.add(labels.pattern); this.#patternsRegistered++; }
    const handle = Object.freeze({}); // object identity binds the handle to this pool and epoch
    this.#handles.set(handle, { poolId, category: labels?.category ?? null, pattern: labels?.pattern ?? null,
      borrowedBlocks: 0, capacityBytes, pages: new Map(), ranges: [], validBytes: 0, actualLength: null });
    this.#logicalBytes += capacityBytes;
    this.#pools[poolId].handles++;
    if (automatic) this.#nextPool = (poolId + 1) % o.poolCount;
    return { accepted: true, handle, poolId, category: labels?.category ?? null, pattern: labels?.pattern ?? null };
  }

  #takePage(poolId) {
    const borrower = this.#pools[poolId]; let donor = borrower;
    if (!donor.free.length) {
      for (let n = 1; n < this.#pools.length; n++) {
        borrower.donorScans++; this.#donorScans++;
        donor = this.#pools[(poolId + n) % this.#pools.length];
        if (donor.free.length) break;
      }
    }
    return this.#leasePage(donor.free.pop(), poolId);
  }

  #leasePage(page, poolId) {
    const borrower = this.#pools[poolId], donor = this.#pools[page.homePool]; page.borrower = poolId;
    donor.ownedLeasedBlocks++; this.#freeBlocks--;
    if (donor === borrower) { borrower.homeGrants++; this.#homeGrants++; }
    else {
      donor.loanedOutBlocks++; borrower.borrowedInBlocks++;
      borrower.borrowedGrants++; this.#borrowedGrants++;
    }
    return page;
  }

  armMirror(handle, offset = 0, length) {
    const item = this.#get(handle); if (item.accepted === false) return item;
    if (this.#busy) return refused('MIRROR_BUSY');
    if (item.actualLength !== null) return refused('MIRROR_SEALED');
    const block = this.#options.blockBytes;
    if (!integer(offset, 0, item.capacityBytes)) return refused('MIRROR_RANGE');
    if (length === undefined) length = Math.min(block, item.capacityBytes - offset);
    if (!this.#range(item, offset, length)) return refused('MIRROR_RANGE');
    if (length === 0) return { accepted: true, armedBytes: item.pages.size * block };
    const first = Math.floor(offset / block), last = Math.floor((offset + length - 1) / block);
    let owned = 0;
    for (const page of item.pages.keys()) if (page >= first && page <= last) owned++;
    // Preflight numerically before walking the requested span: it may be huge.
    const needed = last - first + 1 - owned;
    if (needed > this.#freeBlocks && (!this.#options.elastic ||
        needed - this.#freeBlocks > this.#options.readyBlocks - this.#readyBlocks)) {
      this.#armRefusals++; this.#pools[item.poolId].armRefusals++;
      return refused('MIRROR_BACKPRESSURE');
    }
    if (this.#options.blanket && item.pages.size === 0 && offset === 0 && length > block) {
      const result = this.#armBlanket(item, needed);
      if (result !== null) return result;
    }
    if (needed > this.#freeBlocks && !this.#growPages(needed - this.#freeBlocks)) {
      this.#armRefusals++; this.#pools[item.poolId].armRefusals++;
      return refused('MIRROR_ALLOCATION');
    }
    for (let page = first; page <= last; page++) if (!item.pages.has(page)) {
      const backing = this.#takePage(item.poolId); item.pages.set(page, backing);
      if (backing.homePool !== item.poolId) item.borrowedBlocks++;
    }
    return { accepted: true, armedBytes: item.pages.size * block };
  }

  #range(item, offset, length) {
    return integer(offset, 0, item.capacityBytes) && integer(length, 0, item.capacityBytes - offset);
  }

  writeMirror(handle, offset, bytes) {
    const item = this.#get(handle); if (item.accepted === false) return item;
    if (this.#busy) return refused('MIRROR_BUSY');
    if (item.actualLength !== null) return refused('MIRROR_SEALED');
    // Avoid a concurrently changing producer view or a detached empty view.
    try {
      // Intrinsic brand checks do not walk producer-controlled prototypes.
      if (tagOf.call(bytes) !== 'Uint8Array') return refused('MIRROR_BYTES');
      const buffer = bufferOf.call(bytes);
      bufferLengthOf.call(buffer); // rejects SharedArrayBuffer and fake wrappers
      if (resizable?.call(buffer)) return refused('MIRROR_BYTES');
      // A plain view avoids caller-defined accessors, species and subarray hooks
      // that could reenter the pool or fabricate the received bytes.
      bytes = new Uint8Array(buffer, offsetOf.call(bytes), lengthOf.call(bytes));
    } catch { return refused('MIRROR_BYTES'); }
    const length = bytes.byteLength;
    if (!this.#range(item, offset, length)) return refused('MIRROR_RANGE');
    if (length === 0) return { accepted: true, written: 0, validBytes: item.validBytes, validLength: this.#prefix(item) };
    const block = this.#options.blockBytes, end = offset + length;
    const first = Math.floor(offset / block), last = Math.floor((end - 1) / block);
    if (last - first + 1 > item.pages.size) return refused('MIRROR_NOT_ARMED');
    for (let page = first; page <= last; page++) if (!item.pages.has(page)) return refused('MIRROR_NOT_ARMED');

    // Extending/overwriting the last covered region cannot touch an earlier
    // region or increase range pressure. Keep that common streaming path free
    // of temporary coverage lists. Commit its endpoint only after byte copying.
    const tail = item.ranges[item.ranges.length - 1];
    const extendTail = tail && offset >= tail[0] && offset <= tail[1];
    let ranges, newCount, valid;
    if (extendTail) {
      ranges = item.ranges; newCount = this.#coverageRanges;
      valid = item.validBytes + Math.max(0, end - tail[1]);
    } else {
      // Plan merged coverage first, so refusal changes neither bytes nor metadata.
      ranges = []; let lo = offset, hi = end, inserted = false, mergedBytes = 0;
      for (const [start, stop] of item.ranges) {
        if (stop < lo) ranges.push([start, stop]);
        else if (hi < start) { if (!inserted) { ranges.push([lo, hi]); inserted = true; } ranges.push([start, stop]); }
        else { lo = Math.min(lo, start); hi = Math.max(hi, stop); mergedBytes += stop - start; }
      }
      if (!inserted) ranges.push([lo, hi]);
      newCount = this.#coverageRanges - item.ranges.length + ranges.length;
      if (newCount > this.#options.maxCoverageRanges) return refused('MIRROR_COVERAGE_PRESSURE');
      valid = item.validBytes - mergedBytes + hi - lo;
    }
    let consumed = 0;
    while (consumed < length) {
      const at = offset + consumed, page = Math.floor(at / block), within = at % block;
      const count = Math.min(length - consumed, block - within);
      const backing = item.pages.get(page);
      backing.bytes.set(count === length ? bytes : bytes.subarray(consumed, consumed + count), within);
      backing.dirtyLo = Math.min(backing.dirtyLo, within);
      backing.dirtyHi = Math.max(backing.dirtyHi, within + count);
      consumed += count;
    }
    if (extendTail) tail[1] = Math.max(tail[1], end);
    this.#validBytes += valid - item.validBytes; this.#coverageRanges = newCount;
    item.ranges = ranges; item.validBytes = valid; this.#writtenBytes += length;
    return { accepted: true, written: length, validBytes: valid, validLength: this.#prefix(item) };
  }

  #prefix(item) { return item.ranges[0]?.[0] === 0 ? item.ranges[0][1] : 0; }

  #writtenPressure(fallback, item, simplePrefix) {
    this.#burstSnapshots = Math.min(Number.MAX_SAFE_INTEGER, this.#burstSnapshots + 1);
    let blocks = 0, includedFloor = 0;
    try {
      if (this.#handles.size === 1 && (!this.#options.blanket || simplePrefix)) {
        blocks = fallback;
        if (this.#options.blanket) {
          const first = item.pages.get(0), floor = this.#options.minReadyBlocks;
          blocks = first.blanket ? first.blanket.pages.length + floor : first.floor ? floor : 1 + floor;
        }
      } else {
        const blankets = this.#options.blanket ? new Set() : null, block = this.#options.blockBytes;
        for (const held of this.#handles.values()) {
          if (!held.validBytes) continue;
          for (const [index, page] of held.pages) {
            if (held.actualLength !== null ? index * block >= held.actualLength : page.dirtyHi <= page.dirtyLo) continue;
            if (page.blanket) {
              if (!blankets.has(page.blanket)) { blankets.add(page.blanket); blocks += page.blanket.pages.length; }
            } else { blocks++; if (page.floor) includedFloor++; }
          }
        }
        if (this.#options.blanket) blocks += Math.max(0, this.#options.minReadyBlocks - includedFloor);
      }
    } catch {
      this.#burstFailures = Math.min(Number.MAX_SAFE_INTEGER, this.#burstFailures + 1); blocks = fallback;
    }
    this.#burstLastReady = Math.min(this.#options.readyBlocks, Math.max(fallback, blocks));
    this.#burstPeakReady = Math.max(this.#burstPeakReady, this.#burstLastReady);
    return this.#burstLastReady;
  }

  sealMirror(handle, actualLength) {
    const item = this.#get(handle); if (item.accepted === false) return item;
    if (this.#busy) return refused('MIRROR_BUSY');
    if (item.actualLength !== null) return refused('MIRROR_SEALED');
    if (!integer(actualLength, 1, Math.min(item.capacityBytes, this.#options.maxPayloadBytes))) return refused('MIRROR_RANGE');
    if (this.#prefix(item) < actualLength) return refused('MIRROR_HOLES');
    item.actualLength = actualLength;
    return { accepted: true, length: actualLength };
  }

  submitMirror(handle) {
    const item = this.#get(handle); if (item.accepted === false) return item;
    if (this.#busy) return refused('MIRROR_BUSY');
    if (item.actualLength === null) return refused('MIRROR_UNSEALED');
    const length = item.actualLength, block = this.#options.blockBytes;
    const direct = length <= block;
    const blanket = this.#options.blanket && !direct ? this.#blanketPrefix(item, length) : null;
    if (blanket?.accepted === false) return blanket;
    let bytes, scratch = null;
    if (direct || blanket) {
      // The synchronous engine decoder copies this covered prefix before its
      // lease can end. Refusal/throw leaves the original page untouched.
      bytes = blanket ? blanket.bytes : item.pages.get(0).bytes.subarray(0, length); this.#directSubmissions++;
      if (blanket) this.#blanketDirect++;
    } else {
      if (this.#options.blanket) this.#blanketFallbacks++;
      if ((this.#gather?.byteLength ?? 0) < length && !this.#resizeGather(this.#gatherSize(length))) return refused('MIRROR_ALLOCATION');
      scratch = this.#gather;
      // Decode only the covered actual prefix; retain the exact scratch until
      // its finally scrub even if maintenance later replaces/drops the field.
      for (let offset = 0; offset < length; offset += block) {
        const count = Math.min(length - offset, block);
        scratch.set(item.pages.get(offset / block).bytes.subarray(0, count), offset);
      }
      this.#gatheredBytes += length; this.#gatherSubmissions++;
      bytes = scratch.subarray(0, length);
    }
    this.#busy = true;
    let accepted = false, workingSetBlocks = Math.ceil(length / block);
    try {
      const result = item.category === null ? this.#submit(bytes) : this.#submit(bytes, Object.freeze({
        category: item.category, pattern: item.pattern, poolId: item.poolId,
        blockBytes: block, armedBytes: item.pages.size * block,
        actualLength: length, maxPayloadBytes: this.#options.maxPayloadBytes,
        ...(this.#options.blanket ? { receivePath: blanket ? 'blanket' : direct ? 'direct' : 'gather' } : {}),
      }));
      if (result?.accepted === true) {
        accepted = true;
        if (this.#options.burstRetention) workingSetBlocks = this.#writtenPressure(workingSetBlocks, item, direct || Boolean(blanket));
        this.#release(handle, item);
      }
      return result;
    } finally {
      if (scratch) {
        scratch.fill(0, 0, length); this.#gatherClearedBytes += length; this.#clearedBytes += length;
      }
      if (accepted) this.#retention?.observe(item.category, item.pattern, length, Math.ceil(length / block),
        direct ? 0 : this.#gatherSize(length), workingSetBlocks);
      this.#busy = false;
      this.#maintain(length);
    }
  }

  #release(handle, item) {
    const borrower = this.#pools[item.poolId];
    for (const page of item.pages.values()) {
      if (page.dirtyHi > page.dirtyLo) {
        const length = page.dirtyHi - page.dirtyLo;
        page.bytes.fill(0, page.dirtyLo, page.dirtyHi);
        this.#pageClearedBytes += length; this.#clearedBytes += length;
      }
      page.dirtyLo = page.bytes.byteLength; page.dirtyHi = 0;
      const home = this.#pools[page.homePool]; home.ownedLeasedBlocks--;
      if (home !== borrower) { home.loanedOutBlocks--; borrower.borrowedInBlocks--; }
      page.borrower = null; home.free.push(page); this.#freeBlocks++;
    }
    borrower.handles--;
    this.#logicalBytes -= item.capacityBytes; this.#validBytes -= item.validBytes;
    this.#coverageRanges -= item.ranges.length; this.#handles.delete(handle);
    if (this.#options.blanket) item.pages.clear();
  }

  releaseMirror(handle) {
    const item = this.#get(handle); if (item.accepted === false) return item;
    if (this.#busy) return refused('MIRROR_BUSY');
    const demand = item.actualLength ?? item.validBytes, neverWritten = item.validBytes === 0;
    this.#release(handle, item); this.#maintain(demand, false, neverWritten); return { accepted: true };
  }

  resetMirrors() {
    if (this.#closed) return refused('CLOSED');
    if (this.#busy) return refused('MIRROR_BUSY');
    const released = this.#handles.size;
    for (const [handle, item] of this.#handles) this.#release(handle, item);
    this.#nextPool = 0;
    this.#maintain(0, true);
    return { accepted: true, released };
  }

  categoryStatus(category) {
    if (this.#closed) return refused('CLOSED');
    if (!label(category)) return refused('MIRROR_SELECTOR');
    const record = this.#categories.get(category);
    if (!record) return refused('MIRROR_CATEGORY_UNKNOWN');
    const patterns = new Map([...record.patterns].map((pattern) => [pattern, { pattern, activeHandles: 0 }]));
    let activeHandles = 0, validBytes = 0, potentialCapacityBytes = 0;
    for (const item of this.#handles.values()) if (item.category === category) {
      activeHandles++; validBytes += item.validBytes; potentialCapacityBytes += item.capacityBytes;
      patterns.get(item.pattern).activeHandles++;
    }
    return { accepted: true, category, poolId: record.poolId, patterns: [...patterns.values()],
      ...(this.#retention ? { retention: this.#retention.details(category) } : {}),
      activeHandles, validBytes, potentialCapacityBytes };
  }

  clearMirrorCategories() {
    if (this.#closed) return refused('CLOSED');
    if (this.#busy) return refused('MIRROR_BUSY');
    if (this.#handles.size) return refused('MIRROR_CATEGORIES_BUSY');
    const categoriesCleared = this.#categories.size, patternsCleared = this.#patternsRegistered;
    this.#categories.clear(); this.#patternsRegistered = 0; this.#nextPool = 0;
    this.#retention?.clear();
    for (const home of this.#pools) home.category = null;
    return { accepted: true, categoriesCleared, patternsCleared };
  }

  mirrorStatus(handle) {
    const item = this.#get(handle); if (item.accepted === false) return item;
    return { accepted: true, poolId: item.poolId, category: item.category, pattern: item.pattern, borrowedBlocks: item.borrowedBlocks,
      capacityBytes: item.capacityBytes, armedBytes: item.pages.size * this.#options.blockBytes,
      validBytes: item.validBytes, validLength: this.#prefix(item), actualLength: item.actualLength,
      state: item.actualLength !== null ? 'sealed' : item.validBytes ? 'staging' : 'absent', generation: null };
  }

  statistics() {
    const o = this.#options, readyBytes = this.#closed ? 0 : o.blockBytes * this.#readyBlocks;
    const leasedBlocks = this.#closed ? 0 : this.#readyBlocks - this.#freeBlocks;
    const retention = this.#retention?.statistics() ?? {
      mode: 'fixed', observations: 0, profiles: 0, activeProfiles: 0,
      selectedHorizon: 0, maxObservedHorizon: 0, demandBytes: 0, demandReadyBlocks: 0, evictions: 0, failures: 0,
      maxProfiles: o.maxPatterns, maxHorizon: MIRROR_LIMITS.maxDemandWindow, metadataBytesEstimate: 0,
    };
    let regionBytes = 0, paddingBytes = 0, blanketMetadata = 0;
    for (const blanket of this.#blankets) {
      regionBytes += blanket.bytes.byteLength; blanketMetadata += 160 + blanket.pages.length * 24;
      for (let i = blanket.prefixBlocks; i < blanket.pages.length; i++) if (blanket.pages[i].borrower === null) paddingBytes += o.blockBytes;
    }
    const pools = this.#pools.map((home) => ({ id: home.id, category: home.category,
      capacityBlocks: this.#closed ? 0 : home.capacityBlocks, freeBlocks: home.free.length,
      ownedLeasedBlocks: home.ownedLeasedBlocks, borrowedInBlocks: home.borrowedInBlocks,
      loanedOutBlocks: home.loanedOutBlocks,
      leasedBlocks: home.ownedLeasedBlocks - home.loanedOutBlocks + home.borrowedInBlocks,
      handles: home.handles, homeGrants: home.homeGrants, borrowedGrants: home.borrowedGrants,
      donorScans: home.donorScans, armRefusals: home.armRefusals }));
    return { options: { ...o }, closed: this.#closed, handles: this.#handles.size, logicalBytes: this.#logicalBytes,
      requireCohesion: o.requireCohesion, categoriesRegistered: this.#categories.size, patternsRegistered: this.#patternsRegistered,
      readyBytes, gatherBytes: this.#gather?.byteLength ?? 0, allocatedBytes: readyBytes + (this.#gather?.byteLength ?? 0),
      configuredReadyBytes: o.blockBytes * o.readyBlocks, configuredGatherBytes: o.maxPayloadBytes,
      physicalArrayAllocations: this.#physicalArrayAllocations,
      burstPressure: { enabled: o.burstRetention, snapshots: this.#burstSnapshots, lastReadyBlocks: this.#burstLastReady,
        peakReadyBlocks: this.#burstPeakReady, failures: this.#burstFailures },
      blankets: { enabled: o.blanket, regions: this.#blankets.size, regionBytes, paddingBytes,
        allocations: this.#blanketAllocations, reuses: this.#blanketReuses, directSubmissions: this.#blanketDirect,
        gatherFallbacks: this.#blanketFallbacks, dropped: this.#blanketDropped, metadataBytesEstimate: blanketMetadata },
      retention, demandSamples: this.#retention ? retention.activeProfiles : this.#demands.length,
      recentDemandBytes: this.#retention ? retention.demandBytes : Math.max(0, ...this.#demands),
      pagesGrown: this.#pagesGrown, pagesDropped: this.#pagesDropped,
      gatherGrowths: this.#gatherGrowths, gatherShrinks: this.#gatherShrinks, allocationRefusals: this.#allocationRefusals, trims: this.#trims,
      peakAllocatedBytes: this.#peakAllocatedBytes, peakTransientBytes: this.#peakTransientBytes,
      peakReadyBytes: this.#peakReadyBytes, peakGatherBytes: this.#peakGatherBytes,
      pools, freeBlocks: this.#freeBlocks, leasedBlocks, armedBytes: leasedBlocks * o.blockBytes,
      homeGrants: this.#homeGrants, borrowedGrants: this.#borrowedGrants,
      donorScans: this.#donorScans, armRefusals: this.#armRefusals,
      directSubmissions: this.#directSubmissions, gatherSubmissions: this.#gatherSubmissions,
      pageClearedBytes: this.#pageClearedBytes, gatherClearedBytes: this.#gatherClearedBytes,
      validBytes: this.#validBytes, coverageRanges: this.#coverageRanges,
      warmupMs: this.#warmupMs, writtenBytes: this.#writtenBytes, gatheredBytes: this.#gatheredBytes, clearedBytes: this.#clearedBytes };
  }

  close() {
    if (this.#closed) return { accepted: true };
    if (this.#busy) return refused('MIRROR_BUSY');
    this.resetMirrors(); this.#categories.clear(); this.#patternsRegistered = 0;
    this.#retention?.clear();
    for (const home of this.#pools) { home.free.length = 0; home.category = null; }
    this.#pagesDropped += this.#readyBlocks; this.#readyBlocks = 0;
    this.#freeBlocks = 0; this.#gather = null; this.#submit = null; this.#closed = true;
    return { accepted: true };
  }
}
