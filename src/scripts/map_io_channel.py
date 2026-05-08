import sys, scriptengine as script_engine, os, traceback

DEVICE_PATH = "{DEVICE_PATH}"
CHANNEL_PATH = "{CHANNEL_PATH}"  # e.g. "Inputs/Byte 0" or "0/3" (numeric indices)
VARIABLE_NAME = "{VARIABLE_NAME}"
CLEAR_BINDING = "{CLEAR_BINDING}"  # "1" / "0" - if "1", remove the existing binding (variable_name ignored)

# CODESYS I/O channel mapping is the second-most-fiddly part of fieldbus
# setup (after device descriptors). The scripting API exposes it via per-
# channel set_variable / variable accessors, but the channel object tree
# under a device is not uniform across descriptors. We probe a few patterns.

try:
    print("DEBUG: map_io_channel: device='%s' channel='%s' var='%s' clear=%s" %
          (DEVICE_PATH, CHANNEL_PATH, VARIABLE_NAME, CLEAR_BINDING))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not DEVICE_PATH:
        raise ValueError("Device path empty.")
    if not CHANNEL_PATH:
        raise ValueError("Channel path empty.")

    clear_binding = (CLEAR_BINDING == "1")
    if not clear_binding and not VARIABLE_NAME:
        raise ValueError("variableName is required unless clearBinding is true.")

    device = find_object_by_path_robust(primary_project, DEVICE_PATH, "device")
    if device is None:
        raise ValueError("Device not found at path: %s" % DEVICE_PATH)

    # Resolve the channel. Two addressing modes:
    #   1. slash-separated path under the device, e.g. "Inputs/Byte 0/Bit 3"
    #   2. raw integer index into a flat channel list, e.g. "5"
    # Both forms walk the device's children using the standard helper.
    channel = None
    resolution_attempts = []

    # Attempt 1: numeric index (single integer or comma list).
    is_numeric_path = all(seg.strip().isdigit() for seg in CHANNEL_PATH.replace(',', '/').split('/') if seg.strip())
    if is_numeric_path:
        try:
            current = device
            for seg in CHANNEL_PATH.replace(',', '/').split('/'):
                seg = seg.strip()
                if not seg:
                    continue
                idx = int(seg)
                children = list(current.get_children(False))
                if idx >= len(children):
                    raise ValueError("Index %d out of range (%d children)" % (idx, len(children)))
                current = children[idx]
            channel = current
            resolution_attempts.append("numeric path '%s'" % CHANNEL_PATH)
        except Exception as e:
            resolution_attempts.append("numeric path failed: %s" % e)

    # Attempt 2: name-based traversal via the standard helper, but rooted at
    # the device (not the project root).
    if channel is None:
        try:
            # find_object_by_path_robust starts from a node and walks; pass
            # the device itself as start_node.
            channel = find_object_by_path_robust(device, CHANNEL_PATH, "channel")
            if channel is not None:
                resolution_attempts.append("name path '%s'" % CHANNEL_PATH)
        except Exception as e:
            resolution_attempts.append("name path failed: %s" % e)

    if channel is None:
        raise ValueError(
            "Channel not found at '%s' under '%s'. Tried: %s. Use inspect_device_node "
            "to discover the actual channel layout for this device." %
            (CHANNEL_PATH, DEVICE_PATH, ' | '.join(resolution_attempts))
        )

    channel_name = getattr(channel, 'get_name', lambda: '?')()
    channel_class = type(channel).__name__
    print("DEBUG: Resolved channel '%s' (%s)" % (channel_name, channel_class))

    # Read existing binding before mutating - so we can show before/after.
    before_binding = None
    for attr in ('variable', 'mapped_variable', 'symbol'):
        if hasattr(channel, attr):
            try:
                v = getattr(channel, attr)
                before_binding = _to_unicode(unicode(v) if v is not None and not isinstance(v, unicode) else v) if v is not None else None
                break
            except Exception:
                pass

    # Apply the binding (or clear it).
    set_attempts = []
    success = False
    last_err = None

    target_value = u"" if clear_binding else _to_unicode(VARIABLE_NAME)

    # Attempt 1: channel.set_variable(name)
    if not success and hasattr(channel, 'set_variable'):
        try:
            channel.set_variable(target_value)
            success = True
            set_attempts.append("channel.set_variable(name)")
        except Exception as e:
            last_err = e
            set_attempts.append("set_variable failed: %s" % e)

    # Attempt 2: channel.variable = name (property setter)
    if not success and hasattr(channel, 'variable'):
        try:
            channel.variable = target_value
            success = True
            set_attempts.append("channel.variable = name")
        except Exception as e:
            last_err = e
            set_attempts.append("variable= failed: %s" % e)

    # Attempt 3: channel.symbol = name (older API surface)
    if not success and hasattr(channel, 'symbol'):
        try:
            channel.symbol = target_value
            success = True
            set_attempts.append("channel.symbol = name")
        except Exception as e:
            last_err = e
            set_attempts.append("symbol= failed: %s" % e)

    if not success:
        raise RuntimeError(
            "Could not %s channel binding via any known API. Tried: %s. "
            "Last error: %s. Some channels are read-only or only mappable via "
            "the IDE I/O Mapping tab." %
            ("clear" if clear_binding else "set", ' | '.join(set_attempts), last_err)
        )

    # Read back the final binding for confirmation.
    after_binding = None
    for attr in ('variable', 'mapped_variable', 'symbol'):
        if hasattr(channel, attr):
            try:
                v = getattr(channel, attr)
                after_binding = _to_unicode(unicode(v) if v is not None and not isinstance(v, unicode) else v) if v is not None else None
                break
            except Exception:
                pass

    primary_project.save()
    print("DEBUG: Project saved.")

    emit_result({
        u"device_path": _to_unicode(DEVICE_PATH),
        u"channel_path": _to_unicode(CHANNEL_PATH),
        u"channel_name": _to_unicode(channel_name),
        u"channel_class": _to_unicode(channel_class),
        u"variable_before": before_binding,
        u"variable_after": after_binding,
        u"cleared": clear_binding,
        u"resolution_attempts": resolution_attempts,
        u"set_attempts": set_attempts,
    })
    if clear_binding:
        print("Cleared binding on %s/%s (was: %s)" % (DEVICE_PATH, channel_name, before_binding))
    else:
        print("Mapped %s/%s -> %s (was: %s)" % (DEVICE_PATH, channel_name, VARIABLE_NAME, before_binding))
    print("SCRIPT_SUCCESS: I/O channel binding updated.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error mapping I/O channel: %s\n%s" % (e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
