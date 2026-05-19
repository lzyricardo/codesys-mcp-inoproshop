import sys, scriptengine as script_engine, os, traceback

APP_ACTION = "{APP_ACTION}"

try:
    print("DEBUG: start_stop_application script: Action='%s', Project='%s'" % (APP_ACTION, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not APP_ACTION:
        raise ValueError("Action empty.")

    action_lower = APP_ACTION.lower()
    if action_lower not in ('start', 'stop'):
        raise ValueError("Invalid action '%s'. Must be 'start' or 'stop'." % APP_ACTION)

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    # start/stop are online operations that can also hit "Stack empty"
    # on a real PLC when called from a pure IPC-driven script. Route
    # them through with_executor so the scripting executor fires
    # Executing/Executed and the IDE-internal _executionStack is
    # populated. See ensure_online_connection.py for the full story.
    if action_lower == 'start':
        if not hasattr(online_app, 'start'):
            raise TypeError("Online application does not support start().")
        print("DEBUG: Calling start()...")
        with_executor(online_app.start)
        print("DEBUG: Application started.")
    else:
        if not hasattr(online_app, 'stop'):
            raise TypeError("Online application does not support stop().")
        print("DEBUG: Calling stop()...")
        with_executor(online_app.stop)
        print("DEBUG: Application stopped.")

    state = "unknown"
    if hasattr(online_app, 'application_state'):
        try:
            state = str(with_executor(lambda: online_app.application_state))
        except Exception:
            pass

    print("Action: %s" % APP_ACTION)
    print("Application: %s" % app_name)
    print("State After: %s" % state)
    print("SCRIPT_SUCCESS: Application %s executed successfully." % action_lower)
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error executing %s for project %s: %s\n%s" % (APP_ACTION, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
