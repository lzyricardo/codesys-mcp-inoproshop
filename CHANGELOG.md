# Changelog

## 0.6.2 — 2026-05-09

Bug-fix release after a multi-agent + live-test deep audit of v0.6.1.

### Fixed

- **`inspect_device_node`, `create_project_archive`, and the `pou-code` resource were broken.** All three scripts referenced `PROJECT_FILE_PATH` but only worked because their helper chain previously included `ensure_project_open.py` (which declares the placeholder). When they switched to `require_project_open` for read-only safety, the placeholder declaration disappeared with no replacement, producing `NameError: name 'PROJECT_FILE_PATH' is not defined` on every call. Caught by live test, not by the static `dev/check-scripts.ps1` checker. Fixed by mirroring `ensure_project_open`'s convention - `require_project_open.py` now also declares the placeholder at module scope.
- **`list_device_repository` returned 2045 entries with all descriptor fields null.** SP21's `ScriptDeviceRepository` is not iterable directly; the listing comes from `repo.get_all_devices()` (now probed first), which returns lightweight `DeviceID` handles - not full descriptors. Each entry now also enriches via `repo.get_device_description(deviceID)` to pull `name`, `vendor`, `category`, `description`. (Note: enrichment may still return null for some entries on SP21 - the descriptor object's exact attribute names continue to vary; the structural call is reliable.)
- **`dist/mutation-tracker.*` orphan build artefacts** (.js, .d.ts, .js.map, .d.ts.map) were left behind by 0.6.1's `tsc + cpSync` build because there was no `dist` clean step. Would have been published to npm. Build script now runs `npm run clean` first; new `clean` script wipes `dist/` before `tsc` regenerates it.
- **Test asserted cache behaviour against a removed cache.** `tests/unit/script-manager.test.ts` had a `'cache hit - second load returns same content'` test that passed by accident after the cache was deleted in 0.6.1 (Vitest's `toBe` on identical short strings can pass via Node's string interning). Renamed to `'two reads of the same template return identical content'` and switched to `toEqual` so the assertion describes the actual contract.
- **`ARCHITECTURE.md:168` claimed "reads `.py` files from disk with caching".** Stale after 0.6.1's cache removal. Fixed.

### Known issues NOT fixed in this release (documented for awareness)

- **Project-lock contention** when CODESYS isn't running persistently. Each tool call spawns a `--noUI` headless instance; concurrent tool calls and prior orphans contend for the project file lock and produce `StandardError: The selected project is currently in use` (MEMORY.md pitfall #5). Workarounds: keep persistent mode running, or pass `--kill-existing-codesys` to wipe orphans on launch.
- **`formatToolResponse(result, '')` silent-success on `parseResultJson` failure** in ~7 tools (`search_code`, `read_variable`, `monitor_variables`, `list_device_repository`, `inspect_device_node`, `add_device`, `set_device_parameter`). When the script ran (`SCRIPT_SUCCESS` in stdout) but the RESULT_JSON marker block was malformed, the caller sees an empty success response instead of an error. The diagnostic in `parsed.error` is dropped. Tracked.
- **`list_device_repository` field enrichment is partial.** Structural call works; some descriptors on SP21 don't expose name/vendor under the probed attribute names. Need a sample inspection of a real `DeviceDescription` object on the live runtime to map field names. Tracked.
- **Capability gaps** flagged by the audit (no priority order): `force_variable` / `release_force` (bench commissioning), `write_variables_batch` (recipe atomic write), array-slice `read_variable`, `set_active_application` (multi-app projects), `generate_boot_application` (already on roadmap), `configure_task` (already on roadmap), value-change-event subscription, debugger primitives.

## 0.6.1 — 2026-05-08

Simplification pass after a multi-agent over-engineering audit. ~270 lines removed. No public-API changes — all 39 tests pass.

### Cuts

