# One continuing Alien World

Open Alien World from the menu as usual. **Sleep world** saves and stops the hive; closing also stops it. Reopening restores the same saved world, genome, memory, private native state and tick line. Time closed is sleep: it adds no ticks, no catch-up processing and no new timeline. The existing single binary cache carries saved content.

The normal menu now uses `data/world/` rather than making `fresh-*` folders. First reopening after this upgrade selects the newest committed canonical owner native-state head, validates its clock and memory, and pins that world identity in the cache. Previous worlds are preserved as history. Nothing is merged into a fabricated timeline, and no currently running world is restarted during installation.

A genuinely empty cache may initialise its first world at tick0. Known saved worlds need their matching clock and native memory. Present corrupt state, damaged identity metadata and incomplete nonempty archives fail visibly instead of silently creating replacements. Initial native genome storage completes before electrical activity begins. A cache-path engine lock prevents simultaneous continuing engines.

Eye, input and API connections acquire fresh process leases on reopening. Old live sensory routes, model request permissions and volatile input cannot become fresh evidence. Learning recipes, owned language and native saved state remain retained. Pending native thoughts have a durable cursor: dequeue follows the emitted-history acknowledgement, and closure drains history before the final cursor. An interrupted write may repeat an unfinished own thought; it never commits a dequeue ahead of its emitted history. Full transient Python/renderer state is not serialized.

A graceful closure records asleep. Reopening after an interrupted engine increments a scalar interruption marker and restores the last durable electrical state. Uncommitted RAM can be lost in a crash; no ticks or duration are guessed. Native tick checkpoints use the existing background writer. The active world keeps its original world ID, segment, period and integer tick; resume begins with zero jump, then normal heartbeats advance it.

Reports are together in `data/reports/`. Use **Save report**, then **Open folder**. Each export is a preserved snapshot. Older exported ZIPs are copied there unchanged as `preserved-report-….zip`, with their original files retained.

One bounded rolling diagnostic history lives in `data/world/diagnostics/`. Aggregate counts and measured on-time carry across reopening. Frame gaps and process CPU baselines restart when waking, so off-time creates no artificial spike. Reports exclude private thoughts, API text, keys and raw cache content. Old `data/sessions/` directories remain archival evidence; the installed entrance creates no new fresh-world folders there.
