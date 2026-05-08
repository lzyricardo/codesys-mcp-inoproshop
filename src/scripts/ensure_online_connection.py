import traceback


def ensure_online_connection(primary_project):
    """Returns (online_application, target_app). Raises with an actionable
    message if create_online_application fails.

    Pre-conditions handled by the caller, NOT by this helper:
      * For a real PLC, the device must have a gateway/address configured
        (or the caller must pass ipAddress/gatewayName to connect_to_device,
        which sets it before this helper runs).
      * For simulator mode, the caller must invoke set_simulation_mode
        (enable=True) on the project first.

    Known limitation: the CODESYS scripting API can raise "Stack empty" from
    create_online_application even with simulation engaged, because the
    internal context stack is populated by IDE selection. If this happens,
    the user must click Online -> Login once in the IDE for the session
    (the project-level simulation state then sticks).
    """
    print("DEBUG: ensure_online_connection")

    target_app = primary_project.active_application
    if not target_app:
        for child in primary_project.get_children(True):
            if hasattr(child, 'is_application') and child.is_application:
                target_app = child
                break
    if not target_app:
        raise RuntimeError(
            "No active application found. Open the project in the IDE and "
            "right-click the Application node -> Set Active Application."
        )

    app_name = getattr(target_app, 'get_name', lambda: '?')()
    print("DEBUG: target_app: '%s'" % app_name)

    import scriptengine as se
    try:
        oa = se.online.create_online_application(target_app)
        if oa is not None:
            print("DEBUG: create_online_application OK")
            return oa, target_app
    except Exception as e:
        msg = (
            "create_online_application failed for '%s': %s. "
            "For simulation, call set_simulation_mode(enable=True) first; "
            "for a real PLC, ensure the gateway/address is set on the "
            "device (or pass ipAddress/gatewayName to connect_to_device). "
            "If simulation is engaged but this still raises 'Stack empty', "
            "click Online -> Login once in the IDE for this session."
        ) % (app_name, e)
        raise RuntimeError(msg)

    raise RuntimeError(
        "create_online_application returned None for '%s'." % app_name
    )
