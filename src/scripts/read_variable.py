import sys, scriptengine as script_engine, os, traceback

VARIABLE_PATH = "{VARIABLE_PATH}"

try:
    print("DEBUG: read_variable script: Variable='%s', Project='%s'" % (VARIABLE_PATH, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not VARIABLE_PATH: raise ValueError("Variable path empty.")

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    value_repr = None
    var_type = None
    raw_repr = None

    if hasattr(online_app, 'read_value'):
        result = online_app.read_value(VARIABLE_PATH)
        if result is not None:
            raw_repr = _to_unicode(repr(result))
            if hasattr(result, 'value'):
                value_repr = _to_unicode(unicode(result.value) if not isinstance(result.value, unicode) else result.value)
                if hasattr(result, 'type'):
                    var_type = _to_unicode(str(result.type))
            else:
                value_repr = _to_unicode(unicode(result) if not isinstance(result, unicode) else result)
        print("DEBUG: read_value returned (truncated): %s" % (value_repr[:200] if value_repr else None))
    elif hasattr(online_app, 'read'):
        result = online_app.read(VARIABLE_PATH)
        if result is not None:
            value_repr = _to_unicode(unicode(result) if not isinstance(result, unicode) else result)
            raw_repr = _to_unicode(repr(result))
        print("DEBUG: read returned (truncated): %s" % (value_repr[:200] if value_repr else None))
    else:
        raise TypeError("Online application does not support read_value() or read().")

    # Structured result via the standard RESULT_JSON marker block - lets the
    # Node side parse multi-line struct values without truncation. Caller
    # gets back {variable, value, type, raw, application}.
    emit_result({
        u"variable": _to_unicode(VARIABLE_PATH),
        u"value": value_repr,
        u"type": var_type,
        u"raw": raw_repr,
        u"application": _to_unicode(app_name),
    })

    print("SCRIPT_SUCCESS: Variable read successfully.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error reading variable '%s' in project %s: %s\n%s" % (VARIABLE_PATH, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
