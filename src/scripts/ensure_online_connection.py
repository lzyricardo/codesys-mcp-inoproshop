# ensure_online_connection.py
#
# Shared helper module for every online (logged-in) CODESYS V3
# operation. Exports three functions:
#
#   - ensure_online_connection(primary_project)
#       Returns (online_application, target_app). Handles missing
#       active_application, and the "Stack empty" bug that hits
#       create_online_application from IPC-driven scripts.
#
#   - with_executor(fn, *args)
#       Runs fn(*args) inside a CODESYS scripting executor frame so
#       the IDE-internal _executionStack is populated. Every online
#       op (login, start, stop, read_value, set_prepared_value,
#       force_prepared_values, create_boot_application, ...) should
#       be invoked via with_executor — without it, calls can hit
#       "Stack empty" the same way create_online_application does.
#
#   - resolve_device_address(primary_project)
#       After the caller has set_gateway_and_address with a raw IP,
#       scans the gateway and re-sets the device address to the
#       Network/Block-Driver node form (e.g. "0301.B0F7") that the
#       login layer routes by. Without this step a real PLC login
#       raises "Network error: No route to host" even when IP-level
#       routing is fine.
#
# Why all three live in one file: every online tool already includes
# `ensure_online_connection` as a script helper. Bundling the others
# here means no tool registration in server.ts has to change to pick
# up the workarounds, and there's no "did the build copy the right
# helpers" trap for future maintainers.
#
# CODESYS coverage:
#   - Verified against V3 SP16 Patch 5 (build 3.5.16.50) on an
#     ifm AE3100 IIoT Controller.
#   - The "Stack empty" workaround is V3-fragile because `_executor`
#     is a private field on `_3S.CoDeSys.ScriptDriverOnline.ScriptOnline`.
#     If a future SP renames it, with_executor degrades to a direct
#     call and ensure_online_connection surfaces an actionable
#     error pointing at the manual workaround (Online -> Login in
#     the IDE).
#   - resolve_device_address is a generic V3 fact (gateway + node
#     address) and should work for any vendor's CODESYS V3 runtime
#     (ifm, Wago, Beckhoff, B&R, generic CmpTarget, simulation).
#   - V2 is not supported (no scriptengine.online).


def _get_online_executor():
    """Resolve scriptengine.online._executor via reflection.
    Returns the executor object (an IScriptExecutor with
    ExecuteSource) or None if reflection fails. Safe to call
    repeatedly; the cost is one field lookup + one method-binding
    check.
    """
    try:
        import scriptengine as se
        import clr
        from System.Reflection import BindingFlags
        if not hasattr(se, 'online'):
            return None
        flags = (BindingFlags.Public
                 | BindingFlags.NonPublic
                 | BindingFlags.Instance)
        field = clr.GetClrType(type(se.online)).GetField('_executor', flags)
        if field is None:
            return None
        executor = field.GetValue(se.online)
        if not hasattr(executor, 'ExecuteSource'):
            return None
        return executor
    except Exception:
        return None


def with_executor(fn, *args):
    """Invoke fn(*args) inside a CODESYS scripting executor frame.

    Use this to wrap every call into `scriptengine.online` or the
    `OnlineApplication` returned by `ensure_online_connection`:

        with_executor(online_app.login, scriptengine.OnlineChangeOption.Try, False)
        with_executor(online_app.start)
        value = with_executor(online_app.read_value, 'GVL.x')
        with_executor(online_app.set_prepared_value, 'GVL.x', '42')
        with_executor(online_app.force_prepared_values)

    On CODESYS SPs where reflection into `_executor` doesn't work,
    `with_executor` falls back to calling fn directly. That path
    still works if the user has clicked Online -> Login in the IDE
    earlier in the session (which populates the stack the IDE way).

    Re-raises whatever exception the wrapped call raised; returns
    its return value otherwise.
    """
    executor = _get_online_executor()
    if executor is None:
        return fn(*args)

    import __builtin__ as _b
    _b._mcp_online_fn = fn
    _b._mcp_online_args = args
    _b._mcp_online_result = None
    _b._mcp_online_exc = None
    try:
        inner = (
            "import __builtin__ as _b\n"
            "try:\n"
            "    _b._mcp_online_result = _b._mcp_online_fn(*_b._mcp_online_args)\n"
            "except BaseException as _e:\n"
            "    _b._mcp_online_exc = _e\n"
        )
        executor.ExecuteSource(inner)
        if _b._mcp_online_exc is not None:
            raise _b._mcp_online_exc
        return _b._mcp_online_result
    finally:
        for _n in ('_mcp_online_fn',
                   '_mcp_online_args',
                   '_mcp_online_result',
                   '_mcp_online_exc'):
            try:
                delattr(_b, _n)
            except Exception:
                pass


