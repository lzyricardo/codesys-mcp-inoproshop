# Smoke test sequence

Manual sequence to run after a substantive change to the server, watcher,
or any tool script. Static checks (ASCII, template references) live in
`dev/check-scripts.ps1`; this file covers the runtime side that requires
a live CODESYS instance.

## Pre-flight

```powershell
pwsh dev/check-scripts.ps1   # static checks
npm run build                # tsc + script copy
```

Then either reconnect the MCP server (`/mcp` in Claude Code) or restart
the host so the new build is loaded. With cache ON (the default), script
template edits also need the reconnect.

## Smoke sequence

A test project with at least one Application + Device must already exist.
The dev project for this repo is `TipTopCompletenessV2.project`.

| # | Tool call | Expected |
|---|-----------|----------|
| 1 | `get_codesys_status` | `state: ready`, non-null `pid` |
| 2 | `open_project(projectFilePath="<dev-project>")` | `Project opened` |
| 3 | `get_all_pou_code(projectFilePath="<dev-project>")` | Full POU list. Regression test for the IronPython 2.7 cp1252 encoder bug; non-ASCII chars (e.g. `§`) preserved |
| 4 | Read resource `codesys://project/<encoded-path>/pou/<X>/code` | Single POU returns; non-ASCII chars preserved |
| 5 | `list_project_libraries(projectFilePath="<dev-project>")` | Library list, version info |
| 6 | `compile_project(projectFilePath="<dev-project>")` | 0 errors |
| 7 | `get_compile_messages(projectFilePath="<dev-project>")` | Empty error list |
| 8 | `set_simulation_mode(projectFilePath="<dev-project>", enable=true)` | `Simulation mode enabled on device. Current state: True` |
| 9 | `set_credentials(username="", password="")` | `Default credentials set (user='').` |
| 10 | `set_simulation_mode(projectFilePath="<dev-project>", enable=false)` | `Simulation mode disabled on device. Current state: False` |

If the dev project also has a real PLC reachable, also exercise:

| # | Tool call | Expected |
|---|-----------|----------|
| 11 | `connect_to_device(projectFilePath="<dev-project>", ipAddress="<plc-ip>")` | `Connected to device for application: <name>` |
| 12 | `get_application_state(projectFilePath="<dev-project>")` | `Application: <name>`, `State: <state>` |
| 13 | `disconnect_from_device(projectFilePath="<dev-project>")` | OK |

## Notes

- `connect_to_device` is known to fail with `Stack empty` after enabling
  simulation through the scripting API — see README's troubleshooting
  section. Workaround: click `Online -> Login` once in the IDE per session.
- After step 6 fails for any reason, do not proceed past step 7.
