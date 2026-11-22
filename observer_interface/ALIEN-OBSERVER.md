# Alien Observer Interface & Electric Vision Bridge

`observer_interface/` connects a live **Alien World** desktop window (`app/live.py`) to **Electric Vision** (`https://github.com/CyclopsEyeTeam/electric-vision`) without granting external semantic authority or touching private root/desktop pixels.

## Design Invariants

1. **Exact Verified Client Crop (`AF_UNIX` `SOCK_SEQPACKET`)**:
   - When Alien World renders its first OpenGL frame, `app/agent_observer_io.py` binds `$XDG_RUNTIME_DIR/alienworld-observer/<pid>.sock` (`0600`, same-UID `SO_PEERCRED`).
   - It reports exact GTK client dimensions and the physical OpenGL field crop (`crop: [x, y, width, height]`) so Electric Eye never guesses window borders or header heights, and never reads root-window desktop pixels.
2. **Active Signal Temp Buffer + Native SIMD Geometry**:
   - `FieldObserver` (`alien_observer.py`) pairs `ElectricVisionAgentSession(allow_alien_field=True)` with `ElectricSignalTempBuffer` (`signal_buffer.py`) and `NativeSimdOperatorEngine` (`libprod_gate_simd.so`).
   - Unchanged frames hit the in-memory signal digest cache without repeating live mark translation; changed frames compute 16-colour trace geometry, 4-connected component bounding boxes (`*-shapes.png`), frame-to-frame pixel/tile deltas, and dominant chromatic swatches from Alien's Infinite Colour recipes.
3. **Strict `unauthority` Epistemic Fence**:
   - Observer descriptions (`alien_observe_note`) stay in `./data/observations/observers.sqlite3` (viewable in the **Observers** window) and are never injected into Alien as truth.
   - Explicit words (`alien_say` / `./bin/alien-say --as <name>`) and small PNG drawings (`8..256px`, `<= 16 KiB`, reduced to scalar ink/hue/spread readouts) enter Alien's bounded input queue solely as `observer:<name>` with `authority: "unauthority"`, rate-limited per participant in RAM.
4. **93-Second Receipt-Triggered Lease (`alien-observer-mcp`)**:
   - Opening an MCP connection starts no capture or timer.
   - Only `alien_observe_confirm` (matching the delivered initial PNG's SHA-256 and receipt) starts the bounded 93-second 5 FPS `ContinuousVision` stream.
