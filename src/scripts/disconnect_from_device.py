import sys, scriptengine as script_engine, os, traceback


try:
    print("DEBUG: disconnect_from_device: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)

    target_app = primary_project.active_application
    if not target_app:
        for child in primary_project.get_children(True):
            if hasattr(child, 'is_application') and child.is_application:
                target_app = child
                break
    if not target_app:
        raise RuntimeError("No application found in project.")

    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    # disconnect MUST NOT use ensure_online_connection - that helper raises
    # if the runtime isn't reachable, which makes "disconnect when not
    # connected" fail loudly instead of being a no-op. Try create_online_
    # application directly and treat any failure as "already disconnected".
    online_app = None
    try:
        online_app = script_engine.online.create_online_application(target_app)
    except Exception as e:
        print("DEBUG: create_online_application raised: %s" % e)

    if online_app is None:
        print("Not connected to device for application: %s (no-op)." % app_name)
        print("SCRIPT_SUCCESS: Already disconnected.")
        sys.exit(0)

    if hasattr(online_app, 'logout'):
        try:
            online_app.logout()
            print("DEBUG: Logout successful.")
        except Exception as e:
            # Logout while already-disconnected is benign on most CODESYS
            # versions; surface as success but log the detail.
            print("DEBUG: logout() raised (treating as already-out): %s" % e)
    else:
        raise TypeError("Online application does not support logout().")

    print("Disconnected from device for application: %s" % app_name)
    print("SCRIPT_SUCCESS: Disconnected from device successfully.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error disconnecting from device for project %s: %s\n%s" % (
        PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