def resolve_device_address(primary_project):
    """Re-set the project device's address from the raw IP form to
    the gateway-scan node form. See module docstring for context.

    Returns the resolved node-form address on success, or None if
    no resolution was possible (no device, no gateway, scan
    failed/empty, or set_gateway_and_address rejected the resolved
    value). When the return is None the device address is left as
    the caller set it.
    """
    import scriptengine as se

    device = None
    for child in primary_project.get_children(True):
        if (hasattr(child, 'set_gateway_and_address')
                and hasattr(child, 'get_gateway')):
            device = child
            break
    if device is None:
        return None

    try:
        gw_guid = device.get_gateway()
    except Exception as e:
        print("DEBUG: resolve_device_address: get_gateway raised: %s" % e)
        return None
    if gw_guid is None:
        return None

    if not hasattr(se, 'online'):
        return None
    target_gw = None
    try:
        for g in se.online.gateways:
            try:
                if g.guid == gw_guid:
                    target_gw = g
                    break
            except Exception:
                continue
    except Exception as e:
        print("DEBUG: resolve_device_address: gateway iteration raised: %s" % e)
        return None
    if target_gw is None:
        return None

    try:
        nodes = list(target_gw.perform_network_scan())
    except Exception as e:
        print("DEBUG: resolve_device_address: scan failed: %s" % e)
        return None

    if not nodes:
        print("DEBUG: resolve_device_address: scan returned 0 nodes")
        return None

    target = None
    if len(nodes) == 1:
        target = nodes[0]
    else:
        # Multiple devices on the gateway. Best-effort match by
        # device_name; fall back to the first node and log so the
        # caller can see what happened if it picks wrong.
        type_hint = ''
        for attr in ('get_device_identification', 'get_device_id'):
            if hasattr(device, attr):
                try:
                    info = getattr(device, attr)()
                    type_hint = str(info).lower()
                    break
                except Exception:
                    continue
        if type_hint:
            for n in nodes:
                dn = (getattr(n, 'device_name', '') or '').lower()
                if dn and dn in type_hint:
                    target = n
                    break
        if target is None:
            target = nodes[0]
            print("DEBUG: resolve_device_address: %d nodes; "
                  "no name match, using first ('%s')" % (
                      len(nodes),
                      getattr(target, 'device_name', '?')
                  ))

    addr = getattr(target, 'address', None)
    if not addr:
        return None

    try:
        device.set_gateway_and_address(target_gw.name, addr)
        print("DEBUG: resolve_device_address: '%s' -> node '%s'" % (
            getattr(target, 'device_name', '?'), addr
        ))
        return addr
    except Exception as e:
        print("DEBUG: resolve_device_address: "
              "set_gateway_and_address failed: %s" % e)
        return None


def ensure_online_connection(primary_project):
    """Return (online_application, target_app) for the given project.

    Handles "no active application" and the CODESYS V3 "Stack empty"
    bug described in the module docstring. Raises a `RuntimeError`
    with actionable text if neither the direct path nor the
    ExecuteSource fallback can produce an online application.
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
            "No application found in the project. Right-click an "
            "Application node in the IDE and choose 'Set Active "
            "Application'."
        )

    app_name = getattr(target_app, 'get_name', lambda: '?')()
    print("DEBUG: target_app: '%s'" % app_name)

    # Make active_application authoritative. Some "Stack empty"
    # paths trace back to project/active-app disagreement; this
    # assignment is idempotent when the right app is already active.
    try:
        primary_project.active_application = target_app
    except Exception as _e:
        print("DEBUG: could not set active_application: %s" % _e)

    import scriptengine as se
    if not hasattr(se, 'online'):
        raise RuntimeError(
            "This CODESYS version does not expose 'scriptengine.online'. "
            "Need SP14+ with the Python scripting API."
        )

    # 1. Direct call. Succeeds when the executor stack is already
    #    populated (e.g. user clicked Online -> Login in the IDE
    #    earlier this session, or the calling context is already
    #    inside an ExecuteSource frame).
    try:
        oa = se.online.create_online_application(target_app)
        if oa is not None:
            print("DEBUG: create_online_application OK (direct)")
            return oa, target_app
    except Exception as direct_err:
        msg = str(direct_err)
        if 'Stack empty' not in msg:
            # Genuine error (auth/network/version/...). Surface as-is.
            raise RuntimeError(
                "create_online_application failed for '%s': %s. For "
                "simulation, call set_simulation_mode(enable=True) "
                "first; for a real PLC, ensure the gateway/address is "
                "set on the device." % (app_name, direct_err)
            )
        print("DEBUG: Stack empty on direct call; falling back to ExecuteSource")

    # 2. ExecuteSource fallback. Drives the executor lifecycle so
    #    the inner source sees a populated _executionStack.
    executor = _get_online_executor()
    if executor is None:
        raise RuntimeError(
            "create_online_application raised 'Stack empty' and the "
            "ExecuteSource fallback is unavailable (scriptengine."
            "online._executor field could not be resolved via "
            "reflection — likely renamed in this CODESYS version). "
            "Manual workaround: click Online -> Login once in the "
            "IDE for this session."
        )

    try:
        oa = with_executor(se.online.create_online_application, target_app)
    except Exception as fallback_err:
        raise RuntimeError(
            "create_online_application failed for '%s' even via "
            "ExecuteSource: %s. Manual workaround: click "
            "Online -> Login once in the IDE for this session." % (
                app_name, fallback_err
            )
        )

    if oa is None:
        raise RuntimeError(
            "create_online_application returned None for '%s'." % app_name
        )

    print("DEBUG: create_online_application OK (via ExecuteSource)")
    return oa, target_app
