import sys, scriptengine as script_engine, os, traceback

IP_ADDRESS = "{IP_ADDRESS}"
GATEWAY_NAME = "{GATEWAY_NAME}"

try:
    print("DEBUG: connect_to_device: Project='%s' IP='%s' Gateway='%s'" % (
        PROJECT_FILE_PATH, IP_ADDRESS, GATEWAY_NAME))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)

    # If the caller passed an IP, set gateway+address on the device before
    # creating the online application. set_gateway_and_address rejects an
    # empty address string, so only invoke it when an IP was provided.
    if IP_ADDRESS:
        gw = GATEWAY_NAME or "Gateway-1"
        device = None
        for child in primary_project.get_children(True):
            if hasattr(child, 'set_gateway_and_address'):
                device = child
                break
        if device is None:
            raise RuntimeError(
                "No device in the project supports set_gateway_and_address."
            )
        dev_name = getattr(device, 'get_name', lambda: '?')()
        print("DEBUG: Setting gateway='%s' address='%s' on device '%s'" % (
            gw, IP_ADDRESS, dev_name))
        device.set_gateway_and_address(gw, IP_ADDRESS)

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    print("DEBUG: Calling login() on online application...")
    if hasattr(online_app, 'login'):
        if hasattr(script_engine, 'OnlineChangeOption'):
            try:
                online_app.login(script_engine.OnlineChangeOption.TryOnlineChange)
                print("DEBUG: Logged in with TryOnlineChange option.")
            except Exception as e:
                print("DEBUG: TryOnlineChange failed, trying plain login: %s" % e)
                online_app.login()
        else:
            online_app.login()
        print("DEBUG: Login successful.")
    else:
        raise TypeError("Online application does not support login().")

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
    error_message = "Error connecting to device for project %s: %s\n%s" % (
        PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
