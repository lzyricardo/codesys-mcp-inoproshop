# CLAUDE.md - codesys-mcp-persistent

Orientation for a future Claude / agent session working on this repo. Read first.

## What this is

`codesys-mcp-persistent` is an MCP server that wraps the **CODESYS V3.5 IDE scripting API** (IronPython 2.7) as MCP tools. Owned/maintained by Luke Harriman (`luke-harriman` on GitHub). Drop-in superset of `@codesys/mcp-toolkit`.

- **Target runtime:** Windows + CODESYS V3.5 SP19 / SP21 + Node 18+. Not portable.
- **Wire format:** stdio JSON-RPC (MCP) on the outside; file-based IPC on the inside.
- **Two execution modes:** `persistent` (CODESYS UI stays open, watcher.py running, commands marshalled onto its primary thread) and `headless` (`--noUI` spawn-per-command). Persistent is the point of the project; headless is the bootstrap + fallback.

Read `README.md` for tool surface, `ARCHITECTURE.md` for IPC details, `CHANGELOG.md` for the per-version journey.

## Hard architectural constraints (don't fight these)

1. **IronPython 2.7 inside CODESYS.** Scripts run there, not in CPython. No `f""` strings, no `print()` parens, no `nonlocal`, `unicode` is a separate type from `str`, ints can be `long`, `range()` returns a list. The default `json.dumps(..., ensure_ascii=True)` calls a defective decode path that crashes on cp1252 bytes - **always use `ensure_ascii=False` and emit utf-8 via `_text_utils.emit_result()`**.
2. **ASCII-only Python source** (no `# -*- coding -*-` header in current scripts). Em-dashes, smart quotes, `§` are forbidden in source. The static checker `dev/check-scripts.ps1` enforces this; run it before every commit.
3. **CODESYS scripting API is single-threaded.** The watcher marshals commands onto the IDE's primary UI thread via `system.execute_on_primary_thread()`. A long-running script (regex DoS, big bulk read) freezes the IDE.
4. **Some operations only work when the IDE has a selection in its navigator.** `online.create_online_application` raises `Stack empty` in pure scripting; user has to click `Online -> Login` once per session. Documented limit; not a bug we can fix in the script.
5. **`set_pou_code` auto-saves to disk.** UI Ctrl+Z does NOT recover prior content. Read before overwriting; treat the project file as the source of truth, not the IDE buffer.

## How scripts are delivered

Scripts in `src/scripts/*.py` are **templates with `{KEY}` placeholders**. They are NOT imported by Python; they are **concatenated at the TS layer** via `ScriptManager.prepareScriptWithHelpers(name, params, helpers)`:

1. Helper files (e.g. `_text_utils`, `ensure_project_open`, `find_object_by_path`) are loaded and concatenated first.
2. The main script is appended.
3. `interpolate()` runs `{KEY}` substitution with **automatic Python string escaping** (`pyEscape` in `script-manager.ts`). Use `{KEY:raw}` to bypass escaping (rare; only `set_pou_code` declaration/implementation use this).

