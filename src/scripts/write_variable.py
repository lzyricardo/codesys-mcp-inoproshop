import sys, scriptengine as script_engine, os, traceback

VARIABLE_PATH = "{VARIABLE_PATH}"
VARIABLE_VALUE = "{VARIABLE_VALUE}"

try:
    print("DEBUG: write_variable script: Variable='%s', Value='%s', Project='%s'" % (VARIABLE_PATH, VARIABLE_VALUE, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not VARIABLE_PATH: raise ValueError("Variable path empty.")

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    # Write the variable value
    if hasattr(online_app, 'write_value'):
        try:
            online_app.write_value(VARIABLE_PATH, VARIABLE_VALUE)
            print("DEBUG: write_value succeeded.")
        except Exception as e:
            print("DEBUG: write_value failed: %s" % e)
            raise

    elif hasattr(online_app, 'write'):
        try:
            online_app.write(VARIABLE_PATH, VARIABLE_VALUE)
            print("DEBUG: write succeeded.")
        except Exception as e:
            print("DEBUG: write failed: %s" % e)
            raise

    else:
        raise TypeError("Online application does not support write_value() or write().")

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
