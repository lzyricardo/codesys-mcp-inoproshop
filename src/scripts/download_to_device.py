import sys, scriptengine as script_engine, os, traceback

try:
    print("DEBUG: download_to_device script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    # Login with online change option if available, then download
    print("DEBUG: Logging in for download...")

    if hasattr(online_app, 'login'):
        if hasattr(script_engine, 'OnlineChangeOption'):
            try:
                online_app.login(script_engine.OnlineChangeOption.TryOnlineChange)
                print("DEBUG: Logged in with TryOnlineChange.")
            except Exception as e:
                print("DEBUG: Login with OnlineChangeOption failed, trying plain login: %s" % e)
                online_app.login()
        else:
            online_app.login()
    else:
        raise TypeError("Online application does not support login().")

    # Download
    print("DEBUG: Calling download()...")
    if hasattr(online_app, 'download'):
        online_app.download()
        print("DEBUG: Download complete.")
    elif hasattr(online_app, 'create_boot_application'):
        # Alternative: some versions use create_boot_application
        online_app.create_boot_application()
        print("DEBUG: Boot application created.")
    else:
        raise TypeError("Online application does not support download().")

    print("Downloaded to device for application: %s" % app_name)
    print("SCRIPT_SUCCESS: Application downloaded to device successfully.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error downloading to device for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
