import sys, scriptengine as script_engine, os, time, traceback, json

VARIABLES_JSON = """{VARIABLES_JSON}"""  # JSON array of strings, e.g. ["GVL.x", "PLC_PRG.y"]
DURATION_MS_STR = "{DURATION_MS}"
INTERVAL_MS_STR = "{INTERVAL_MS}"

try:
    print("DEBUG: monitor_variables: vars=%s duration=%s interval=%s" %
          (VARIABLES_JSON, DURATION_MS_STR, INTERVAL_MS_STR))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)

    try:
        variable_paths = json.loads(VARIABLES_JSON)
    except Exception as parse_err:
        raise ValueError("Could not parse VARIABLES_JSON ('%s'): %s" % (VARIABLES_JSON, parse_err))
    if not isinstance(variable_paths, list) or not variable_paths:
        raise ValueError("variablePaths must be a non-empty array.")

    duration_ms = int(DURATION_MS_STR)
    interval_ms = int(INTERVAL_MS_STR)
    if interval_ms < 10:
        interval_ms = 10  # cap floor - any tighter and we just spin
    # Hard cap on duration to stay well under the watcher's 120s primary-thread
    # WaitOne timeout. 60s is plenty for tuning; longer sessions should call
    # monitor_variables in a loop client-side.
    if duration_ms > 60000:
        duration_ms = 60000
    if duration_ms < interval_ms:
        duration_ms = interval_ms

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    # Snapshot the read function once - hasattr probing on every iteration
    # adds latency that shows up at high sample rates.
    if hasattr(online_app, 'read_value'):
        read_fn = online_app.read_value
        is_value_object = True
    elif hasattr(online_app, 'read'):
        read_fn = online_app.read
        is_value_object = False
    else:
        raise TypeError("Online application does not support read_value() or read().")

    samples = []
    interval_sec = interval_ms / 1000.0
    start_t = time.time()
    deadline_t = start_t + (duration_ms / 1000.0)

    while True:
        now = time.time()
        if now >= deadline_t:
            break
        elapsed_ms = int((now - start_t) * 1000)
        frame = {u"t_ms": elapsed_ms}
        values = {}
        for var_path in variable_paths:
            try:
                result = read_fn(var_path)
                if result is None:
                    values[_to_unicode(var_path)] = None
                elif is_value_object and hasattr(result, 'value'):
                    raw = result.value
                    values[_to_unicode(var_path)] = _to_unicode(unicode(raw) if not isinstance(raw, unicode) else raw)
                else:
                    values[_to_unicode(var_path)] = _to_unicode(unicode(result) if not isinstance(result, unicode) else result)
            except Exception as read_err:
                values[_to_unicode(var_path)] = _to_unicode("__error__: %s" % read_err)
        frame[u"values"] = values
        samples.append(frame)

        # Sleep until the next interval boundary, not just for `interval_ms`
        # after the read completed - keeps the sample cadence stable when
        # reads are slow on a heavily-loaded PLC.
        next_t = start_t + (len(samples) * interval_sec)
        sleep_for = next_t - time.time()
        if sleep_for > 0:
            time.sleep(sleep_for)

    end_t = time.time()
    actual_duration_ms = int((end_t - start_t) * 1000)

    emit_result({
        u"variables": [_to_unicode(p) for p in variable_paths],
        u"sample_count": len(samples),
        u"duration_ms_requested": duration_ms,
        u"duration_ms_actual": actual_duration_ms,
        u"interval_ms": interval_ms,
        u"application": _to_unicode(app_name),
        u"samples": samples,
    })
    print("Captured %d samples over %d ms" % (len(samples), actual_duration_ms))
    print("SCRIPT_SUCCESS: monitor_variables complete.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error in monitor_variables: %s\n%s" % (e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
