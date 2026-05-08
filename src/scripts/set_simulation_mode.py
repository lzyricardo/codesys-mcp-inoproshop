import sys, scriptengine as script_engine, os, traceback

# ENABLE is interpolated from the MCP tool param: 'true' or 'false'.
ENABLE_STR = "{ENABLE}"

try:
    print("DEBUG: set_simulation_mode script: Project='%s' ENABLE='%s'" % (PROJECT_FILE_PATH, ENABLE_STR))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    enable = ENABLE_STR.strip().lower() in ('true', '1', 'yes', 'on')

    # Enumerate every object with set_simulation_mode so we know what's
    # available and so we can surface the choice diagnostically.
    candidates = []
    for child in primary_project.get_children(True):
        if hasattr(child, 'set_simulation_mode'):
            name = getattr(child, 'get_name', lambda: '?')()
            sim_before = None
            if hasattr(child, 'is_simulation_mode'):
                try:
                    sim_before = child.is_simulation_mode
                except Exception as read_err:
                    sim_before = "ERR:" + str(read_err)
            candidates.append({'obj': child, 'name': name, 'class': type(child).__name__, 'before': sim_before})

    print("DEBUG: Found %d object(s) with set_simulation_mode:" % len(candidates))
    for c in candidates:
        print("  - name='%s' class='%s' is_simulation_mode=%s" % (c['name'], c['class'], c['before']))

    # Prefer an object literally named "Device" (the PLC Device descriptor) -
    # that's the canonical place set_simulation_mode is honoured. Fall back to
    # the first candidate if no Device-named object exists.
    target = None
    for c in candidates:
        if c['name'] == 'Device':
            target = c
            print("DEBUG: Selected canonical 'Device' object.")
            break
    if target is None and candidates:
        target = candidates[0]
        print("DEBUG: No object named 'Device' found; falling back to first candidate '%s'." % target['name'])

    if target is None:
        # Last-ditch: try project.find('Device', True)
        try:
            found = primary_project.find('Device', True)
            for f in found:
                if hasattr(f, 'set_simulation_mode'):
                    target = {'obj': f, 'name': getattr(f, 'get_name', lambda: '?')(),
                              'class': type(f).__name__, 'before': None}
                    print("DEBUG: Found Device via project.find: '%s'" % target['name'])
                    break
        except Exception as e:
            print("DEBUG: project.find('Device') failed: %s" % e)

    if target is None:
        raise RuntimeError("No object with set_simulation_mode found. Project has no Device descriptor or none expose simulation_mode.")

    device = target['obj']
    device_name = target['name']
    device_class = target['class']
    before = target['before']

    print("DEBUG: Setting simulation_mode=%s on '%s' (%s); was %s" % (enable, device_name, device_class, before))
    device.set_simulation_mode(enable)

    # Save so simulation state persists across script invocations
    try:
        primary_project.save()
        print("DEBUG: Project saved after set_simulation_mode.")
    except Exception as save_err:
        print("WARN: project.save() failed after set_simulation_mode: %s" % save_err)

    # Read back via primary getter
    after = None
    if hasattr(device, 'is_simulation_mode'):
        try:
            after = device.is_simulation_mode
        except Exception as e:
            print("WARN: Could not read is_simulation_mode after: %s" % e)

    # Some descriptors expose a different property name; probe a few
    other_states = {}
    for attr in ('simulation_mode', 'simulation', 'is_simulating'):
        if hasattr(device, attr):
            try:
                other_states[attr] = getattr(device, attr)
            except Exception as e:
                other_states[attr] = "ERR:" + str(e)

    print("Device: %s" % device_name)
    print("DeviceClass: %s" % device_class)
    print("Simulation Before: %s" % before)
    print("Simulation Requested: %s" % enable)
    print("Simulation After: %s" % after)
    if other_states:
        print("Other simulation-like properties: %s" % other_states)

    # NB: we don't enforce after==enable here because some descriptors
    # implement set_simulation_mode without a usable getter. Verification
    # happens via subsequent connect_to_device.

    print("SCRIPT_SUCCESS: Simulation mode set.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error setting simulation mode for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
