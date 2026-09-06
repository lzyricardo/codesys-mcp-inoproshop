# codesys-mcp-inoproshop

MCP server that drives **InoProShop** (Inovance / 汇川) — the CODESYS-based IDE — from an AI assistant. Exposes the InoProShop scripting API as 40+ tools and 3 resources, keeping **one single InoProShop window open across every tool call** via a file-based IPC watcher.

This is an improved fork of [`codesys-mcp-persistent`](https://github.com/luke-harriman/Codesys-MCP) (luke-harriman), adapted for InoProShop and hardened against the **"every call opens a new window"** defect that the original LIMIT `InoProShop_LIMIT_MCP` bundle suffered from.

## What changed vs. the original LIMIT bundle

The LIMIT bundle spawned a fresh `InoProShop.exe --runscript=…` **on every tool call** and killed it after each result — so the IDE popped a new window (and re-loaded the project) on every single request. This fork keeps a **single persistent InoProShop instance**:

- One `InoProShop.exe` is launched (detached, no shell) and a watcher script runs **inside** it.
- The watcher starts a background thread, then **returns** — freeing the IDE UI thread so you can keep using InoProShop alongside the AI.
- Every tool call is marshaled onto the IDE's primary thread via `se.system.execute_on_primary_thread()` and the result is written to a `results/` file; Node polls it.
- On an MCP-server restart, the launcher **adopts the already-running InoProShop session** (matched by profile + live PID + `ready.signal`) instead of spawning a second window.

Verified end-to-end on **InoProShop V1.9.1.6** (see `test/integration-launch.ts`): cold launch → 3 sequential tool calls → all reuse the same PID, exactly **one** `InoProShop.exe`; a simulated reconnect adopts the session in ~0.008s with still only one process.

## Requirements

- Windows
- Node.js 18+ (tested on 22.x)
- InoProShop **V1.9.1.6** (verified) or **V1.10.0.3** (see caveat below), installed with the matching profile registered.

> ⚠️ **V1.10.0.3 compatibility is NOT verified.** The persistent model relies on `se.system.execute_on_primary_thread()`, which upstream CODESYS removed in V3.5 SP21+. InoProShop V1.10.0.3 may or may not still expose it. If V1.10.0.3 reports `Marshal error: … execute_on_primary_thread … no longer supported`, run with `--mode headless` (each call spawns `--noUI`; no window, but no single-instance reuse either). Please report back what V1.10.0.3 actually does so this can be confirmed.

## Install / build

```bash
git clone <your-repo-url>
cd codesys-mcp-inoproshop
npm install
npm run build          # tsc + copy src/scripts -> dist/scripts
```

The entry point is `dist/bin.js`.

## Configure (WorkBuddy `mcp.json`)

```json
{
  "mcpServers": {
    "inoproshop": {
      "command": "node",
      "args": [
        "D:\\codesys-mcp-inoproshop\\dist\\bin.js",
        "--codesys-path", "D:\\Inovance Control\\CODESYS\\Common\\InoProShop.exe",
        "--codesys-profile", "InoProShop(V1.9.1.6)",
        "--workspace", "D:\\your-projects"
      ],
      "timeout": 900
    }
  }
}
```

If your InoProShop lives at the newer `D:\Inovance Control\InoProShop\CODESYS\Common\InoProShop.exe` layout, change `--codesys-path` accordingly — both paths exist as V1.9.1.6.

Claude Code / `.mcp.json`:

```json
{
  "mcpServers": {
    "inoproshop": {
      "command": "node",
      "args": [
        "D:\\codesys-mcp-inoproshop\\dist\\bin.js",
        "--codesys-path", "D:\\Inovance Control\\CODESYS\\Common\\InoProShop.exe",
        "--codesys-profile", "InoProShop(V1.9.1.6)"
      ]
    }
  }
}
```

## CLI

| Flag | Description | Default |
|---|---|---|
| `-p, --codesys-path <path>` | Path to `InoProShop.exe` | `D:\Inovance Control\CODESYS\Common\InoProShop.exe` |
| `-f, --codesys-profile <name>` | InoProShop profile name | `InoProShop(V1.9.1.6)` |
| `-w, --workspace <dir>` | Workspace for relative project paths | cwd |
| `-m, --mode <mode>` | `persistent` or `headless` | `persistent` |
| `--no-auto-launch` | Don't launch InoProShop on startup | auto-launch on |
| `--fallback-headless` | Fall back to headless if persistent launch fails | `true` |
| `--keep-alive` | Keep InoProShop running after server stops | `false` |
| `--kill-existing-inoproshop` | Kill any running `InoProShop.exe` before launching (dev only) | `false` |
| `--timeout <ms>` | Default per-command IPC timeout | `900000` (15 min; upstream was 60000) |
| `--ready-timeout <ms>` | InoProShop startup ready-signal deadline | `180000` (upstream was 60000) |
| `--detect` | Scan installed InoProShop locations and exit | - |
| `--verbose` / `--debug` | Logging | - |

Environment variables:

- `CODESYS_PATH`, `CODESYS_PROFILE` — defaults for the corresponding flags (legacy names retained for compatibility)
- `INOPROSHOP_MCP_READY_TIMEOUT_MS` — ready-signal deadline (overrides `--ready-timeout`; `CODESYS_MCP_READY_TIMEOUT_MS` also honored)
- `INOPROSHOP_MCP_PROFILE` — **internal**: set by the launcher on the spawned InoProShop so a later MCP restart can re-adopt this exact session. Do not set manually.

## Tools

Management: `launch_codesys`, `shutdown_codesys`, `get_codesys_status`, `eval_python`.

Project: `open_project`, `create_project`, `list_project_templates`, `save_project`, `compile_project`, `get_compile_messages`, `create_pou`, `set_pou_code`, `create_property`, `create_method`, `create_dut`, `create_gvl`, `create_folder`, `delete_object`, `rename_object`, `get_all_pou_code`, `search_code`, `find_references`, `rename_symbol`.

Online / runtime: `connect_to_device`, `disconnect_from_device`, `set_credentials`, `set_simulation_mode`, `get_application_state`, `read_variable`, `write_variable`, `download_to_device`, `start_stop_application`, `monitor_variables`.

Library: `list_project_libraries`, `add_library`.

Device tree: `list_device_repository`, `inspect_device_node`, `add_device`, `set_device_parameter`, `map_io_channel`.

Archiving: `create_project_archive`.

Resources: `inoproshop://project/status`, `inoproshop://project/{path}/structure`, `inoproshop://project/{path}/pou/{pou}/code`.

## Execution modes

**Persistent (default).** On startup the launcher scans `%TEMP%/inoproshop-mcp-persistent/` for a live session (profile match, PID alive, `ready.signal` present) and adopts it; otherwise it spawns `InoProShop.exe --runscript=watcher.py` (no `--noUI`). The watcher writes `ready.signal`, then runs a background thread polling a `commands/` directory. Results land in `results/`; Node polls with exponential backoff. The IDE stays interactive between calls.

**Headless.** Each tool call spawns a new `--noUI` InoProShop process, runs the script, and exits. No UI, no single-instance reuse. Used for `--mode headless`, or as a fallback when persistent launch fails.

## Detect installations

```bash
node dist/bin.js --detect
```

Scans the common InoProShop install layouts (both `…\Inovance Control\CODESYS\Common\` and `…\Inovance Control\InoProShop\CODESYS\Common\`) and prints the version of any found executable.

## Troubleshooting

- **InoProShop not found** — run `--detect`, or pass an explicit `--codesys-path`.
- **Watcher timeout at startup** — cold first launch can take >60s; `--ready-timeout 180000` is already the default. Bump further with `INOPROSHOP_MCP_READY_TIMEOUT_MS=300000` if your machine is slow. If InoProShop is still booting, just call `launch_codesys` again — the launcher re-attaches to the live PID rather than spawning a second instance.
- **Command timeout** — default is now 900000ms (15 min). `compile_project`, `get_all_pou_code`, `download_to_device` use 120s internally. Increase with `--timeout <ms>`.
- **Project file locked across MCP restarts** — the launcher adopts the prior session automatically. If you still hit a lock, kill the orphan `InoProShop.exe` via Task Manager or pass `--kill-existing-inoproshop` next launch (off by default to protect any InoProShop you're using manually).
- **`Marshal error: … execute_on_primary_thread … no longer supported`** — you're on an InoProShop build that dropped the API. Restart with `--mode headless`.

## Development

```bash
npm install
npm run build
npm test                 # vitest unit tests
npx tsx test/integration-launch.ts   # real InoProShop launch + reuse + adopt test
npm run typecheck
```

Project layout:

```
src/
  bin.ts              CLI entry point (InoProShop defaults, --detect)
  server.ts           MCP tool / resource registration
  launcher.ts         InoProShop process lifecycle + session adoption
  ipc.ts              File-based IPC transport (commands/ + results/)
  headless.ts         Headless fallback executor (--noUI)
  script-manager.ts   IronPython 2.7 template loading + interpolation
  executor-proxy.ts   Race-free executor swap during background auto-launch
  result-parser.ts    RESULT_JSON marker extraction
  scripts/            IronPython 2.7 watcher + helpers + tool scripts
test/
  integration-launch.ts   Real InoProShop single-instance validation
```

## Attribution & license

Forked from [`codesys-mcp-persistent`](https://github.com/luke-harriman/Codesys-MCP) (MIT, luke-harriman). InoProShop-specific defaults, the single-instance hardening, and longer timeouts added here. Distributed under the same MIT license.
