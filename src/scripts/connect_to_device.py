import sys, scriptengine as script_engine, os, traceback

IP_ADDRESS = "{IP_ADDRESS}"
GATEWAY_NAME = "{GATEWAY_NAME}"

try:
    print("DEBUG: connect_to_device: Project='%s' IP='%s' Gateway='%s'" % (
        PROJECT_FILE_PATH, IP_ADDRESS, GATEWAY_NAME))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)

    # If the caller passed an IP, set the device's gateway/address and
    # then resolve to the Network/Block-Driver node form via gateway
    # scan. set_gateway_and_address stores the raw IP encoded as
    # "0xxx.0xxx.0xxx.0xxx", but CODESYS V3 login routes by node form
    # (e.g. "0301.B0F7"). Without the scan/resolve step the login layer
    # raises "Network error: No route to host" even when IP routing is
    # fine. See resolve_device_address.py for the full explanation.
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

        node_addr = resolve_device_address(primary_project)
        if node_addr:
            print("DEBUG: device address resolved to node form '%s'" % node_addr)
        else:
            # Scan didn't help — log and continue. Login may still
            # succeed if a stale cached resolution survives, or if this
            # CODESYS version routes by IP directly.
            print("DEBUG: address resolution returned no node; "
                  "leaving IP-encoded form as-is")

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    if not hasattr(online_app, 'login'):
        raise TypeError("Online application does not support login().")

    # CODESYS V3 login signature is `login(OnlineChangeOption, bool)`.
    # Enum values on `scriptengine.OnlineChangeOption` are Force, Keep,
    # Never, Try. The 2nd arg controls whether differently-named
    # applications already on the PLC are deleted (False = keep them).
    # Call via with_executor so the scripting executor lifecycle is
    # driven, otherwise login can also hit "Stack empty" the same way
    # create_online_application does.
    print("DEBUG: Calling login...")
    if hasattr(script_engine, 'OnlineChangeOption'):
        with_executor(
            online_app.login,
            script_engine.OnlineChangeOption.Try,
            False,
        )
        print("DEBUG: Logged in (OnlineChangeOption.Try, keep_foreign=False).")
    else:
        # Older CODESYS SPs without the public OnlineChangeOption enum.
        with_executor(online_app.login)
        print("DEBUG: Logged in (no OnlineChangeOption available).")

    state = "connected"
    if hasattr(online_app, 'application_state'):
        try:
            state = str(with_executor(lambda: online_app.application_state))
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
