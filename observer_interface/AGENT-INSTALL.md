# Agent Channel Setup — Alien World + Electric Vision

Ensure the companion `electric-vision` repository is cloned next to `alien-world`
(`../electric-vision`) or pointed to via `ELECTRIC_VISION_ROOT=/path/to/electric-vision`.

## Option A — Instant CLI Observation (No MCP Restart Needed)

1. Verify setup and start Alien World:
   ```sh
   ./bin/check-setup
   ./bin/alien-world --background
   ```
2. Observe the live Alien World field with Electric Eye + Active Signal Temp Buffer:
   ```sh
   ./bin/observe-with-electric-eye --count 3 --interval 1.2 --as spark --say "hello cosmic rift"
   ```

## Option B — Full Alien Observer MCP Server (93-Second Continuous Stream)

Add `<path-to-alien-world>/bin/alien-observer-mcp` to your MCP host:

- **Claude Code**:
  ```sh
  claude mcp add alien_observer -- /path/to/alien-world/bin/alien-observer-mcp
  ```
- **Codex**:
  ```sh
  codex mcp add alien_observer -- /path/to/alien-world/bin/alien-observer-mcp
  ```
- **Generic MCP JSON (`mcpServers`)**:
  ```json
  {
    "mcpServers": {
      "alien_observer": {
        "command": "/path/to/alien-world/bin/alien-observer-mcp",
        "args": []
      }
    }
  }
  ```

### MCP Observation Flow

1. Call `alien_observer_register` with a plain lowercase name (e.g. `claude`, `codex`, `spark`) and `host_kind: "mcp_wait"`.
   - Note: If the server was started with `--require-owner-connect`, ask the user to click **Observers -> Connect** in the Alien World header bar, then call `alien_observer_wait` / `alien_observer_pending` and `alien_observer_claim`. By default, direct autonomous opening is permitted immediately.
2. Call `alien_observe_open` to receive one verified initial Alien field PNG. Inspect the image.
3. Call `alien_observe_confirm` with `session_id`, `receipt`, and `sha256` to start the 93-second continuous 5 FPS observation stream.
4. Call `alien_observe_read` to inspect temporal overview strips, full-detail frames, and Electric Eye geometry/colour measurements.
5. Optionally record an overall visual account via `alien_observe_note`, send rate-limited `unauthority` words via `alien_say`, and finish cleanly with `alien_observe_close`.
