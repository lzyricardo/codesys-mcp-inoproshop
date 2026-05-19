import sys, scriptengine as script_engine, os, traceback

VARIABLE_PATH = "{VARIABLE_PATH}"
VARIABLE_VALUE = "{VARIABLE_VALUE}"

try:
    print("DEBUG: write_variable script: Variable='%s', Value='%s', Project='%s'" % (VARIABLE_PATH, VARIABLE_VALUE, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not VARIABLE_PATH:
        raise ValueError("Variable path empty.")

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    # CODESYS V3 IScriptOnlineApplication does NOT expose a direct
    # `write_value`/`write` method. Variables are written by:
    #   1. Staging a value with `set_prepared_value(name, value_str)`
    #   2. Committing staged values with `force_prepared_values()`
    #
    # After force_prepared_values the variable is FORCED at the new
    # value (the runtime accepts the write and holds the variable at
    # that value until unforced). For BOOL/INT control flags this is
    # what you want. For variables the PLC program also writes to (e.g.
    # counters, outputs from FBs) forcing will freeze them — caller
    # should follow up with set_unforce_value or restart the runtime.
    #
    # All calls are routed through with_executor so the scripting
    # executor's Executing event fires and the IDE-internal
    # _executionStack is populated. Without that, set_prepared_value /
    # force_prepared_values raise 'Stack empty' from an IPC-driven
    # script the same way create_online_application does.
    if not hasattr(online_app, 'set_prepared_value') or not hasattr(online_app, 'force_prepared_values'):
        # Some very old SPs might expose a direct write_value/write.
        # Try those as a fallback if the prepared-value API isn't
        # available. (Empirically, SP14+ uses prepared values only.)
        if hasattr(online_app, 'write_value'):
            with_executor(online_app.write_value, VARIABLE_PATH, VARIABLE_VALUE)
            print("DEBUG: write_value succeeded.")
        elif hasattr(online_app, 'write'):
            with_executor(online_app.write, VARIABLE_PATH, VARIABLE_VALUE)
            print("DEBUG: write succeeded.")
        else:
            raise TypeError(
                "Online application has neither set_prepared_value/"
                "force_prepared_values nor write_value/write."
            )
    else:
        with_executor(online_app.set_prepared_value, VARIABLE_PATH, VARIABLE_VALUE)
        with_executor(online_app.force_prepared_values)
        print("DEBUG: set_prepared_value + force_prepared_values succeeded.")

    print("Variable: %s" % VARIABLE_PATH)
    print("Value Written: %s" % VARIABLE_VALUE)
    print("Application: %s" % app_name)
    print("SCRIPT_SUCCESS: Variable written successfully.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error writing variable '%s' in project %s: %s\n%s" % (VARIABLE_PATH, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
