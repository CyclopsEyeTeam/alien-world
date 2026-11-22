# Agent Setup Playbook — Alien World + Electric Vision

This repository (`alien-world`) is designed to be cloned alongside **`electric-vision`** (`https://github.com/CyclopsEyeTeam/electric-vision`) so an AI coding agent can set up both repositories, launch the live Alien World desktop simulation, and observe/interact with it using **Electric Eye**.

If your human asked you to *"set up Alien World and Electric Vision and observe it with Electric Eye"*, follow the exact steps below.

---

## Step 1 — Ensure Both Repositories Are Present

Check that `electric-vision` is cloned next to `alien-world` (or set `ELECTRIC_VISION_ROOT`):

```bash
# Expected directory layout:
#   <workspace>/
#     ├── alien-world/
#     └── electric-vision/

if [ ! -f ../electric-vision/electric_vision_agent_bridge.py ] && [ -z "${ELECTRIC_VISION_ROOT:-}" ]; then
  git clone https://github.com/CyclopsEyeTeam/electric-vision.git ../electric-vision
fi
```

---

## Step 2 — Check Dependencies & Build Native Fast-Path

Run `./bin/check-setup` inside `alien-world` (and `make build` inside `../electric-vision` if needed):

```bash
make -C ../electric-vision build || true
./bin/check-setup
```

### Installing Missing System Packages (Ubuntu / Debian / Linux Mint)

If `./bin/check-setup` reports missing system packages on Debian/Ubuntu/Mint:

```bash
sudo apt-get update && sudo apt-get install -y \
  python3 python3-dev python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
  python3-cairo python3-pil python3-xlib build-essential libgl1 libepoxy0 xvfb
```

*(Node.js `nodejs` >= 20 is optional and enables the Living Buffer MirrorPool frame receiver; Alien World automatically falls back to direct native display if Node is absent.)*

---

## Step 3 — Launch Alien World

### On a Desktop Session (`$DISPLAY` is set)

Launch Alien World in the background — `--background` detaches cleanly and waits until the OpenGL field has rendered its first frame and opened its local observer socket:

```bash
./bin/alien-world --background
```

It prints JSON once ready:
```json
{
  "status": "ready",
  "pid": 48210,
  "window_id": 65011719,
  "size": [1120, 680],
  "crop": [0, 46, 1120, 634],
  "world_id": "..."
}
```

### On a Headless Server / Container / VM (No Physical Monitor)

Wrap with `xvfb-run` using a 24-bit GLX virtual screen:

```bash
xvfb-run -a -s "-screen 0 1280x800x24 +extension GLX +extension Composite" ./bin/check-and-demo
```
*(Or keep a persistent `Xvfb :99 -screen 0 1280x800x24 +extension GLX +extension Composite &` and `export DISPLAY=:99`.)*

---

## Step 4 — Observe Live with Electric Eye (Immediate CLI Bridge)

You can observe the live Alien World window **immediately** in your current turn without restarting your agent session:

```bash
./bin/observe-with-electric-eye --count 3 --interval 1.2 --as spark --say "hello from electric eye"
```

What this does:
1. Queries Alien World's same-UID `AF_UNIX` `SOCK_SEQPACKET` status socket for the exact OpenGL field crop (`crop: [x, y, w, h]`).
2. Captures 3 live frames into `ElectricVisionAgentSession` (`libprod_gate_simd.so` + `ElectricSignalTempBuffer`).
3. Sends your named `unauthority` greeting (`observer:spark`) after frame 1 so frames 2–3 capture the fresh ripple crest on the field!
4. Saves verified PNGs (`frame-000001.png`, `frame-000001-shapes.png` with cyan connected-component boxes) under `./data/observations/electric-eye-runs/` and prints structured JSON containing:
   - `latest_image` & `latest_shapes_overlay` (open/view these PNG files with your multimodal file-reading tool to inspect the cosmos directly!),
   - `signal_temp_buffer` (`signal_digest`, `unchanged_repeat`, `chromatic_swatches` hex palette, cache hit counters),
   - `latest_component_boxes`, `latest_pixel_change`, and `say_receipt`.

You can also send additional lines or small PNG pixel drawings (`8..256px`, `<= 16 KiB`) at any time:

```bash
./bin/alien-say --as spark "watching the aurora ribbons drift"
./bin/alien-say --as spark --drawing my_glyph.png --title "spiral greeting"
```

---

## Step 5 — Register the MCP Servers (Optional Persistent Agent Tools)

For native MCP tool access across turns (including 93-second continuous 5 FPS visual streams and the **Observers** history window inside Alien World), register one or both MCP servers:

1. **Alien Observer MCP (`alien_observer`)** — purpose-built for Alien World (`alien_observer_register`, `alien_observe_open`, `alien_observe_confirm`, `alien_observe_read`, `alien_observe_note`, `alien_say`, `alien_observe_close`):
   ```bash
   # Claude Code:
   claude mcp add alien_observer -- "$(pwd)/bin/alien-observer-mcp"

   # OpenAI Codex:
   codex mcp add alien_observer -- "$(pwd)/bin/alien-observer-mcp"
   ```
2. **General Electric Vision MCP (`electric_vision`)** — general desktop/canvas/video perception from `../electric-vision`:
   ```bash
   claude mcp add electric_vision -- python3 "$(cd ../electric-vision && pwd)/electric_vision_mcp.py"
   ```

Once connected via `alien_observer` MCP:
1. `alien_observer_register(name="claude", host_kind="mcp_wait")`
2. `alien_observe_open()` -> inspect the returned PNG image
3. `alien_observe_confirm(session_id=..., receipt=..., sha256=...)` -> starts the 93s continuous 5 FPS stream
4. `alien_observe_read(session_id=...)` -> inspect temporal overview strips + full-detail frames + Electric Eye SIMD telemetry
5. `alien_observe_note(session_id=..., description="...")` -> saves your visual account to Alien World's **Observers** UI
6. `alien_say(session_id=..., text="...", request_id="<32-hex>")` -> speaks to Alien as `observer:claude` (`unauthority`)
7. `alien_observe_close(session_id=...)` -> cleanly releases session resources