- **Removed `MutationTracker`** (src/mutation-tracker.ts deleted, ~90 lines across server.ts). The per-project compile/mutation timestamping was lossy bandaid masquerading as substrate: it tracked only TS-side tool calls, missed IDE edits and watcher restarts, and the value it produced was a single warning string ("WARN: Project was modified Xs ago") that a static note in `get_compile_messages`'s description delivers identically. Tools that previously routed through `formatMutatorResponse` now go through `formatToolResponse` directly.
- **Removed the script-template cache** (src/script-manager.ts, ~30 lines). The Map of file contents solved an imaginary perf problem (~1ms savings per call vs. 100ms+ CODESYS calls); its only user-visible artifact was the `CODESYS_MCP_NO_CACHE` env var that existed because the cache broke template iteration during dev. `loadTemplate()` now reads from disk every call.
- **Deleted dead `PouTypeEnum` and `ImplementationLanguageEnum`** at server.ts:20-26 — declared but never referenced (`create_pou` redeclares inline).
- **Deduplicated `_json_default`** in `compile_project.py` and `get_compile_messages.py` — `_text_utils.py` already provides it via the helper-prepend chain.
- **Stripped narrative `DEBUG:` prints** from `find_object_by_path.py` (the most-called helper in the codebase, was emitting 5-10 lines per CRUD tool invocation) and `ensure_project_open.py` (~18 flow-trace prints + commented-out dead code blocks). All `WARN:` and `ERROR:` diagnostic prints retained.
- **Trimmed verbose tool descriptions** for `add_device`, `set_device_parameter`, `find_references`, `rename_symbol`, `monitor_variables`, `list_device_repository`, `inspect_device_node`, `map_io_channel`, `search_code`. Each was 300-700 chars and loaded into every model turn; trimmed to ~150 chars (~3-4K tokens off the tool-list payload). Detail moved to parameter `.describe()` strings.

### Not done (deliberately deferred)

- **Tool-registration `simpleTool()` helper** that would collapse ~12 mutator registrations into a 6-line declaration. ~600-line cut estimated, but introduces a generalised abstraction and the bespoke shape of `compile_project` / `read_variable` / `monitor_variables` / `search_code` / `rename_symbol` would need to remain custom anyway. Held for a future pass once the helper's shape is clearer.
- **Stripping per-script `try/except SCRIPT_ERROR; sys.exit(1)`** boilerplate. The watcher catches uncaught exceptions, but `SCRIPT_SUCCESS` is load-bearing (server.ts checks `result.output.includes('SCRIPT_SUCCESS')`); reworking is invasive enough to merit its own release.
- **Multi-version API probes** in `add_device`, `set_device_parameter`, `list_device_repository`, `create_project_archive`. Auditor flagged some as speculative; not pruned without grounding in actual user reports of CODESYS version divergence.
- **`ExecutorProxy.swapVersion`** monotonic-counter logic. Small win (~25 lines) and the race it guards is hard to test for; left in place.

## 0.6.0 — 2026-05-08

Substrate + capability release. Closes the five remaining still-open bugs from 0.5.x and ships ten new tools (search_code, find_references, rename_symbol, monitor_variables, create_project_archive, inspect_device_node, add_device, set_device_parameter, list_device_repository, map_io_channel).

### Substrate primitives (foundational, used by multiple tools)

- **`ExecutorProxy` (src/executor-proxy.ts)** — stable proxy reference replacing the `let executor` rebind. `executeScript` awaits a readiness promise then delegates; `swap()` and `swapNow()` mutate the inner without breaking captured closures. Closes B3 (background-launcher 30s race) and gives long-lived tools (monitor_variables) a clean substrate.
- **`require_project_open` helper (src/scripts/require_project_open.py)** — read-only sibling of `ensure_project_open`. Raises if the requested project isn't currently primary; never opens or switches. Used by resource handlers (B1 fix) and read-only tools (create_project_archive, inspect_device_node).
- **`### RESULT_JSON ###` marker protocol (src/scripts/_text_utils.py emit_result + src/result-parser.ts)** — standardised structured-result channel for scripts. Pairs with `parseResultJson<T>()` on the Node side. Closes B4 (read_variable multi-line truncation) and underpins every new structured-output tool.
- **`MutationTracker` (src/mutation-tracker.ts)** — per-project compile/mutation timestamps in TS memory. Mutators call `markMutated`; `compile_project` calls `markCompiled`; `get_compile_messages` prepends a "stale, run compile_project" warning when mutations followed the last compile. Closes B2.
- **`atomic_write` via .NET `File.Replace` (src/scripts/watcher.py)** — atomic NTFS rename replacing the os.remove+os.rename pair, with a retry-loop fallback for AV-locked files. Closes B5.

### New tools (capability adds)

