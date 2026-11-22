# Long-run diagnostic reports

Yielding-learning releases also include a **Mathematical yield** summary from the latest retained learning sample. It separates provisional working patterns from durably published establishments/revisions. Only scalar counts and predictive skill are included; conclusions, feature measurements and source names are excluded. These are internal mathematical observations, not evidence of semantic truth or general intelligence.

Use **Save run report** while Alien World is running or after Stop. It writes a new local report folder and `report.zip` beside that session's reports. The ZIP contains only `report.md`, `report.json` and `sanitized.jsonl`. Send the ZIP when asking for investigation; application logs, the binary content cache and credential files are unnecessary.

The recorder is separate from the hive, native tick timeline and content archive. Its host monotonic elapsed time measures observed delays; it grants no source authority or semantic truth. Frame receive callbacks and actual renderer callbacks update bounded RAM aggregates. Renderer callbacks can draw the same sequence again, so they are not vblank or unique-frame FPS. Sequence gaps count missing values between observed incoming frames; they do not establish whether transport, engine pacing or intentional coalescing caused them.

Once a second, the existing refresh hook samples allowlisted receiving, intake, archive and queue counters. It reads only `/proc/<pid>/stat` for explicitly supplied GUI, worker, Living Buffer helper, preparer, Eye and API process roles. It does not scan a process tree, environment, command line or unrelated processes. Missing roles and first CPU samples are unknown. CPU uses 100% for one core. Per-process RSS can include shared pages; adding it does not measure unique physical RAM. Duplicate role PIDs are marked. Reports cover this observed PID subset rather than claiming whole-application usage.

Each diagnostic run has an owner-only directory, a queue of at most 64 scalar records, four rotating JSONL files of at most 2 MiB each, and a separate bounded summary. Callbacks never write to disk or perform model calls. The writer preserves whole-run counts, sums, minima, exact observed maxima and fixed-bin histograms independently of the retained log window. The final histogram bin is overflow; histogram ranges are not percentiles. It checkpoints the summary after periodic samples and finalizes it after a drained Stop. Queue pressure or an oversized record drops that record and increments a count; aggregate updates remain in RAM. A crash can lose aggregates since the latest summary checkpoint. Writer failure or a two-second close timeout does not stop the application, and incomplete coverage remains visible.

Only fixed field names, bounded finite numbers, booleans and fixed status/API enums are accepted. Metadata permits the known release name, a hexadecimal library revision and fixed scope. The recorder excludes keys, prompts, API replies, private thoughts, monologue, glyphs, colours, cache contents, arbitrary error strings, process IDs and owner paths. Structural category/pattern strings are also excluded. The offline analyser applies the allowlist again even to hostile or malformed input. It reads only the fixed diagnostic file names, refuses file symlinks and limits individual lines, total input bytes and record counts. It never copies raw input files into the ZIP.

API dispatch, reply and admission are separate counted events. API-adjacent frame/draw gaps are intervals ending within five seconds after an observed admission. They show correlation, not causality. They do not prove provider completion, language readiness, learning, or model perception. The report separates the retained record interval from whole-run aggregate coverage and flags rotation, queue drops, malformed input, truncated tails, absent stop records and active/incomplete summaries. An export during a run is a bounded best-effort view rather than an atomic snapshot of all rotating files. Reports are unsigned observations.

For offline use from this release's `app` directory:

```sh
python3 analyse_run.py --sessions /path/to/data/sessions
python3 analyse_run.py --sessions /path/to/data/sessions --latest --output /path/to/report-output
python3 analyse_run.py --session /path/to/fresh-session --output /path/to/report-output
```

The first command lists diagnostic runs. `--session` accepts a worker session, its diagnostics folder, or an individual diagnostic run. Every export creates a new folder and preserves previous reports and source data. A failed export is nonfatal and leaves the application running. The files are bounded receiving/render diagnostics; they are not a recording of Alien's internal experience or a reconstruction of unobserved time.

## Continuing-world storage

The continuous-world release uses `data/world/diagnostics/` for one bounded history, with cumulative measured on-time and counters across opens. The existing **Save report** button writes snapshots under `data/reports/`. Offline export accepts `--session ./data/world --output ./data/reports`. Older session-based examples remain valid for preserved archives.

Packed-receiving reports additionally retain the latest worker, presentation and receiver profiles with current-process tokens and observed elapsed denominators. Their named CPU/wall spans are inclusive and can overlap; they must not be summed as disjoint process CPU. Old reports without these fields remain valid. Packed/staging counters and learning pause reasons help compare receiving allocations and deliberate deferral with actual computation cost.
