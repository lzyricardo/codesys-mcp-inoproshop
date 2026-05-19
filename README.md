# codesys-mcp-persistent

MCP server for CODESYS with a persistent UI instance and file-based IPC.

Unlike headless-only approaches that spawn a new CODESYS process per command, this server launches CODESYS **with its UI visible** and keeps it running. MCP tool calls are sent to the same instance via a file-based IPC watcher, so changes appear in real-time and the user can interact with the IDE alongside AI-driven automation.

## Features

- **Persistent mode** - CODESYS UI stays open. Commands execute in the running instance
- **Headless fallback** - automatic fallback to `--noUI` spawn-per-command if persistent mode fails
- **File-based IPC** - atomic file writes (`.NET System.IO.File.Replace` on NTFS) + a watcher running inside CODESYS via `--runscript`
- **Command serialization** - async mutex ensures one command at a time
- **Session adoption** - on launch, scans for and re-attaches to a live CODESYS+watcher left by a previous MCP server (no duplicate spawn, no project-lock contention on `/mcp` reconnect)
- **Health monitoring** - detects CODESYS crashes and reports state
- **41 MCP tools** - project management + templates, POU authoring, structured compiler diagnostics, runtime monitoring, simulation, library management, code search, refactor, device tree, fieldbus I/O mapping, archiving, plus a `[DEV]` raw-ScriptEngine evaluator
- **Drop-in replacement** - same MCP tool names and parameters as `@codesys/mcp-toolkit` (the original toolkit's surface is a strict subset)

## Installation

```bash
npm install -g codesys-mcp-persistent
```

Or install from the repository:

```bash
git clone https://github.com/luke-harriman/Codesys-MCP.git
cd Codesys-MCP
npm install
npm run build
npm link
```

**Requirements:** Node.js 18+, Windows, CODESYS 3.5 SP19 or SP20 installed for full persistent-mode support. **SP21+ note:** CODESYS removed the scripting API the persistent watcher uses to marshal work onto the UI thread (`system.execute_on_primary_thread`), so on SP21 Patch 5 and SP22 Patch 1 (and possibly earlier SP21 patches) persistent mode fails with "Marshal error: ... no longer supported" on every tool call. Until the watcher rewrite ships, run SP21+ with `--mode headless` (works identically to the upstream `@codesys/mcp-toolkit`, just slower). See [Known limitations](#known-limitations) for details.

## Quick Start

Add to your `.mcp.json` (Claude Code configuration):

```json
{
  "mcpServers": {
    "codesys": {
      "command": "codesys-mcp-persistent",
      "args": [
        "--codesys-path", "C:\\Program Files\\CODESYS 3.5.21.0\\CODESYS\\Common\\CODESYS.exe",
        "--codesys-profile", "CODESYS V3.5 SP21 Patch 3",
        "--mode", "persistent"
      ]
    }
  }
}
```

Or run directly:

```bash
codesys-mcp-persistent \
  --codesys-path "C:\Program Files\CODESYS 3.5.21.0\CODESYS\Common\CODESYS.exe" \
  --codesys-profile "CODESYS V3.5 SP21 Patch 3"
```

## CLI Reference

| Flag | Description | Default |
|------|-------------|---------|
| `-p, --codesys-path <path>` | Path to CODESYS executable | `$CODESYS_PATH` or auto-detected |
| `-f, --codesys-profile <name>` | CODESYS profile name | `$CODESYS_PROFILE` or `CODESYS V3.5 SP21` |
| `-w, --workspace <dir>` | Workspace directory for relative paths | Current directory |
| `-m, --mode <mode>` | `persistent` (UI) or `headless` (--noUI) | `persistent` |
| `--no-auto-launch` | Don't launch CODESYS on startup | Auto-launch enabled |
| `--fallback-headless` | Fall back to headless if persistent fails | `true` |
| `--keep-alive` | Keep CODESYS running after server stops | `false` |
| `--kill-existing-codesys` | Kill any running `CODESYS.exe` before launching (dev convenience. Off by default to protect external IDE sessions) | `false` |
| `--timeout <ms>` | Default command timeout | `60000` |
| `--detect` | List installed CODESYS versions and exit | - |
| `--verbose` | Enable verbose logging | - |
| `--debug` | Enable debug logging | - |
| `-V, --version` | Show version number | - |
| `-h, --help` | Show help | - |

Environment variables:
- `CODESYS_PATH`, `CODESYS_PROFILE` - defaults for the corresponding flags
- `CODESYS_MCP_READY_TIMEOUT_MS` - override the watcher-ready timeout (default `180000`). Cold first launches of older SPs (SP16 P5 observed at ~120s) routinely exceed the 60s used in earlier versions, so the default is now 3 minutes. Bump it further on slow hardware

## MCP Tools

### Management Tools

| Tool | Description |
|------|-------------|
| `launch_codesys` | Manually launch CODESYS (use with `--no-auto-launch`). Will adopt a live session if one already exists |
| `shutdown_codesys` | Shut down the persistent CODESYS instance |
| `get_codesys_status` | Get current state, PID, execution mode |
| `eval_python` | **[DEV]** Execute arbitrary IronPython 2.7 against the live `scriptengine`. Code must print `SCRIPT_SUCCESS` before `sys.exit(0)`. Intended for ScriptEngine API audits, not routine use. Never invoke the IDE's `Login` command from here - it hangs the primary thread |

### Project Tools

| Tool | Description |
|------|-------------|
| `open_project` | Open an existing CODESYS project file |
| `create_project` | Create a new project. Defaults to the bundled `Standard.project`; pass `templatePath` to copy a specific `.project` file, or `templateName` to instantiate a template registered with CODESYS's Template Manager (e.g. an installed ifm AE3100 template). Use `list_project_templates` to discover valid values |
| `list_project_templates` | Enumerate available project templates. Combines (1) templates registered via CODESYS's Template Manager (what `File > New Project > Standard Project from Template` shows) and (2) a filesystem scan of well-known `%ProgramData%/CODESYS` locations. Returns `{name, path, source}` per template |
| `save_project` | Save the currently open project |
| `compile_project` | Build the primary application with structured error output (120s timeout) |
| `get_compile_messages` | Retrieve last compiler messages without triggering a new build |

### POU / Code Authoring Tools

| Tool | Description |
|------|-------------|
| `create_pou` | Create a Program, Function Block, or Function |
| `set_pou_code` | Set declaration and/or implementation code. Also accepts Method and Property paths (e.g. `Application/MyFB/MethodName`) |
| `create_property` | Create a property within a Function Block |
| `create_method` | Create a method within a Function Block |
| `create_dut` | Create a Data Unit Type (Structure, Enumeration, Union, Alias) |
| `create_gvl` | Create a Global Variable List with optional initial declaration |
| `create_folder` | Create an organizational folder in the project tree |
| `delete_object` | Delete a user-created project object (POU, DUT, GVL, folder, etc.). Refuses system nodes (`Application`, `Device`, `Plc Logic`, `Library Manager`, `Task Configuration`, `MainTask`, `Communication`, `Ethernet`, `Project Settings`, etc.) and any top-level path |
| `rename_object` | Rename any project object |
| `get_all_pou_code` | Bulk read all declaration and implementation code in the project (120s timeout) |
| `search_code` | Regex (or literal substring) search across every POU/Method/Property/DUT/GVL body. Returns `{path, section, line, col, text}` hits |
| `find_references` | Word-boundary search for a symbol name across the project. Wraps `search_code` with `\bsymbol\b` |
| `rename_symbol` | Best-effort textual rename across all POU bodies. Two-phase write (plan + apply). Refuses IEC keywords - `dryRun=true` by default |

### Online / Runtime Tools

| Tool | Description |
|------|-------------|
| `connect_to_device` | Login to the PLC runtime. Optionally pass `ipAddress` (and `gatewayName`, default `Gateway-1`); the device address is set then auto-resolved from IP-encoded form to the gateway-scan node form (V3 login routes by node, not IP) before login. Works against real PLCs from a pure IPC-driven script via the `with_executor` / `ExecuteSource` frame in `ensure_online_connection` |
| `disconnect_from_device` | Logout from the PLC runtime. No-op (returns success) if not connected |
| `set_credentials` | Set default `username`/`password` for subsequent logins. Username must be non-empty. For no-auth runtimes simply do not call this tool |
| `set_simulation_mode` | Toggle device-level simulation mode on/off. Run before `connect_to_device` when no physical PLC is available |
| `get_application_state` | Report the running PLC application state (run / stop / exception) plus login status |
| `read_variable` | Read a live variable. Path format: `GVL_Name.varname` or `PRG_Name.varname` (no `Application.` prefix). Struct members: `GVL.stFrame.aRoi[0].iValueMm` |
| `write_variable` | Write a variable via V3's `set_prepared_value` + `force_prepared_values`. The variable is FORCED at the new value until unforced (or runtime restart). Use for control flags / test injection, not program-output variables |
| `download_to_device` | Download compiled application to PLC. `mode`: `auto` (default - try online change, fall back to full), `online_change` (fail if rejected), or `full`. After login the boot application is built so the change survives power-cycle. 120s timeout |
| `start_stop_application` | Start or stop the PLC application |
| `monitor_variables` | Sample one or more PLC variables at a fixed interval over a bounded duration. Each sample goes through the `with_executor` frame (adds a few ms per read), so very short intervals see real-vs-requested cadence drift. Return timeseries (capped at 60s. intervalMs floor 10ms) |

### Library Management Tools

| Tool | Description |
|------|-------------|
| `list_project_libraries` | List all libraries referenced in the project with version info |
| `add_library` | Add a library reference to the project. The library must be installed in the local CODESYS repository. pass the fully-qualified placeholder name (e.g. `Standard, * (System)`) - bare names like `Util` won't resolve |

### Device-Tree Tools

| Tool | Description |
|------|-------------|
| `list_device_repository` | Read-only enumeration of every device descriptor installed in the local CODESYS Device Repository. Optional `vendor`, `nameContains`, `maxResults` filters. Returns `{name, vendor, device_type, device_id, version, description, category}` per entry - substrate for validating `add_device` arguments |
| `inspect_device_node` | Read-only introspection of a project device node: descriptor metadata, parameter list with current values, child sub-devices |
| `add_device` | Wrap `parent.add_device(name, type, id, version)`. Pair with `list_device_repository` to source canonical `deviceType` / `deviceId` / `version` triples instead of guessing |
| `set_device_parameter` | EXPERIMENTAL. Wrap `device.parameter[id].value = ...` with fallbacks. Many fieldbus parameters are GUI-only and return a clear error |
| `map_io_channel` | Bind (or clear) a fieldbus I/O channel to a global variable symbol. Resolves channel by slash-separated name path (`Inputs/Byte 0/Bit 3`) or numeric indices (`0/3`). Set `clearBinding: true` to remove an existing binding |

### Archiving Tools

| Tool | Description |
|------|-------------|
| `create_project_archive` | Save the open project as a `.projectarchive`. Saves unsaved edits first. Optional `comment`, `includeLibraries`, `includeCompiledLibraries` |

## MCP Resources

| Resource URI | Description |
|--------------|-------------|
| `codesys://project/status` | CODESYS scripting status and open project info |
| `codesys://project/{path}/structure` | Project tree structure |
| `codesys://project/{path}/pou/{pou}/code` | POU declaration and implementation code |

### URI path format

The `{path}` and `{pou}` segments use [RFC 6570 reserved expansion](https://datatracker.ietf.org/doc/html/rfc6570#section-3.2.3) - pass the values **literally with raw `:` and `/`**, not percent-encoded. On Windows, convert backslashes to forward slashes. Examples:

```
codesys://project/C:/Users/me/Documents/MyPLC.project/structure
codesys://project/C:/Users/me/Documents/MyPLC.project/pou/Application/MyPOU/code
codesys://project/C:/Users/me/Documents/MyPLC.project/pou/Application/MyFB/Method1/code
```

The `pou-code` resource also reads Method and Property bodies (despite its name) - a path with three or more segments after `/pou/` resolves down to children of FBs. If you percent-encode the path (e.g. `C%3A%2FUsers%2F...`), the segment is passed through verbatim and treated as a relative path, which fails with `Object reference not set to an instance of an object`.

`ListMcpResourcesTool` only returns the static `project-status` resource. The two templated resources are dynamic (require parameters) and don't appear in the list.

> ⚠️ **Side effect:** if the requested project path differs from the currently-open project, `ensure_project_open` will close the current one and open the requested one. This violates the "resources are read-only" expectation. Treat resource URIs as if they could swap project context.

## Execution Modes

### Persistent Mode (default)

1. **Session adoption first.** Server scans `%TEMP%/codesys-mcp-persistent/` for any live session left by a previous MCP server (matching profile, PID still alive, `ready.signal` present). If one is found, the launcher attaches to it instead of spawning a new CODESYS - this closes out the orphan-on-`/mcp`-reconnect problem
2. Otherwise, server launches `CODESYS.exe` with `--runscript=watcher.py` (no `--noUI`)
3. CODESYS UI opens - user can see and interact with the IDE
4. The watcher script writes `ready.signal` (with PID + profile + python version), then starts a .NET background thread that polls a `commands/` directory and **returns control to CODESYS** so the UI stays fully responsive
5. When a tool is called, the server writes a `.py` script + `.command.json` to `commands/` (atomic via `.NET File.Replace`, with script written + renamed before the trigger)
6. The background thread detects the command and marshals execution onto the CODESYS UI thread via `system.execute_on_primary_thread()`
7. Results are written atomically to `results/`; Node polls with exponential backoff (100ms → 1000ms cap)
8. Changes made by tools appear in the CODESYS UI in real-time
9. The UI remains interactive between commands - only briefly paused during synchronous API calls (compile, open)

### Headless Mode

Falls back to the original approach: each tool call spawns a new CODESYS process with `--noUI`, runs the script, and exits. No UI is shown. Used when:

- `--mode headless` is specified
- Persistent mode fails to launch and `--fallback-headless` is enabled
- CODESYS is launched with `--no-auto-launch` and `launch_codesys` hasn't been called yet

## Detect Installed Versions

```bash
codesys-mcp-persistent --detect
```

Scans `Program Files` and `Program Files (x86)` for CODESYS installations.

## Known limitations

These are CODESYS scripting API or platform constraints, not bugs in this server:

- **Identifier length is not enforced at create time.** `create_pou`, `create_dut`, `create_gvl` accept names of any length. CODESYS only complains during compile or save. Stick to ≤32 char IEC identifiers.
- **DUT names containing `.` are rejected by CODESYS** with `The name 'X.Y' is not valid for this object.` Don't use dots in identifier names.
- **`set_pou_code` empty-string is now a no-op.** Passing `declarationCode: ""` (or `implementationCode: ""`) is treated the same as omitting it - the section is not changed. To explicitly clear a section, pass a single-line placeholder like `// cleared` or a comment block.
- **`delete_object` won't delete a user object with a system-reserved last segment via legacy clients.** The allowlist uses exact path matching. User folders named `MainTask`, `Library Manager`, etc. are allowed as long as they're nested under a non-system parent path.
- **`find_object_by_path` ambiguous resolves return None.** If two objects share a name in the project tree, the helper now refuses to pick a winner. Pass a more specific path (e.g. `Application/SubFolder/MyPOU` instead of just `MyPOU`).
- **`add_library` requires a fully-qualified placeholder** matching the Library Manager UI display string (e.g. `Standard, * (System)`). Bare names like `Util` fail with `placeholder library X could not be resolved`.
- **`set_default_credentials` rejects empty usernames** with `ValueError`. The `set_credentials` tool Zod-validates `username.min(1)`.
- **`is_simulation_mode` getter returns `None`** on the ifm AE3100 device descriptor (and probably others). The setter works. Verification has to come from compile + Online → Login working.
- **`online.create_online_application` historically raised `Stack empty`** from a pure IPC-driven script — the IDE-internal `_executionStack` is only populated by the script executor's `Executing` event, which the IPC bridge bypassed. **Fixed in 0.6.3** for real PLCs: `ensure_online_connection.py` now reflects into `scriptengine.online._executor` and runs every online call inside an `ExecuteSource(source)` frame (via the `with_executor` helper). Real-PLC programmatic login + start/stop/read/write/download now work without a manual `Online → Login` click. If you run on a CODESYS SP where the private `_executor` field is renamed, `with_executor` degrades to a direct call and the helper surfaces an actionable error pointing at the manual workaround. Simulation mode (`set_simulation_mode(enable=true)`) is still hit-or-miss on this front — engaged simulation can leave the project in a state that resists `create_online_application` even with the workaround; if so, click `Online → Login` once in the IDE.
- **`set_pou_code` auto-saves** - every successful call writes to disk. UI Ctrl+Z does not recover prior content.
- **Persistent mode is broken on CODESYS V3.5 SP21+.** The watcher's UI-thread marshalling call (`se.system.execute_on_primary_thread()`) was removed from the scripting API; the SP21 P5 stub `ScriptLib/Stubs/scriptengine/ScriptSystem.pyi` has zero matches for `primary_thread|invoke|marshal|dispatch|defer|async`. CODESYS doesn't announce the removal in the SP21 release notes (the closest signal is SP21 P3's one-liner `CDS-94322 "Scripting: Context object for Python calls needed"`, which may or may not be the breakpoint). Symptom: persistent mode boots cleanly, then every tool call returns `Marshal error: The functionality 'system.execute_on_primary_thread(...)' is no longer supported`. **The `--fallback-headless` flag is launch-time only** — it does not catch this and auto-swap mid-session. Workarounds: (a) run with `--mode headless` until the watcher rewrite ships, or (b) use the forward-port at [phobicdotno/Codesys-MCP-SP21-plus](https://github.com/phobicdotno/Codesys-MCP-SP21-plus) which implements the single-thread + `system.delay()` rewrite. SP19 / SP20 are unaffected.

## Troubleshooting

**CODESYS not found**
Verify the path with `--detect`. The executable is typically at:
`C:\Program Files\CODESYS 3.5.XX.X\CODESYS\Common\CODESYS.exe`

**Project file locked**
Another CODESYS instance may have the project open. Close it first or use persistent mode so there's only one instance.

**Every tool call fails with "Marshal error: ... is no longer supported" (CODESYS V3.5 SP21+)**
CODESYS removed `se.system.execute_on_primary_thread()` somewhere in the SP21 line. The persistent watcher uses it to dispatch work from its polling thread onto the IDE's UI thread; without it, every tool call returns this error verbatim. The launcher comes up cleanly (`ready.signal` fires before the first marshal), so this doesn't surface until you actually call a tool.

Workaround for now: switch to headless mode — `--mode headless` (or remove the `--mode persistent` arg if you've set it explicitly). Each tool call will spawn a fresh `--noUI` CODESYS process; you lose the live-UI workflow and pay the 10–30s startup-per-command cost but everything else works. Alternatively, use the SP21+ forward-port at [phobicdotno/Codesys-MCP-SP21-plus](https://github.com/phobicdotno/Codesys-MCP-SP21-plus). The rewrite is on this repo's roadmap; tracked in `CLAUDE.md` deferred work.

**Watcher timeout (persistent mode)**
Default is **180 seconds** - cold first launches of older SPs (SP16 P5 observed at ~120s) routinely exceed the older 60s budget. If the watcher still doesn't signal ready, check:
- CODESYS path and profile are correct
- No modal dialogs are blocking CODESYS startup
- Bump the deadline further on slow hardware: `CODESYS_MCP_READY_TIMEOUT_MS=300000`
- Try `--verbose` for detailed logging

If a launch timed out but CODESYS is actually still coming up, simply call `launch_codesys` again (or reconnect `/mcp`) - the launcher's recovery path will re-attach to the alive PID and finish polling for `ready.signal` instead of spawning a second instance.

**UI briefly pauses during commands (persistent mode)**
The watcher uses a background thread that marshals work onto the UI thread, so the UI stays responsive between commands. During synchronous CODESYS API calls (compile, project open), the UI may briefly pause - this is expected and normal. If a command hangs, check the CODESYS messages window for modal dialogs or errors.

**Command timeout**
Default is 60s (120s for compile and download). Increase with `--timeout <ms>`. Check CODESYS messages window for errors.

**Online/runtime tools fail**
The online tools (`connect_to_device`, `read_variable`, etc.) require:
- A device/gateway configured in the CODESYS project (or `connect_to_device(ipAddress=...)` to set one at call time, or `set_simulation_mode(enable=true)` for a simulator-only flow)
- The project to be compiled successfully before connecting
- A reachable PLC or CODESYS SoftPLC runtime (when not in simulation)

`disconnect_from_device` is safe to call when not connected - it returns `Already disconnected.` rather than failing.

**`Stack empty` from `connect_to_device`**
Fixed in 0.6.3 for real PLCs. `ensure_online_connection.py` now reflects into `scriptengine.online._executor` and runs every online call inside an `ExecuteSource(source)` frame, so the IDE-internal `_executionStack` the scripting API depends on is properly populated. Standard `connect_to_device`, `start_stop_application`, `read_variable`, `write_variable`, `download_to_device`, `get_application_state`, and `monitor_variables` all work programmatically against real hardware without a manual IDE login. If you still see `Stack empty` after upgrading:
- Confirm the SP exposes `scriptengine.online._executor` (CODESYS V3 SP14+; verified on SP16 P5). The helper raises a clear error if the private field has been renamed in a future SP.
- For simulation mode (`set_simulation_mode(enable=true)`): the workaround is hit-or-miss against the simulator; click `Online → Login` once in the IDE if needed, or test against a real PLC / CODESYS Control Win softPLC.

**`Network error: No route to host` from `connect_to_device`** even though `ping`/TCP works
CODESYS V3 login routes by the Network/Block-Driver node address (e.g. `0301.B0F7`) assigned by the gateway during a scan — not by the IP-encoded form (`0192.0168.0083.0247`) that `set_gateway_and_address` stores from a raw IP string. **Fixed in 0.6.3:** `connect_to_device` now scans the gateway after setting the IP and re-sets the device to the scan node form before login. If you still hit this, run `gw.perform_network_scan()` manually via `eval_python` to see what the gateway can reach — empty results usually mean a firewall blocking the gateway-to-runtime port (TCP 11740 by default) rather than the IP path.

**Project file locked after MCP server restart**
The launcher now scans for a live session from the prior MCP server and adopts it on startup, so this should rarely surface. If it still does (mismatched profile, malformed `ready.signal`, or you ran a non-persistent transient earlier), either close the orphan `CODESYS.exe` via Task Manager, or pass `--kill-existing-codesys` to the next launch (off by default so we never kill an external IDE session you might have open).

**`add_library` reports "placeholder library X could not be resolved"**
The `add_library` tool calls `Library Manager.add_library(name)`, which only accepts library names that are installed in the CODESYS library repository. Ad-hoc strings like `"Util"` are rejected. Pass a fully-qualified placeholder string the way it appears in the Library Manager UI, e.g.:
- `Standard, * (System)`
- `Util, 3.5.16.0 (3S - Smart Software Solutions GmbH)`
- `CAA Memory, * (CAA Technical Workgroup)`

If you don't know the exact placeholder string, add the library once via the CODESYS UI to discover the canonical form, then use that string for subsequent calls.

## Roadmap (still-open gaps)

Implemented in 0.6.0: `search_code`, `find_references`, `rename_symbol`, `monitor_variables`, `create_project_archive`, `inspect_device_node`, `add_device`, `set_device_parameter`, `list_device_repository`, `map_io_channel`. Still on the table:

| Capability | Scope | Why it matters |
|---|---|---|
| `generate_boot_application` | Wraps `Online.CreateBootApplication` | Field-deploy artefact creation |
| `configure_task` | Cyclic / event / freewheeling task config + POU attachment | Cycle-time-sensitive code (PPVS reject latency) needs scriptable task config |
| `export_project_xml` | `proj.export_xml(...)` | Cut from 0.6.0 in favour of `create_project_archive`. Revisit if a non-deterministic-but-readable export channel is needed |

## Development

```bash
# Install dependencies
npm install

# Build (compiles TypeScript + copies Python scripts)
npm run build

# Run all tests
npm test

# Type check only
npm run typecheck

# Run tests in watch mode
npm run test:watch
```

### Project Structure

```
src/
  bin.ts              CLI entry point
  server.ts           MCP tool/resource registration (41 tools, 3 resources)
  launcher.ts         CODESYS process management
  ipc.ts              File-based IPC transport
  headless.ts         Headless fallback executor
  script-manager.ts   Python template loading + interpolation
  types.ts            Shared TypeScript types
  logger.ts           Structured stderr logging
  scripts/            Python scripts (watcher + helpers + tool scripts)
tests/
  unit/               Unit tests (IPC, script manager, launcher)
  integration/        Integration tests (script pipeline, manual CODESYS tests)
  mock_watcher.py     Standalone watcher for testing without CODESYS
```

## License

MIT
