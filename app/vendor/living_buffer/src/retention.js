// Discardable reuse-gap metadata. This counter orders accepted observations;
// it is neither a clock nor a generation supplied by the application.
export class RetentionPolicy {
  #profiles = new Map(); #active = new Map(); #maxProfiles; #maxHorizon; #maxReadyBlocks;
  #sequence = 0; #observations = 0; #selected = 0; #maxObserved = 0; #evictions = 0; #failures = 0;

  constructor(maxProfiles, maxHorizon, maxReadyBlocks = 256) { this.#maxProfiles = maxProfiles; this.#maxHorizon = maxHorizon; this.#maxReadyBlocks = maxReadyBlocks; }

  observe(category, pattern, bytes, pageBlocks, gatherBytes, workingSetBlocks = pageBlocks) {
    // Optional cache bookkeeping must not reverse or throw after source admission.
    this.#observations = Math.min(Number.MAX_SAFE_INTEGER, this.#observations + 1);
    try {
      if (this.#sequence >= Number.MAX_SAFE_INTEGER) { this.resetWorking(); this.#sequence = 0; }
      const observation = ++this.#sequence;
      this.#selected = 0;
      if (typeof category === 'string' && typeof pattern === 'string') {
        const key = JSON.stringify([category, pattern, pageBlocks, gatherBytes]);
        let row = this.#profiles.get(key);
        if (row) {
          this.#profiles.delete(key); // refreshed insertion order is bounded LRU.
          if (row.lastObservation !== null) {
            row.lastGap = observation - row.lastObservation;
            row.horizon = Math.min(this.#maxHorizon, row.lastGap);
          }
        } else {
          if (this.#profiles.size >= this.#maxProfiles) {
            const oldest = this.#profiles.keys().next().value;
            this.#profiles.delete(oldest); this.#active.delete(oldest); this.#evictions++;
          }
          row = { category, pattern, pageBlocks, gatherBytes, lastGap: null, horizon: 0,
            lastObservation: null, bytes: 0 };
        }
        row.lastObservation = observation; row.bytes = bytes;
        row.workingSetBlocks = Number.isSafeInteger(workingSetBlocks) && workingSetBlocks >= pageBlocks && workingSetBlocks <= this.#maxReadyBlocks ? workingSetBlocks : pageBlocks;
        this.#profiles.set(key, row); this.#active.set(key, row);
        this.#selected = row.horizon; this.#maxObserved = Math.max(this.#maxObserved, row.horizon);
      }
      // At most maxHorizon+1 distinct observations can still be active.
      for (const [key, row] of this.#active) {
        if (row.lastObservation === null || observation - row.lastObservation > row.horizon) this.#active.delete(key);
      }
    } catch {
      this.#failures++;
      // Derived knowledge may be discarded if its metadata allocation fails.
      this.#profiles.clear(); this.#active.clear(); this.#selected = 0;
    }
  }

  demandBytes() {
    let bytes = 0;
    for (const row of this.#active.values()) bytes = Math.max(bytes, row.bytes);
    return bytes;
  }

  demandReadyBlocks() {
    let blocks = 0;
    for (const row of this.#active.values()) blocks = Math.max(blocks, row.workingSetBlocks);
    return blocks;
  }

  resetWorking() {
    this.#active.clear(); this.#selected = 0;
    for (const row of this.#profiles.values()) row.lastObservation = null;
  }

  clear() {
    this.#profiles.clear(); this.#active.clear(); this.#selected = 0; this.#maxObserved = 0; this.#sequence = 0;
  }

  details(category) {
    const result = [];
    for (const [key, row] of this.#profiles) if (row.category === category) {
      result.push({ pattern: row.pattern, pageBlocks: row.pageBlocks, gatherBytes: row.gatherBytes,
        lastGap: row.lastGap, horizon: row.horizon, active: this.#active.has(key), workingSetBlocks: row.workingSetBlocks });
    }
    return result;
  }

  statistics() {
    let metadataBytesEstimate = 0;
    for (const [key, row] of this.#profiles) metadataBytesEstimate += 328 + 2 * (key.length + row.category.length + row.pattern.length);
    return { mode: 'learned', observations: this.#observations, profiles: this.#profiles.size,
      activeProfiles: this.#active.size, selectedHorizon: this.#selected, maxObservedHorizon: this.#maxObserved,
      demandBytes: this.demandBytes(), demandReadyBlocks: this.demandReadyBlocks(), evictions: this.#evictions, failures: this.#failures,
      maxProfiles: this.#maxProfiles, maxHorizon: this.#maxHorizon, metadataBytesEstimate };
  }
}