- **`search_code`** — regex (or literal substring) search across every POU/Method/Property/DUT/GVL declaration and implementation body. Returns `{path, section, line, col, text}` hit list via RESULT_JSON. Reports skipped graphical bodies so callers know coverage.
- **`find_references`** — TS-only wrapper around `search_code` with a word-boundary regex (`\bsymbol\b`). Single source of truth for traversal — does not duplicate the script.
- **`rename_symbol`** — best-effort textual rename across all POU bodies. Two-phase write: phase 1 plans every change, phase 2 applies all-or-rollback. dryRun=true by default. Refuses IEC keywords as the new name. Project save() runs only when every section rewrites cleanly; partial failures DON'T save (caller reopens to discard in-memory state).
- **`monitor_variables`** — sample one or more PLC variables at a fixed interval over a bounded duration. Returns the timeseries via RESULT_JSON. Duration capped at 60s, interval floor 10ms. Anti-drift sample loop (`next_t = start_t + n*interval`).
- **`create_project_archive`** — wraps `primary.save_archive(path, comment, content)` with multi-version probing. Saves the project before archiving so unsaved edits are captured. Read-only with respect to project state (uses require_project_open). Includes/excludes libraries via `includeLibraries` / `includeCompiledLibraries` flags.
- **`add_device` (EXPERIMENTAL)** — wrap `parent.add_device(name, type, id, version)` with multi-version signature probing and post-hoc child enumeration for SP16's None-return path. Marked EXPERIMENTAL — `deviceType` / `deviceId` are unvalidated and wrong ids produce wrong-but-valid project nodes. Recommended workflow: add one device manually in IDE, run `inspect_device_node` to capture ids, then automate.
- **`set_device_parameter` (EXPERIMENTAL)** — wrap `device.parameter[id].value =` with fallbacks to `set_parameter_value` / `parameters[id]`. Marked EXPERIMENTAL — many fieldbus parameters are GUI-only. Pair with `inspect_device_node` to discover writable parameters.
- **`inspect_device_node`** — read-only introspection of a device node: descriptor metadata (device_id, type, version, vendor when exposed), parameter list with current values + types, and child sub-devices. Substrate for the device-tree mutation tools.
- **`list_device_repository`** — read-only enumeration of every device descriptor installed in the local CODESYS Device Repository. Probes `script_engine.device_repository` / `device_descriptions` / `devicerepository` and surfaces `{name, vendor, device_type, device_id, version, description, category}` per entry, with optional case-insensitive `vendor` and `nameContains` substring filters and a `maxResults` cap. Closes the validation gap for `add_device` (callers can now look up canonical ids instead of guessing).
- **`map_io_channel`** — bind (or clear) a fieldbus I/O channel to a global variable symbol. Resolves the channel by slash-separated name path (`Inputs/Byte 0/Bit 3`) or numeric child indices (`0/3`) for descriptors that don't expose stable channel names. Tries `channel.set_variable(name)`, then `channel.variable = name`, then `channel.symbol = name` to cover descriptor variants. `clearBinding: true` removes an existing binding (variableName ignored). RESULT_JSON returns `{channel_name, channel_class, variable_before, variable_after, cleared, resolution_attempts, set_attempts}`.

### Bug fixes leveraging substrate

- **B1: Resource handlers no longer silently switch projects.** Both `pou-code` and `project-structure` resources now use `require_project_open` instead of `ensure_project_open`.
- **B2: get_compile_messages warns when stale.** Mutators (set_pou_code, create_*, delete_object, rename_object, add_library, set_simulation_mode, etc.) call `markMutated`; `compile_project` calls `markCompiled`; `get_compile_messages` prepends a clear staleness warning when mutated > compiled.
- **B3: Launcher executor swap is race-free.** ExecutorProxy serialises tool calls behind a readiness promise around the auto-launch transition.
- **B4: read_variable returns multi-line struct values intact.** Switched from regex `/Value:\s*(.+)/` to RESULT_JSON marker block; `value`, `type`, `raw`, `application` returned structurally.
- **B5: atomic_write is atomic on Windows NTFS.** `.NET File.Replace` for existing destinations, `File.Move` for new files, retry-loop fallback for AV-locked files.

### Cut from this release

- **C5 export_project_xml** cut by the implementation-order analyst — overlaps with `create_project_archive` for backup/diff use cases. Track on roadmap.

### Tests

- 39/39 tests pass (4 new pyEscape coverage tests carried over from 0.5.1).
- Static checks (`dev/check-scripts.ps1`): all 41 scripts ASCII-clean, all template references resolve.

## 0.5.2 — 2026-05-08

Second adversarial-review pass. Tightens schemas, fixes path-resolution corruption, replaces a too-broad delete allowlist with exact-path matching, and stops `set_pou_code` from silently overwriting code with empty strings.

