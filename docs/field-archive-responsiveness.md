# Field and archive responsiveness

This follows the packed receiving release without changing its Living Buffer, native geometry, layers, cadence, colours, clocks or continued-world storage.

## What changed

Committed cache queries no longer hold the actor's producer/acknowledgement condition. A delayed disk read can still delay its own synchronous caller, but cannot hold unrelated producers or the writer's ACK bookkeeping behind that condition. Head dedup rechecks concurrent mutations; ordered record reads retry if acceptance or durability changes across the SQL snapshot. Private proposals remain invisible through the real COMMIT/before-ACK boundary. This does not remove SQLite's own locks, bypass backpressure or acknowledge uncommitted bytes.

The field prepares native `sample_xy` mappings once per axis per frame, using unchanged arithmetic and native clipping. Every frame rebuilds the maps for current scale and dimensions. Glyphs, RGB, void, overlays, ripple order and native metrics are retained exactly.

Worker profiles add cache reads, progression, language, tick checkpoints, art lookup and field preparation. The scalar-only report distinguishes worker archive health from window archive health, including committed-read failure/busy counts and last base SQLite code. Learning checkpoint failures distinguish capacity/closing, storage I/O and invalid state. These are process diagnostics, never hive clock/meaning/authority and never private content.

## Evidence and limits

Deterministic slow-storage gates reproduced queue/ACK blocking in get, head, set and records. Their regressions include same-head mutation through a real ACK, a limited ordered read racing a newer committed record, and a hidden proposal held after real COMMIT until ACK. Independent review found and repaired the ordered-read race before promotion.

Matched complete-frame CPU fell 4.6–14.5% across six scenes (80x24,140x37,240x64; scale1,.88,1.13,2.4; plain/dream/effects), including every unchanged layer and metric. This is a calculation benchmark, not whole-application or long-run CPU evidence.

The owner's report established a 4.9-second event-dispatch wait, three dispatch exceptions and four failed archive operations, but not their exact causes. The worker log additionally recorded shutdown archive-drain timeouts. The repaired shared-lock propagation is reproduced independently; it is not proof that every historical wait/error is eliminated. The new report stages and separate writer health are intended to identify any recurrence precisely. Preserve original reports and failed validation evidence.

Installation creates a new immutable release selected for the next reopening. Existing worlds, binary cache, history, keys/quota, original Alien and previous releases are preserved. Closing still adds no offline ticks. No real provider request is required for qualification.

## Concurrent accepted update

The written Alphabet maths release32e5087 was selected while this work was being qualified. Preserve its exact accepted modules/UI/docs and integrate the performance work on top. The first field/archive release remains preserved as a qualified candidate; the combined native-field-archive-v2 is the intended next-opening release. Requalify all459 unit tests, the17 native alphabet checks and the two installed GPU/Eye/sleep/reopen checks. No active world is restarted.
