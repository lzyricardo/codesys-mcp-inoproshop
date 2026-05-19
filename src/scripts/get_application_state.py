import sys, scriptengine as script_engine, os, traceback

try:
    print("DEBUG: get_application_state script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    # Both `application_state` and `is_logged_in` are properties on
    # the OnlineApplication. Reading them touches CODESYS internal
    # state and can hit "Stack empty" on a real PLC from an IPC
    # script, so route the reads through with_executor.
    state = "unknown"
    if hasattr(online_app, 'application_state'):
        try:
            state = str(with_executor(lambda: online_app.application_state))
        except Exception as e:
            print("WARN: Could not read application_state: %s" % e)
    else:
        print("WARN: online application does not have application_state property.")

    is_logged_in = "unknown"
    if hasattr(online_app, 'is_logged_in'):
        try:
            is_logged_in = str(with_executor(lambda: online_app.is_logged_in))
        except Exception:
            pass

    print("Application: %s" % app_name)
    print("State: %s" % state)
    print("Logged In: %s" % is_logged_in)
    print("SCRIPT_SUCCESS: Application state retrieved.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error getting application state for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