### Schema hardening (Zod)
- `create_pou.type` is now `z.enum(['Program', 'FunctionBlock', 'Function'])` (was `z.string()`).
- `create_pou.language` is now `z.enum(['ST', 'LD', 'FBD', 'SFC', 'IL', 'CFC'])`.
- `create_pou.name` and `parentPath` now require `min(1)`.
- `create_dut.dutType` is now `z.enum(['Structure', 'Enumeration', 'Union', 'Alias'])`.
- `create_dut.name` and `parentPath` now require `min(1)`.
- `start_stop_application.action` is now `z.enum(['start', 'stop'])` (was `z.string()`).
- `set_pou_code.pouPath` now requires `min(1)`.

### Fixed
- **`find_object_by_path_robust` no longer corrupts namespaced names.** Previously `path.replace('.', '/')` was applied unconditionally, so a path like `Application/MyLib.MyType` got split into 4 parts and the find always returned `None`. Now `.` is only treated as a separator when the input has no `/` at all.
- **`find_object_by_path_robust` recursive fallback no longer silently picks the first match.** When the project tree contains multiple objects with the same name, the helper used to return `[0]` from `find(part_name, True)` which could resolve to the wrong object. Now ambiguous matches return `None` with a clear error.
- **`find_object_by_path_robust` final-name verification uses normalised path parts.** The previous `full_path.split('/')[-1]` returned the whole input when `.` was used as a separator, causing successful traversals to be reported as name-mismatch errors.
- **`delete_object` allowlist is now an exact-path match, not a last-segment match.** Prior implementation false-positively refused legitimate user objects whose final name happened to match a system node (e.g. `Application/MyFolder/MainTask` for a user folder named `MainTask`). The new check uses an explicit set of canonical system paths.
- **`set_pou_code` no longer silently overwrites with empty string.** Empty-string values for `declarationCode` or `implementationCode` are now treated the same as omitted (don't change). Previously only `=== undefined` was checked, so an empty string from a buggy client wiped the section. New `UPDATE_DECL` / `UPDATE_IMPL` flag params explicitly mark which sections to update.
- **`ensure_project_open` final RuntimeError now includes the last underlying error.** Previously the helper raised a generic "after 3 attempts" message; now it appends the most recent `projects.open()` exception text so callers can distinguish "file locked", "file missing", "version mismatch", etc.

### Known issues (still not fixed; documented for awareness)
- Resource handler can switch projects via `ensure_project_open` (treat resource URIs as potentially state-mutating).
- Compile message store can go stale after `set_pou_code` (auto-saves but doesn't invalidate cache); call `compile_project` again to refresh.
- `read_variable` regex captures only the first line; multi-line struct values get truncated.
- Background-launcher swap mid-tool-call has a 30s race window where headless and persistent executors can both be live.
- Watcher `atomic_write` is not strictly atomic on Windows (`os.remove` + `os.rename`).

## 0.5.1 — 2026-05-08

Hardening pass after multi-agent adversarial review. Centralizes Python escaping, blocks destructive deletes, and fixes additional CODESYS scripting API mismatches.

### Security / correctness
- **Central Python string escape in `ScriptManager.interpolate()`**. Every `{KEY}` placeholder is now Python-escaped before substitution (backslashes, double/single quotes, newlines, tabs). This closes a class of injection bugs where a `"` or newline in a user-controlled identifier (POU name, variable path, library name, password) could break out of the string literal in the generated IronPython source. Use `{KEY:raw}` for the rare case where a value should bypass escaping (currently only `set_pou_code`'s declaration/implementation blocks no longer need it - the `:raw` form is provided as an escape hatch).
- **`delete_object` allowlist.** The tool now refuses to delete system nodes (`Application`, `Device`, `Plc Logic`, `Library Manager`, `Project Settings`, `Task Configuration`, `MainTask`, `Communication`, `Ethernet`, `SoftMotion General Axis Pool`, `__VisualizationStyle`) and any path with no `/` separator. Pre-fix, deleting these silently bricked the project.
- **Server.ts no longer pre-escapes `set_pou_code` content.** The redundant `\\` and `"""` escape that used to live at the call site is now handled by `interpolate()` for all params.

### Fixed
- `create_folder.py` no longer requires `create_folder()` to return a non-`None` object. SP16 returns `None` on success and the new folder must be discovered by walking the parent's children. The script now does that and only fails when post-creation enumeration also doesn't find the folder.
- Raw-string templates (`r"{KEY}"`) in `create_project.py`, `ensure_project_open.py`, `get_project_structure.py`, and `watcher.py` converted to regular strings (`"{KEY}"`). Raw strings can't survive central escaping; the regular form is now consistent across all templates.
- `launcher.ts` no longer pre-escapes `IPC_BASE_DIR` - `interpolate()` handles it.

### Tests
- 4 new unit tests in `tests/unit/script-manager.test.ts` covering pyEscape behavior: backslashes, triple quotes, single quotes, newlines, `:raw` bypass, and `$` not being a regex backref.
- E2E tests updated to expect Python-escaped paths in generated source.

### Known issues surfaced (not fixed in this release)
- **Resource URIs can silently switch projects** when the requested project differs from the currently-open one (`ensure_project_open` opens the new one, closing any unsaved work). Resources should be read-only; tracked for a future fix that adds a `verify-only` mode.
- **`atomic_write` is not strictly atomic on Windows.** The `os.remove` + `os.rename` pair leaves a window where readers see no file. Rare in practice but worth replacing with `os.replace` (Python 3.3+; for IronPython 2.7, retry-rename loop).
- **CODESYS doesn't enforce IEC identifier length** at create time; very long names are accepted and may surface as cryptic compile errors later. Consider a TS-side length cap (~24-32 chars) for new POU/DUT/GVL names.

## 0.5.0 — 2026-05-08

New tools and parameters for runtime work without dedicated hardware.

### Added
- **`set_simulation_mode` tool** — toggle device-level simulation mode on/off. Run before `connect_to_device` when no physical PLC is available. Supports a `verbose` flag (default `false` returns a terse summary; `true` returns the full script output).
- **`set_credentials` tool** — set the default username/password used for subsequent PLC logins. Username must be non-empty; for no-auth runtimes do not call this tool.
- **`connect_to_device` `ipAddress` and `gatewayName` parameters** — when `ipAddress` is provided, `set_gateway_and_address` is called on the device before login. `gatewayName` defaults to `Gateway-1` (the CODESYS install default).
- **`download_to_device` `mode` parameter** — `auto` (default; try online change, fall back to full), `online_change` (fail if rejected), or `full` (skip online change).
- **`--kill-existing-codesys` CLI flag** — opt-in: kills any pre-existing `CODESYS.exe` before launching. Off by default so an external IDE session is never killed.
- **`CODESYS_MCP_NO_CACHE` environment variable** — set to `1` to disable the in-memory Python script template cache. Useful for iterating on script templates without restarting the server.

### Changed
- **Cache is ON by default again** (was temporarily off during dev). Opt out via `CODESYS_MCP_NO_CACHE=1`.
- **Launcher uses `spawn(exe, args)` instead of `spawn(cmd, [], { shell: true })`** so the tracked PID is the actual `CODESYS.exe` PID rather than a wrapping `cmd.exe` shell PID. Health-check and shutdown paths now operate on the right process.
- **`connect_to_device` timeout reduced from 240s back to 60s** (the 240s was a debug bump; the IDE `Login` command path that needed it is no longer invoked from script).
- **`watcher.py` primary-thread `WaitOne` reduced from 240s back to 120s** for the same reason.

### Fixed
- Removed the IDE `Login` command invocation chain from `ensure_online_connection` — it hung the CODESYS primary thread indefinitely. The helper now calls `online.create_online_application` directly and returns an actionable error if it fails (with hints to enable simulation, set the gateway/address, or click `Online -> Login` in the IDE for the session if the scripting API hits its known `Stack empty` limitation).
- Em-dashes purged from `set_simulation_mode.py` (IronPython 2.7 source must stay ASCII-only without a UTF-8 coding header).
- `create_folder.py` now passes the folder name as a positional argument (CODESYS SP16 raised `TypeError: create_folder() got an unexpected keyword argument 'name'` with the previous keyword-arg call).
- `disconnect_from_device.py` no longer goes through `ensure_online_connection`. Disconnecting when not connected is now a no-op success rather than a `Stack empty` failure.
- `add_library.py` reports the actual API failure (e.g. "placeholder library X could not be resolved") instead of masking it with the generic "Library Manager does not support known add methods" message.
- `set_credentials` now Zod-validates `username.min(1)` — CODESYS rejects empty usernames with `ValueError`.

### Encoder fixes (carried forward from 0.4.x)
- Bulk POU read (`get_all_pou_code`), `get_compile_messages`, `compile_project`, `list_project_libraries`, and the single-POU resource read all handle non-ASCII content (e.g. cp1252 bytes for `§`) via the shared `_text_utils._to_unicode` helper plus `json.dumps(..., ensure_ascii=False)` and utf-8 byte-stdout writes. IronPython 2.7's default JSON encoder path crashes on such input.

## 0.4.x

Internal dev iterations. See git history.
