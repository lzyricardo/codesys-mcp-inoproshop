import sys, scriptengine as script_engine, os, traceback

DEVICE_PATH = "{DEVICE_PATH}"

try:
    print("DEBUG: inspect_device_node: device='%s'" % DEVICE_PATH)
    primary_project = require_project_open(PROJECT_FILE_PATH)
    if not DEVICE_PATH:
        raise ValueError("Device path empty.")

    device = find_object_by_path_robust(primary_project, DEVICE_PATH, "device")
    if device is None:
        raise ValueError("Device not found at path: %s" % DEVICE_PATH)

    device_name = getattr(device, 'get_name', lambda: '?')()
    device_class = type(device).__name__

    # Probe the parameter accessor. Different CODESYS versions expose the
    # parameter list differently; we try the canonical names in order.
    param_records = []
    parameter_accessors_tried = []

    def _coerce_value(v):
        if v is None:
            return None
        try:
            return _to_unicode(unicode(v) if not isinstance(v, unicode) else v)
        except Exception:
            try:
                return _to_unicode(repr(v))
            except Exception:
                return None

    # Primary accessor: device.parameter (a dict-like keyed by parameter id)
    params_obj = getattr(device, 'parameter', None)
    parameter_accessors_tried.append('parameter')
    if params_obj is not None:
        # Some CODESYS versions expose iteration via .keys() or just iter().
        param_ids = []
        try:
            param_ids = list(params_obj.keys())
        except Exception:
            try:
                param_ids = list(iter(params_obj))
            except Exception as iter_err:
                print("DEBUG: parameter accessor not iterable: %s" % iter_err)
        for pid in param_ids:
            try:
                slot = params_obj[pid]
                rec = {
                    u"id": pid if isinstance(pid, int) else _to_unicode(unicode(pid)),
                    u"value": _coerce_value(getattr(slot, 'value', None)),
                }
                # Optional metadata if exposed.
                for meta_attr in ('name', 'type', 'description', 'default_value', 'unit'):
                    if hasattr(slot, meta_attr):
                        try:
                            rec[_to_unicode(meta_attr)] = _coerce_value(getattr(slot, meta_attr))
                        except Exception:
                            pass
                param_records.append(rec)
            except Exception as slot_err:
                param_records.append({
                    u"id": pid if isinstance(pid, int) else _to_unicode(unicode(pid)),
                    u"error": _to_unicode(str(slot_err)),
                })

    # Fallback: device.parameters (some versions)
    if not param_records:
        params_obj = getattr(device, 'parameters', None)
        parameter_accessors_tried.append('parameters')
        if params_obj is not None:
            try:
                for pid in params_obj:
                    try:
                        rec = {u"id": _to_unicode(unicode(pid)), u"value": _coerce_value(params_obj[pid])}
                        param_records.append(rec)
                    except Exception as e:
                        param_records.append({u"id": _to_unicode(unicode(pid)), u"error": _to_unicode(str(e))})
            except Exception:
                pass

    # Identify children (sub-devices) - useful context for callers planning
    # add_device under this node.
    children = []
    try:
        for child in device.get_children(False):
            children.append({
                u"name": _to_unicode(getattr(child, 'get_name', lambda: '?')()),
                u"type": _to_unicode(type(child).__name__),
            })
    except Exception:
        pass

    # Identify the device's own type/id metadata if exposed.
    descriptor = {}
    for meta_attr in ('device_id', 'device_type', 'version', 'vendor', 'description'):
        if hasattr(device, meta_attr):
            try:
                descriptor[_to_unicode(meta_attr)] = _coerce_value(getattr(device, meta_attr))
            except Exception:
                pass

    emit_result({
        u"device_path": _to_unicode(DEVICE_PATH),
        u"device_name": _to_unicode(device_name),
        u"device_class": _to_unicode(device_class),
        u"descriptor": descriptor,
        u"parameters": param_records,
        u"parameter_count": len(param_records),
        u"children": children,
        u"parameter_accessors_tried": parameter_accessors_tried,
    })
    print("Inspected: %s (%d parameters, %d children)" % (device_name, len(param_records), len(children)))
    print("SCRIPT_SUCCESS: inspect_device_node complete.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error inspecting device '%s': %s\n%s" % (DEVICE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
