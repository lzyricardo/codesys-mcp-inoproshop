import sys, scriptengine as script_engine, os, traceback

PARENT_DEVICE_PATH = "{PARENT_DEVICE_PATH}"
DEVICE_NAME = "{DEVICE_NAME}"
DEVICE_TYPE_STR = "{DEVICE_TYPE}"  # numeric string (CODESYS device type id)
DEVICE_ID_STR = "{DEVICE_ID}"  # numeric string (CODESYS device id) or empty
DEVICE_VERSION = "{DEVICE_VERSION}"  # version string, may be empty

try:
    print("DEBUG: add_device: parent='%s' name='%s' type='%s' id='%s' ver='%s'" %
          (PARENT_DEVICE_PATH, DEVICE_NAME, DEVICE_TYPE_STR, DEVICE_ID_STR, DEVICE_VERSION))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not DEVICE_NAME:
        raise ValueError("Device name empty.")
    if not PARENT_DEVICE_PATH:
        raise ValueError("Parent device path empty.")

    try:
        device_type = int(DEVICE_TYPE_STR)
    except Exception:
        raise ValueError("deviceType must be a numeric CODESYS device type id (e.g. 18 for EtherNet/IP adapter).")

    try:
        device_id = int(DEVICE_ID_STR) if DEVICE_ID_STR else None
    except Exception:
        raise ValueError("deviceId must be numeric or empty.")

    parent_obj = find_object_by_path_robust(primary_project, PARENT_DEVICE_PATH, "parent device")
    if parent_obj is None:
        raise ValueError("Parent device not found at path: %s" % PARENT_DEVICE_PATH)
    if not hasattr(parent_obj, 'add_device'):
        raise TypeError(
            "Object at '%s' (type %s) does not expose add_device. "
            "The scripting API only allows adding devices under nodes that "
            "act as fieldbus parents." % (PARENT_DEVICE_PATH, type(parent_obj).__name__)
        )

    # CODESYS scripting add_device varies a bit by version. Try the most
    # common signatures in order. The DeviceIdentification class is the
    # canonical wrapper but isn't always available - fall through to the
    # tuple form when missing.
    new_device = None
    last_err = None
    attempts = []

    # Attempt 1: positional (name, type, id, version)
    try:
        if device_id is not None and DEVICE_VERSION:
            new_device = parent_obj.add_device(DEVICE_NAME, device_type, device_id, DEVICE_VERSION)
        elif device_id is not None:
            new_device = parent_obj.add_device(DEVICE_NAME, device_type, device_id)
        else:
            new_device = parent_obj.add_device(DEVICE_NAME, device_type)
        attempts.append("positional(name, type[, id[, version]])")
    except TypeError as e:
        last_err = e
        attempts.append("positional failed: %s" % e)

    # Attempt 2: kwargs (name=..., device_id=..., type=..., version=...)
    if new_device is None:
        try:
            kwargs = {'name': DEVICE_NAME, 'type': device_type}
            if device_id is not None:
                kwargs['device_id'] = device_id
            if DEVICE_VERSION:
                kwargs['version'] = DEVICE_VERSION
            new_device = parent_obj.add_device(**kwargs)
            attempts.append("kwargs(name, type, device_id, version)")
        except TypeError as e:
            last_err = e
            attempts.append("kwargs failed: %s" % e)

    if new_device is None:
        # Attempt 3: post-hoc child enumeration. SP16's add_device returns
        # None on success and the new node has to be discovered.
        try:
            for child in parent_obj.get_children(False):
                child_name = getattr(child, 'get_name', lambda: '')()
                if child_name == DEVICE_NAME:
                    new_device = child
                    attempts.append("verified-by-children-walk")
                    break
        except Exception as walk_err:
            attempts.append("post-create walk failed: %s" % walk_err)

    if new_device is None:
        raise RuntimeError(
            "add_device returned no new device. Tried: %s. Last error: %s" %
            (' | '.join(attempts), last_err)
        )

    new_device_name = getattr(new_device, 'get_name', lambda: DEVICE_NAME)()
    print("DEBUG: Added device '%s' under '%s'" % (new_device_name, PARENT_DEVICE_PATH))

    primary_project.save()
    print("DEBUG: Project saved.")

    emit_result({
        u"parent_path": _to_unicode(PARENT_DEVICE_PATH),
        u"device_name": _to_unicode(new_device_name),
        u"device_type": device_type,
        u"device_id": device_id,
        u"version": _to_unicode(DEVICE_VERSION) if DEVICE_VERSION else None,
        u"add_attempts": attempts,
    })
    print("Device added: %s/%s" % (PARENT_DEVICE_PATH, new_device_name))
    print("SCRIPT_SUCCESS: Device added.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error adding device under '%s': %s\n%s" % (PARENT_DEVICE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
