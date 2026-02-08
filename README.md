# codesys-mcp-persistent

MCP server for CODESYS with a persistent UI instance and file-based IPC.

Unlike headless-only approaches that spawn a new CODESYS process per command, this server launches CODESYS **with its UI visible** and keeps it running. MCP tool calls are sent to the same instance via a file-based IPC watcher, so changes appear in real-time and the user can interact with the IDE alongside AI-driven automation.

## Features

- **Persistent mode** — CODESYS UI stays open; commands execute in the running instance
- **Headless fallback** — automatic fallback to `--noUI` spawn-per-command if persistent mode fails
- **File-based IPC** — proven approach using atomic file writes and a Python watcher script
- **Command serialization** — async mutex ensures one command at a time
- **Health monitoring** — detects CODESYS crashes and reports state
- **Drop-in replacement** — same MCP tool names and parameters as `@codesys/mcp-toolkit`

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
| `compile_project` | Build the primary application (120s timeout) |

### POU Tools

| Tool | Description |
|------|-------------|
| `create_pou` | Create a Program, Function Block, or Function |
| `set_pou_code` | Set declaration and/or implementation code |
| `create_property` | Create a property within a Function Block |
| `create_method` | Create a method within a Function Block |

## MCP Resources

| Resource URI | Description |
|--------------|-------------|
| `codesys://project/status` | CODESYS scripting status and open project info |
| `codesys://project/{path}/structure` | Project tree structure |
| `codesys://project/{path}/pou/{pou}/code` | POU declaration and implementation code |

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
The v0.3.0 watcher uses a background thread that marshals work onto the UI thread, so the UI stays responsive between commands. During synchronous CODESYS API calls (compile, project open), the UI may briefly pause — this is expected and normal. If a command hangs, check the CODESYS messages window for modal dialogs or errors.

**Command timeout**
Default is 60s (120s for compile). Increase with `--timeout <ms>`. Check CODESYS messages window for errors.

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
  server.ts           MCP tool/resource registration
  launcher.ts         CODESYS process management
  ipc.ts              File-based IPC transport
  headless.ts         Headless fallback executor
  script-manager.ts   Python template loading + interpolation
  types.ts            Shared TypeScript types
  logger.ts           Structured stderr logging
  scripts/            Python scripts (watcher + 13 tool scripts)
tests/
  unit/               Unit tests (IPC, script manager, launcher)
  integration/        Integration tests (script pipeline, manual CODESYS tests)
  mock_watcher.py     Standalone watcher for testing without CODESYS
```

## License

MIT
