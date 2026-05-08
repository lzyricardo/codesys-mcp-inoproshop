# codesys-mcp-persistent

MCP server for CODESYS with a persistent UI instance and file-based IPC.

Unlike headless-only approaches that spawn a new CODESYS process per command, this server launches CODESYS **with its UI visible** and keeps it running. MCP tool calls are sent to the same instance via a file-based IPC watcher, so changes appear in real-time and the user can interact with the IDE alongside AI-driven automation.

## Features

- **Persistent mode** — CODESYS UI stays open; commands execute in the running instance
- **Headless fallback** — automatic fallback to `--noUI` spawn-per-command if persistent mode fails
- **File-based IPC** — proven approach using atomic file writes and a Python watcher script
- **Command serialization** — async mutex ensures one command at a time
- **Health monitoring** — detects CODESYS crashes and reports state
- **40 MCP tools** — project management, POU authoring, structured compiler diagnostics, runtime monitoring, simulation, library management, code search, refactor, device tree, fieldbus I/O mapping, archiving
- **Drop-in replacement** — same MCP tool names and parameters as `@codesys/mcp-toolkit` (the original toolkit's surface is a strict subset)

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

**Requirements:** Node.js 18+, Windows, CODESYS 3.5 SP19 or SP21 installed.

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
| `--kill-existing-codesys` | Kill any running `CODESYS.exe` before launching (dev convenience; off by default to protect external IDE sessions) | `false` |
| `--timeout <ms>` | Default command timeout | `60000` |
| `--detect` | List installed CODESYS versions and exit | — |
| `--verbose` | Enable verbose logging | — |
| `--debug` | Enable debug logging | — |
| `-V, --version` | Show version number | — |
| `-h, --help` | Show help | — |

Environment variables `CODESYS_PATH` and `CODESYS_PROFILE` are used as defaults when the corresponding flags are not provided.

## MCP Tools

### Management Tools

| Tool | Description |
|------|-------------|
| `launch_codesys` | Manually launch CODESYS (use with `--no-auto-launch`) |
| `shutdown_codesys` | Shut down the persistent CODESYS instance |
| `get_codesys_status` | Get current state, PID, execution mode |

### Project Tools

| Tool | Description |
|------|-------------|
| `open_project` | Open an existing CODESYS project file |
| `create_project` | Create a new project from the standard template |
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
| `rename_symbol` | Best-effort textual rename across all POU bodies. Two-phase write (plan + apply); refuses IEC keywords; `dryRun=true` by default |

### Online / Runtime Tools

| Tool | Description |
|------|-------------|
| `connect_to_device` | Login to the PLC runtime. Optionally pass `ipAddress` (and `gatewayName`, default `Gateway-1`) to set the device address before login |
| `disconnect_from_device` | Logout from the PLC runtime. No-op (returns success) if not connected |
| `set_credentials` | Set default `username`/`password` for subsequent logins. Username must be non-empty; for no-auth runtimes simply do not call this tool |
| `set_simulation_mode` | Toggle device-level simulation mode on/off. Run before `connect_to_device` when no physical PLC is available |
| `get_application_state` | Check if the PLC application is running, stopped, or in exception |
| `read_variable` | Read a live variable value from the running PLC (e.g., `PLC_PRG.bMotorRunning`) |
| `write_variable` | Write/force a variable value on the running PLC |
| `download_to_device` | Download compiled application to PLC. `mode`: `auto` (default — try online change, fall back to full), `online_change` (fail if rejected), or `full`. 120s timeout |
| `start_stop_application` | Start or stop the PLC application |
| `monitor_variables` | Sample one or more PLC variables at a fixed interval over a bounded duration; return timeseries (capped at 60s; intervalMs floor 10ms) |

### Library Management Tools

| Tool | Description |
|------|-------------|
| `list_project_libraries` | List all libraries referenced in the project with version info |
| `add_library` | Add a library reference to the project. The library must be installed in the local CODESYS repository; pass the fully-qualified placeholder name (e.g. `Standard, * (System)`) — bare names like `Util` won't resolve |

### Device-Tree Tools

| Tool | Description |
|------|-------------|
| `list_device_repository` | Read-only enumeration of every device descriptor installed in the local CODESYS Device Repository. Optional `vendor`, `nameContains`, `maxResults` filters. Returns `{name, vendor, device_type, device_id, version, description, category}` per entry — substrate for validating `add_device` arguments |
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

The `{path}` and `{pou}` segments use [RFC 6570 reserved expansion](https://datatracker.ietf.org/doc/html/rfc6570#section-3.2.3) — pass the values **literally with raw `:` and `/`**, not percent-encoded. On Windows, convert backslashes to forward slashes. Examples:

```
codesys://project/C:/Users/me/Documents/MyPLC.project/structure
codesys://project/C:/Users/me/Documents/MyPLC.project/pou/Application/MyPOU/code
codesys://project/C:/Users/me/Documents/MyPLC.project/pou/Application/MyFB/Method1/code
```

The `pou-code` resource also reads Method and Property bodies (despite its name) — a path with three or more segments after `/pou/` resolves down to children of FBs. If you percent-encode the path (e.g. `C%3A%2FUsers%2F...`), the segment is passed through verbatim and treated as a relative path, which fails with `Object reference not set to an instance of an object`.

`ListMcpResourcesTool` only returns the static `project-status` resource; the two templated resources are dynamic (require parameters) and don't appear in the list.

> ⚠️ **Side effect:** if the requested project path differs from the currently-open project, `ensure_project_open` will close the current one and open the requested one. This violates the "resources are read-only" expectation; treat resource URIs as if they could swap project context.

## Execution Modes

### Persistent Mode (default)

1. Server launches `CODESYS.exe` with `--runscript=watcher.py` (no `--noUI`)
2. CODESYS UI opens — user can see and interact with the IDE
3. The watcher script starts a .NET background thread that polls a `commands/` directory, then **returns control to CODESYS** so the UI stays fully responsive
4. When a tool is called, the server writes a `.py` script + `.command.json` to `commands/`
5. The background thread detects the command and marshals execution onto the CODESYS UI thread via `system.execute_on_primary_thread()`
6. Results are written atomically to `results/`
7. Changes made by tools appear in the CODESYS UI in real-time
8. The UI remains interactive between commands — only briefly paused during synchronous API calls (compile, open)

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

- **Identifier length is not enforced at create time.** `create_pou`, `create_dut`, `create_gvl` accept names of any length; CODESYS only complains during compile or save. Stick to ≤32 char IEC identifiers.
- **DUT names containing `.` are rejected by CODESYS** with `The name 'X.Y' is not valid for this object.` Don't use dots in identifier names.
- **`set_pou_code` empty-string is now a no-op.** Passing `declarationCode: ""` (or `implementationCode: ""`) is treated the same as omitting it - the section is not changed. To explicitly clear a section, pass a single-line placeholder like `// cleared` or a comment block.
- **`delete_object` won't delete a user object with a system-reserved last segment via legacy clients.** The allowlist uses exact path matching; user folders named `MainTask`, `Library Manager`, etc. are allowed as long as they're nested under a non-system parent path.
- **`find_object_by_path` ambiguous resolves return None.** If two objects share a name in the project tree, the helper now refuses to pick a winner; pass a more specific path (e.g. `Application/SubFolder/MyPOU` instead of just `MyPOU`).
- **`add_library` requires a fully-qualified placeholder** matching the Library Manager UI display string (e.g. `Standard, * (System)`). Bare names like `Util` fail with `placeholder library X could not be resolved`.
- **`set_default_credentials` rejects empty usernames** with `ValueError`. The `set_credentials` tool Zod-validates `username.min(1)`.
- **`is_simulation_mode` getter returns `None`** on the ifm AE3100 device descriptor (and probably others). The setter works; verification has to come from compile + Online → Login working.
- **`online.create_online_application` raises `Stack empty`** even when simulation is engaged via `system.commands.Item('Simulation').execute('true')`. The IDE's Login command populates an internal context stack the scripting API can't reach. Workaround: click `Online → Login` once in the IDE per session, or run against a real PLC.
- **`set_pou_code` auto-saves** — every successful call writes to disk. UI Ctrl+Z does not recover prior content.
- **Atomic file writes are not strictly atomic on Windows** — the watcher's `os.remove` + `os.rename` sequence leaves a small window where readers see no file. Tolerated by the IPC retry loop but not ideal. Tracked.

## Troubleshooting

**CODESYS not found**
Verify the path with `--detect`. The executable is typically at:
`C:\Program Files\CODESYS 3.5.XX.X\CODESYS\Common\CODESYS.exe`

**Project file locked**
Another CODESYS instance may have the project open. Close it first or use persistent mode so there's only one instance.

**Watcher timeout (persistent mode)**
If the watcher doesn't signal ready within 60 seconds, check:
- CODESYS path and profile are correct
- No modal dialogs are blocking CODESYS startup
- Try `--verbose` for detailed logging

**UI briefly pauses during commands (persistent mode)**
The watcher uses a background thread that marshals work onto the UI thread, so the UI stays responsive between commands. During synchronous CODESYS API calls (compile, project open), the UI may briefly pause — this is expected and normal. If a command hangs, check the CODESYS messages window for modal dialogs or errors.

**Command timeout**
Default is 60s (120s for compile and download). Increase with `--timeout <ms>`. Check CODESYS messages window for errors.

**Online/runtime tools fail**
The online tools (`connect_to_device`, `read_variable`, etc.) require:
- A device/gateway configured in the CODESYS project (or `connect_to_device(ipAddress=...)` to set one at call time, or `set_simulation_mode(enable=true)` for a simulator-only flow)
- The project to be compiled successfully before connecting
- A reachable PLC or CODESYS SoftPLC runtime (when not in simulation)

`disconnect_from_device` is safe to call when not connected — it returns `Already disconnected.` rather than failing.

**`Stack empty` from `connect_to_device` after enabling simulation**
A known limitation in the CODESYS scripting API: `online.create_online_application` can raise `Stack empty` even when simulation is engaged, because the internal context stack is populated by IDE selection (clicking Device or Application in the navigator). Workarounds:
- Click `Online -> Login` once in the CODESYS IDE for the session, then retry. The project-level simulation flag persists.
- Or run against a real PLC / CODESYS Control Win softPLC instead of IDE simulation.

**Project file locked after MCP server restart**
If a previous MCP session left an orphan `CODESYS.exe` holding the project file, transient spawns will fail with "selected project currently in use". Either close the orphan via Task Manager, or pass `--kill-existing-codesys` to the next launch (off by default so we never kill an external IDE session you might have open).

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
| `export_project_xml` | `proj.export_xml(...)` | Cut from 0.6.0 in favour of `create_project_archive`; revisit if a non-deterministic-but-readable export channel is needed |

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
  server.ts           MCP tool/resource registration (40 tools, 3 resources)
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
