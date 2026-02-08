import sys, scriptengine as script_engine, os, traceback

try:
    print("DEBUG: connect_to_device script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    # Login to the device
    print("DEBUG: Calling login() on online application...")

    if hasattr(online_app, 'login'):
        # Try with OnlineChangeOption if available
        if hasattr(script_engine, 'OnlineChangeOption'):
            try:
                online_app.login(script_engine.OnlineChangeOption.TryOnlineChange)
                print("DEBUG: Logged in with TryOnlineChange option.")
            except Exception as e:
                print("DEBUG: Login with OnlineChangeOption failed, trying plain login: %s" % e)
                online_app.login()
        else:
            online_app.login()
        print("DEBUG: Login successful.")
    else:
        raise TypeError("Online application does not support login().")

    # Check connection state
    state = "connected"
    if hasattr(online_app, 'application_state'):
        try:
            state = str(online_app.application_state)
        except Exception:
            pass

    print("Connected to device for application: %s" % app_name)
    print("Application State: %s" % state)
    print("SCRIPT_SUCCESS: Connected to device successfully.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error connecting to device for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