**Consequence:** helpers and the main script share module scope. A function defined in `_text_utils.py` is callable from any script that includes it. Variables like `PROJECT_FILE_PATH = "{PROJECT_FILE_PATH}"` declared in a helper are visible to the main script. **If a tool script uses a name, either it or one of its declared helpers must define it.** (See "Known pitfall" #1.)

## Substrate primitives that earn their keep

These exist for real reasons. Don't simplify them away without reading their CHANGELOG entry first.

| Primitive | File | Why it exists |
|---|---|---|
| `ExecutorProxy` | `src/executor-proxy.ts` | Stable proxy reference + readiness-promise gate so persistent-mode auto-launch doesn't race with in-flight tool calls. The `swapVersion` counter handles the case where `launch_codesys` and the background auto-launch race; minor surface, leave it. |
| `### RESULT_JSON ###` markers | `src/scripts/_text_utils.py` (`emit_result`) + `src/result-parser.ts` (`parseResultJson`) | Standardised structured-payload channel that survives interleaved DEBUG/print noise. The parser scans from `lastIndexOf(START)` so a stray marker copy in debug output doesn't confuse it. |
| `_text_utils._to_unicode` | `src/scripts/_text_utils.py` | Coerce CODESYS-returned bytes (frequently cp1252) to unicode before json.dumps. Without this every script crashes on POU comments containing `§`. |
| `_text_utils._json_default` | same | Coerces .NET-backed `long` sentinels (e.g. message position 281474976710655L) into ints. Without it, `json.dumps` raises TypeError on real compile messages. |
| `ensure_project_open` (helper) | `src/scripts/ensure_project_open.py` | Mutator helper. Opens the project (with retry) if not currently primary, and switches to it if a different project is. Declares `PROJECT_FILE_PATH = "{PROJECT_FILE_PATH}"` so any script using it for free. |
| `require_project_open` (helper) | `src/scripts/require_project_open.py` | Read-only sibling. Raises if the requested project isn't currently primary; never opens or switches. Use this in resource handlers and read-only tools (inspect_device_node, create_project_archive). Also declares `PROJECT_FILE_PATH`. |
| `find_object_by_path_robust` | `src/scripts/find_object_by_path.py` | Walks a slash- or dot-separated path under a start node. Refuses ambiguous matches (returns `None` rather than picking a winner). Used by every CRUD script. |

## Substrate that was deliberately deleted (don't bring back as bandaid)

| Removed | Reason | If you're tempted to add it back |
|---|---|---|
| `MutationTracker` (0.6.1) | Lossy heuristic - tracked only TS-side mutator calls, missed IDE edits and watcher restarts; produced one warning string that a static note delivers identically. | Verify the new use-case isn't authoritative on the TS side either. The CODESYS compile cache is the truth, not us. |
| Script-template cache (0.6.1) | Solved an imaginary perf problem (~1ms vs ~100ms CODESYS calls); existed because it broke template iteration during dev. | Don't. Disk reads aren't the bottleneck. |
| `formatMutatorResponse` (0.6.1) | Just `markMutated` + `formatToolResponse`. Vestige of the removed tracker. | Use `formatToolResponse` directly. |
| Per-script `try/except: print SCRIPT_ERROR; sys.exit(1)` boilerplate | Audit flagged it; held back because `SCRIPT_SUCCESS` is load-bearing (server.ts checks `output.includes('SCRIPT_SUCCESS')`). The watcher already catches uncaught exceptions cleanly. | If you tackle this, it's its own release - touches every script. |
| `simpleTool()` registration helper | Audit recommended; held back because ~30% of tools have bespoke parsing (`compile_project`, `read_variable`, `monitor_variables`, `search_code`, `rename_symbol`). | Possible future cut, but verify the helper actually fits the bespoke shapes before generalizing. |

## Conventions

### Adding a new tool

1. Write `src/scripts/<name>.py`. Start with a placeholder block:
   ```python
   import sys, scriptengine as script_engine, traceback

   PARAM_A = "{PARAM_A}"  # always use placeholders for inputs

   try:
       primary_project = ensure_project_open(PROJECT_FILE_PATH)
       # ... do the work ...
       emit_result({u"key": value})  # if structured output needed
       print("SCRIPT_SUCCESS: <one-line summary>")
       sys.exit(0)
   except Exception as e:
       print("Error: %s\n%s" % (e, traceback.format_exc()))
       print("SCRIPT_ERROR: %s" % e)
       sys.exit(1)
   ```
2. Register in `src/server.ts`:
   - Use `s.tool(name, description, zodSchema, handler)`.
   - **Description: ~150 chars max.** It loads into every model turn.
   - For mutators: helpers `['_text_utils', 'ensure_project_open', 'find_object_by_path']`.
   - For read-only: helpers `['_text_utils', 'require_project_open', 'find_object_by_path']`.
   - For non-project-state (global like `list_device_repository`): just `['_text_utils']`.
   - Use `formatToolResponse(result, successMessage)` for plain-text response, or `parseResultJson<T>(result.output)` for structured returns.
3. Run `pwsh dev/check-scripts.ps1` (ASCII + template-reference check).
4. `npm run build && npm test`.
5. After Python script changes: no MCP restart needed (cache removed in 0.6.1; templates read from disk every call).
6. After TS changes: `/mcp` reconnect required.
7. Update `README.md` tool table and `CHANGELOG.md`.

### Choosing the right helpers

- **Read-only tool that needs the project loaded** → `require_project_open` (raises if wrong project is primary; never switches). Use in resource handlers.
- **Mutator** → `ensure_project_open` (opens or switches). Note the side effect: this can close the user's currently-open project.
- **Global state, no project** → no helper. Just `['_text_utils']` if you emit RESULT_JSON.

### When NOT to escape strings yourself

`pyEscape()` in `script-manager.ts:interpolate()` runs on every `{KEY}` substitution. Don't double-escape in the script. The one exception: `set_pou_code.py` does its own targeted escape inside triple-quoted code blocks (uses `{KEY:raw}` to opt out of central escaping for the code body). Don't add new uses of `{KEY:raw}` without thinking carefully about injection.

### When NOT to add multi-version API probes

The `add_device.py`, `set_device_parameter.py`, `list_device_repository.py`, `create_project_archive.py` scripts have multi-method probes (e.g. try `get_all_devices()` then `devices` then `iter(repo)`). Some are grounded in real SP-version differences; some are speculative defensive code. **Only add a fallback when you've actually hit the divergence.** A speculative `try X except Y try Z` chain hides bugs.

## Known pitfalls (the recurring ones)

1. **`PROJECT_FILE_PATH` not defined** if your script uses `ensure_project_open(PROJECT_FILE_PATH)` or `require_project_open(PROJECT_FILE_PATH)` but doesn't declare the placeholder. Fixed in 0.6.2 by having both helpers declare it themselves; if you write a NEW helper, declare it there too.
2. **Em-dashes / smart quotes / `§`** in `.py` source crash IronPython without a coding header. `dev/check-scripts.ps1` catches this. Run before commit.
3. **`json.dumps` default `ensure_ascii=True` crashes** on cp1252 bytes returned by CODESYS textual fields. Always `ensure_ascii=False` + emit utf-8 via `emit_result()`.
4. **Orphan CODESYS process holds the project file lock** across `/mcp` reconnects. Symptom: `StandardError: The selected project is currently in use by '<user>' on '<host>'`. Workaround: pass `--kill-existing-codesys` to the launcher (off by default to protect external IDE sessions), or kill the orphan via Task Manager.
5. **`connect_to_device` raises `Stack empty`** when simulation mode is engaged via the scripting API. The IDE's Login command needs a navigator selection that the scripting API can't set. Workaround: click `Online -> Login` once per session, or run against a real PLC.
6. **`set_pou_code` empty-string semantics**: passing `""` for `declarationCode` or `implementationCode` is **a no-op**, not a clear. To explicitly clear a section, pass a single-line placeholder like `// cleared`. Hardened in 0.5.2 with explicit `UPDATE_DECL/UPDATE_IMPL` flags.
7. **`add_library` placeholder format**: bare names like `"Util"` fail with "placeholder library X could not be resolved". Pass the fully-qualified Library Manager string: `"Standard, * (System)"`.
8. **`set_default_credentials` rejects empty username** with `ValueError`. The Zod schema enforces `username.min(1)`. For no-auth runtimes, **do not call set_credentials at all**.
9. **DUT names with `.`** are rejected by CODESYS. Don't use dots in identifier names (they're parsed as namespace separators).
10. **`set_pou_code` content not formatted for diff inspection.** Every successful call hits disk and the project file's XML changes. There's no staging. Always read before overwriting; keep prior content in conversation context.
11. **`is_simulation_mode` getter returns `None`** on the ifm AE3100 device descriptor (and probably others). The setter works; verification has to come from compile + Online -> Login working.

