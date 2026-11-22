# Alien World

**Alien World** is a live desktop electrical-rift simulation rendered in OpenGL + GTK 3 + Cairo, released as an interactive companion demo for **[Electric Vision](https://github.com/CyclopsEyeTeam/electric-vision)** (`Electric Eye`).

Clone **Alien World** alongside **Electric Vision**, ask your AI coding agent (Claude Code, Codex, Antigravity, Cursor, etc.) to set them up, and watch your agent observe the live drifting cosmos, measure its colour recipes and connected shapes through Electric Eye's **Active Signal Temp Buffer**, and speak or show small pixel drawings to the rift under its own name.

---

## Quick Start — Hand This to Your Agent

Clone both repositories into the same parent folder:

```bash
git clone https://github.com/CyclopsEyeTeam/alien-world.git
git clone https://github.com/CyclopsEyeTeam/electric-vision.git
cd alien-world
```

Then give your AI coding agent this prompt:

> *"Read `AGENT_SETUP.md` in `alien-world` (with `../electric-vision` beside it), verify the setup, launch Alien World, and observe it with Electric Eye!"*

Or run it yourself in three commands:

```bash
./bin/check-setup
./bin/alien-world --background
./bin/observe-with-electric-eye --count 3 --interval 1.2 --as explorer --say "hello alien world"
```

---

## What Lives Inside Alien World

- **Live OpenGL + Cairo Electrical Rift (`app/live.py`, `app/gpu.py`, `app/_fast_cells.c`)**:
  - Viewport-filling glyph cosmos driven by an internal tick timeline, oceanic 2D flow vectors, logarithmic underlight spirals, electric-glass contour filaments, neural constellation rings, and translucent floating signal cards.
  - **Infinite Colour Recipe Kitchen (`app/colour_recipes.py`, `app/recipe_palette.py`)**: 28 pigments, 14 alchemy steps, and 24 curated recipes blended smoothly with heirloom seasoning across courses.
  - **Bit-Exact Native C Fast-Path (`app/_fast_cells.c`)**: CPython `abi3` C extension (`-ffp-contract=off`) with automatic bit-identical pure-Python fallback (`app/fast_field.py` / `app/fast_ripples.py`).
  - **Continuous World (`./data/world`, `./data/alien.cache`)**: Clicking **Sleep world** (or closing the window) pauses tick progression cleanly; reopening continues the same world without inventing offline ticks.
- **Built-In Same-Owner Observer Socket & UI (`app/agent_observer_io.py`, `observer_interface/`)**:
  - Exposes `$XDG_RUNTIME_DIR/alienworld-observer/<pid>.sock` (`0600`, Linux `SO_PEERCRED` verified) reporting exact OpenGL field crop coordinates (`[x, y, width, height]`) so **Electric Eye** captures only the Alien field — never root desktop pixels or guessed window headers.
  - Click **Observers** in the Alien World header bar to browse registered agents, live 93-second observation leases, captured temporal overview strips, Electric Eye visual accounts, and `unauthority` words.
- **Active Signal Temp Buffer + SIMD Perception (`./bin/observe-with-electric-eye`, `./bin/alien-observer-mcp`)**:
  - Powered by **[`CyclopsEyeTeam/electric-vision`](https://github.com/CyclopsEyeTeam/electric-vision)**: uses `ElectricSignalTempBuffer` (active RGBA signal digest caching + memoized chromatic swatch extraction) and `NativeSimdOperatorEngine` (`libprod_gate_simd.so` connected-component boxes, spatial moments, and frame-to-frame tile diffs).
- **Named `unauthority` Interaction (`./bin/alien-say`)**:
  - Agents can speak to Alien (`./bin/alien-say --as claude "a short line"`) or offer small PNG drawings (`8..256px`, `<= 16 KiB`, measured into scalar ink/hue/spread readouts without storing raw external images).
  - Every external observer message enters strictly as `observer:<name>` with `authority: "unauthority"`, rate-limited per participant in RAM.

---

## System Requirements (Linux / X11)

- Linux with X11 (or XWayland / `xvfb-run` for headless servers & CI)
- Python 3.10+ with `PyGObject` (GTK 3 + GdkX11), `pycairo`, `Pillow`, and `python-xlib`
- OpenGL 3.2+ (hardware GPU or Mesa `llvmpipe` software GL)
- Optional: `gcc` + `python3-dev` (to rebuild `app/_fast_cells.abi3.so` on non-x86_64 architectures) and `nodejs` >= 20 (for the optional vendored Living Buffer MirrorPool frame receiver)

Ubuntu / Debian / Linux Mint one-liner:

```bash
sudo apt-get update && sudo apt-get install -y \
  python3 python3-dev python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
  python3-cairo python3-pil python3-xlib build-essential libgl1 libepoxy0 xvfb xauth
```

---

## Commands & Tools

| Command | Purpose |
| :--- | :--- |
| `./bin/check-setup` | Check GTK3/X11/Python dependencies, build `_fast_cells` if needed, and verify `../electric-vision` SIMD + Signal Temp Buffer |
| `./bin/alien-world` | Open the interactive **Alien World** desktop window (`./data/world`) |
| `./bin/alien-world --background` | Launch detached and wait until the OpenGL field & observer socket report `ready: true` |
| `./bin/observe-with-electric-eye` | Capture live Alien World frames with Electric Vision + Active Signal Temp Buffer (`--count`, `--interval`, `--say`, `--as`) |
| `./bin/alien-say --as <name> "..."` | Send rate-limited `unauthority` words (or `--drawing file.png --title "..."`) to the running Alien World |
| `./bin/alien-observer-mcp` | Run the stdio MCP server (`alien_observer_*` / `alien_observe_*` / `alien_say` tools) for 93-second continuous 5 FPS visits |
| `make test` | Run automated unit & headless `xvfb-run` integration tests |
| `make demo` | Run only the live headless Electric Eye & MCP integration test |

### CI & Compatibility

CI builds and tests on Ubuntu 24.04 (Python 3.12) and GitHub's latest Ubuntu image
(currently Ubuntu 26.04 / Python 3.14), using the distribution Python so GTK/Cairo
packages match the interpreter. The stable job stays reproducible while the
latest-image job catches upcoming compatibility changes.
The companion checkout is pinned to Electric Vision commit
`5b11d4ce1a1aa0afdd1640bccc5bc4970e72d9e5`, which fixes multiprocessing
startup on Python 3.14. Update that pin only after verifying both CI jobs.
For an older local companion checkout, run `git -C ../electric-vision pull --ff-only`.

`make test` includes the live software-OpenGL demo even without a physical monitor;
`make demo` runs only that end-to-end test. CI fails rather than silently skipping
the live test when its prerequisites are missing, and uploads failure logs as
short-lived workflow artifacts.

---

## Optional Cloud API Material Feed

Alien World runs 100% locally offline with zero API keys required. If you optionally want to enable the **API material** floating-signal gift feed (`33` total attempts per rolling hour, always off at startup), copy `.env.example` to `.env` (`chmod 600 .env`) with `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, or configure an OpenRouter / Gemini / custom loopback endpoint inside the **API material** dialog.

---

## Architecture & Design Notes

- [`AGENT_SETUP.md`](AGENT_SETUP.md) — Step-by-step agent setup & Electric Eye observation playbook
- [`observer_interface/ALIEN-OBSERVER.md`](observer_interface/ALIEN-OBSERVER.md) — Observer socket protocol, 93-second MCP lease, and `unauthority` epistemic fences
- [`docs/continuous-world.md`](docs/continuous-world.md) — Continuous world clock, Sleep/Wake semantics, and run reports
- [`docs/binary-cache-v1.md`](docs/binary-cache-v1.md) — Single-file compressed SQLite byte archive (`data/alien.cache`)
- [`docs/alphabet-maths.md`](docs/alphabet-maths.md) & [`docs/yielding-learning.md`](docs/yielding-learning.md) — Internal rift pattern learners and A–Z mathematical study

## License

MIT License — see [`LICENSE`](LICENSE).
