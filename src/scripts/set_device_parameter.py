import sys, scriptengine as script_engine, os, traceback

DEVICE_PATH = "{DEVICE_PATH}"
PARAMETER_ID_STR = "{PARAMETER_ID}"  # numeric or string
VALUE = "{VALUE}"

try:
    print("DEBUG: set_device_parameter: device='%s' param='%s' value='%s'" %
          (DEVICE_PATH, PARAMETER_ID_STR, VALUE))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not DEVICE_PATH:
        raise ValueError("Device path empty.")
    if not PARAMETER_ID_STR:
        raise ValueError("Parameter id empty.")

    device = find_object_by_path_robust(primary_project, DEVICE_PATH, "device")
    if device is None:
        raise ValueError("Device not found at path: %s" % DEVICE_PATH)

    # Resolve parameter_id - accept numeric IDs (most common in CODESYS
    # device descriptors) and fall through to the string form if the integer
    # cast fails.
    try:
        parameter_id = int(PARAMETER_ID_STR)
    except Exception:
        parameter_id = PARAMETER_ID_STR

    set_attempts = []
    success = False
    last_err = None

    # Attempt 1: device.parameter[id].value = ...
    if not success:
        try:
            params = getattr(device, 'parameter', None)
            if params is not None:
                slot = params[parameter_id]
                slot.value = VALUE
                success = True
                set_attempts.append("device.parameter[id].value")
        except Exception as e:
            last_err = e
            set_attempts.append("parameter[id].value failed: %s" % e)

    # Attempt 2: device.set_parameter_value(id, value)
    if not success and hasattr(device, 'set_parameter_value'):
        try:
            device.set_parameter_value(parameter_id, VALUE)
            success = True
            set_attempts.append("device.set_parameter_value(id, value)")
        except Exception as e:
            last_err = e
            set_attempts.append("set_parameter_value failed: %s" % e)

    # Attempt 3: device.parameters[id] = value (some versions expose a dict-like)
    if not success:
        try:
            params = getattr(device, 'parameters', None)
            if params is not None:
                params[parameter_id] = VALUE
                success = True
                set_attempts.append("device.parameters[id] = value")
        except Exception as e:
            last_err = e
            set_attempts.append("parameters[id]= failed: %s" % e)

    if not success:
        raise RuntimeError(
            "Could not write device parameter via any known API. Tried: %s. "
            "Last error: %s. Some EtherNet/IP and PROFINET adapter parameters "
            "are only writable through the IDE property pages, not via the "
            "scripting API." % (' | '.join(set_attempts), last_err)
        )

    primary_project.save()
    print("DEBUG: Project saved.")

    # Read back where possible to confirm
    readback = None
    try:
        params = getattr(device, 'parameter', None)
        if params is not None:
            slot = params[parameter_id]
            readback = _to_unicode(unicode(slot.value) if not isinstance(slot.value, unicode) else slot.value)
    except Exception:
        pass

    emit_result({
        u"device_path": _to_unicode(DEVICE_PATH),
        u"parameter_id": parameter_id if isinstance(parameter_id, int) else _to_unicode(parameter_id),
        u"value_written": _to_unicode(VALUE),
        u"value_readback": readback,
        u"set_attempts": set_attempts,
    })
    print("Parameter written: %s[%s] = %s" % (DEVICE_PATH, parameter_id, VALUE))
    print("SCRIPT_SUCCESS: Device parameter set.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error setting device parameter on '%s': %s\n%s" % (DEVICE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