## Development workflow

```powershell
# Static checks (ASCII, template-reference resolution, orphan scripts)
pwsh dev/check-scripts.ps1

# Build (cleans dist/, runs tsc, copies scripts/)
npm run build

# All tests (39 currently)
npm test

# Type check only
npm run typecheck
```

After Python script edits: just rebuild; the in-process script-manager reads templates from disk every call (no cache; removed 0.6.1).

After TS edits: `/mcp` reconnect required (the host has the compiled JS in memory).

Smoke-test recipe for live verification: `dev/SMOKE_TEST.md`.

## Working preferences

- **Honest engineering review** over papering over rough edges. The user actively wants to know about regressions, capability gaps, and over-engineering.
- **Production = CODESYS V3.5 SP21 Patch 3 on Windows.** SP19 is supported; SP16 is not (the user's adjacent COR.25333 project runs SP16 but the MCP itself targets SP21).
- **Audit-then-implement, not implement-then-discover.** When something needs major change, multi-agent paper audit first. The audits in 0.6.0 / 0.6.1 / 0.6.2 caught real bugs; the agents ARE the right tool for design review.
- **Live tests catch what static analysis can't.** The 0.6.2 BLOCKERs (`PROJECT_FILE_PATH` NameError, `list_device_repository` SP21 API mismatch) only surfaced in live `/mcp` calls. Always smoke-test after big changes.
- **Tool descriptions are model-facing, not user-facing.** Keep them tight (~150 chars). Detail belongs in parameter `.describe()` or the README.
- **Don't trust the CODESYS scripting API to be uniform.** Probe attributes before reading; coerce values defensively (use `_to_unicode`, `_json_default`); RESULT_JSON wraps the structured channel so DEBUG noise doesn't break parsing.

## Deferred work (capability backlog)

From the v0.6.2 deep-test audit. None are "in progress"; flag if you start one.

- **`force_variable` / `release_force`** - bench commissioning needs forcing; `write_variable` is transient against a running app.
- **`write_variables_batch`** - atomic recipe write (currently 12 IPC round-trips per scenario change).
- **Array-slice `read_variable`** - returns first-line repr only; can't read `aROI[3..7]`.
- **`set_active_application`** - multi-application projects all silently target "first" app.
- **`generate_boot_application`** - currently only a fallback inside `download_to_device`, not standalone (already on README roadmap).
- **`configure_task`** - cycle-time / priority / POU-attachment for tasks (already on README roadmap; needed for hard-realtime targets like PPVS reject latency).
- **Value-change subscription** - polling at 10ms floor misses fast events.
- **Debugger primitives** - breakpoints, single-cycle step, force values, call-stack readback. Significant scripting-API surface, non-trivial to wire across the file-IPC channel.
- **`list_device_repository` field enrichment** - structural call works; descriptor metadata fields (`name`, `vendor`, etc.) still null on SP21 because the right `DeviceDescription` attribute names haven't been mapped. Needs live introspection.
- **`formatToolResponse(result, '')` silent-success** on `parseResultJson` failure in ~7 tools. The `parsed.error` diagnostic is dropped. Tighten to surface the parse error.
- **Result-file accumulation on timeout** - the watcher leaves orphan `.result.json` files when the TS side has already given up. Add a janitor.

## Pointer files in this repo

- `README.md` - public-facing, tool tables, troubleshooting.
- `ARCHITECTURE.md` - IPC protocol, atomic-write strategy, watcher internals.
- `CHANGELOG.md` - per-version detail; 0.6.0 substrate justification, 0.6.1 simplification cuts, 0.6.2 deep-test bug fixes.
- `dev/SMOKE_TEST.md` - manual sequence after substantive changes.
- `dev/check-scripts.ps1` - static checker (ASCII, template refs, orphans).
