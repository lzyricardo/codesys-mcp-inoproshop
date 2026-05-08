import sys, scriptengine as script_engine, os, traceback, json

try:
    print("DEBUG: compile_project script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    project_name = os.path.basename(PROJECT_FILE_PATH)
    target_app = None
    app_name = "N/A"

    # Try getting active application first
    try:
        target_app = primary_project.active_application
        if target_app:
            app_name = getattr(target_app, 'get_name', lambda: "Unnamed App (Active)")()
            print("DEBUG: Found active application: %s" % app_name)
    except Exception as active_err:
        print("WARN: Could not get active application: %s. Searching..." % active_err)

    # If no active app, search for the first one
    if not target_app:
        print("DEBUG: Searching for first compilable application...")
        apps = []
        try:
             # Search recursively through all project objects
             all_children = primary_project.get_children(True)
             for child in all_children:
                  # Check using the marker property and if build method exists
                  if hasattr(child, 'is_application') and child.is_application and hasattr(child, 'build'):
                       app_name_found = getattr(child, 'get_name', lambda: "Unnamed App")()
                       print("DEBUG: Found potential application object: %s" % app_name_found)
                       apps.append(child)
                       break # Take the first one found
        except Exception as find_err: print("WARN: Error finding application object: %s" % find_err)

        if not apps: raise RuntimeError("No compilable application found in project '%s'" % project_name)
        target_app = apps[0]
        app_name = getattr(target_app, 'get_name', lambda: "Unnamed App (First Found)")()
        print("WARN: Compiling first found application: %s" % app_name)

    print("DEBUG: Calling build() on app '%s'..." % app_name)
    if not hasattr(target_app, 'build'):
         raise TypeError("Selected object '%s' is not an application or doesn't support build()." % app_name)

    # Execute the build
    target_app.build();
    print("DEBUG: Build command executed for application '%s'." % app_name)

    # --- Extract compiler messages ---
    messages = []
    messages_found = False

    # Pattern 1: target_app.get_message_objects()
    if hasattr(target_app, 'get_message_objects'):
        try:
            msg_objects = target_app.get_message_objects()
            if msg_objects is not None:
                messages_found = True
                for msg in msg_objects:
                    entry = {}
                    if hasattr(msg, 'severity'):
                        sev = str(msg.severity).lower()
                        if 'error' in sev:
                            entry['severity'] = 'error'
                        elif 'warning' in sev:
                            entry['severity'] = 'warning'
                        elif 'info' in sev:
                            entry['severity'] = 'info'
                        else:
                            entry['severity'] = sev
                    else:
                        entry['severity'] = 'unknown'
                    entry['text'] = getattr(msg, 'text', getattr(msg, 'message', str(msg)))
                    if hasattr(msg, 'object_name'):
                        entry['object'] = msg.object_name
                    elif hasattr(msg, 'source'):
                        entry['object'] = str(msg.source)
                    if hasattr(msg, 'line_number'):
                        entry['line'] = msg.line_number
                    elif hasattr(msg, 'position'):
                        entry['line'] = msg.position
                    messages.append(entry)
                print("DEBUG: Got %d messages from app.get_message_objects()" % len(messages))
        except Exception as e:
            print("DEBUG: app.get_message_objects() failed: %s" % e)

    # Pattern 2: script_engine.system.get_message_objects()
    if not messages_found and hasattr(script_engine, 'system'):
        se_sys = script_engine.system
        if hasattr(se_sys, 'get_message_objects'):
            try:
                msg_objects = se_sys.get_message_objects()
                if msg_objects is not None:
                    messages_found = True
                    for msg in msg_objects:
                        entry = {}
                        if hasattr(msg, 'severity'):
                            sev = str(msg.severity).lower()
                            if 'error' in sev:
                                entry['severity'] = 'error'
                            elif 'warning' in sev:
                                entry['severity'] = 'warning'
                            elif 'info' in sev:
                                entry['severity'] = 'info'
                            else:
                                entry['severity'] = sev
                        else:
                            entry['severity'] = 'unknown'
                        entry['text'] = getattr(msg, 'text', getattr(msg, 'message', str(msg)))
                        if hasattr(msg, 'object_name'):
                            entry['object'] = msg.object_name
                        elif hasattr(msg, 'source'):
                            entry['object'] = str(msg.source)
                        if hasattr(msg, 'line_number'):
                            entry['line'] = msg.line_number
                        elif hasattr(msg, 'position'):
                            entry['line'] = msg.position
                        messages.append(entry)
                    print("DEBUG: Got %d messages from system.get_message_objects()" % len(messages))
            except Exception as e:
                print("DEBUG: system.get_message_objects() failed: %s" % e)

    # Pattern 3: script_engine.system.get_messages() (older API)
    if not messages_found and hasattr(script_engine, 'system'):
        se_sys = script_engine.system
        if hasattr(se_sys, 'get_messages'):
            try:
                msg_objects = se_sys.get_messages()
                if msg_objects is not None:
                    messages_found = True
                    for msg in msg_objects:
                        entry = {}
                        if hasattr(msg, 'severity'):
                            sev = str(msg.severity).lower()
                            if 'error' in sev:
                                entry['severity'] = 'error'
                            elif 'warning' in sev:
                                entry['severity'] = 'warning'
                            elif 'info' in sev:
                                entry['severity'] = 'info'
                            else:
                                entry['severity'] = sev
                        else:
                            entry['severity'] = 'unknown'
                        entry['text'] = getattr(msg, 'text', getattr(msg, 'message', str(msg)))
                        if hasattr(msg, 'object_name'):
                            entry['object'] = msg.object_name
                        elif hasattr(msg, 'source'):
                            entry['object'] = str(msg.source)
                        if hasattr(msg, 'line_number'):
                            entry['line'] = msg.line_number
                        elif hasattr(msg, 'position'):
                            entry['line'] = msg.position
                        messages.append(entry)
                    print("DEBUG: Got %d messages from system.get_messages()" % len(messages))
            except Exception as e:
                print("DEBUG: system.get_messages() failed: %s" % e)

    for entry in messages:
        if 'text' in entry:
            entry['text'] = _to_unicode(entry['text'])
        if 'object' in entry:
            entry['object'] = _to_unicode(entry['object'])
        if 'severity' in entry:
            entry['severity'] = _to_unicode(entry['severity'])

    # _json_default is provided by the prepended _text_utils helper.
    messages_json = json.dumps(messages, ensure_ascii=False, default=_json_default)
    if isinstance(messages_json, unicode):
        messages_json_bytes = messages_json.encode('utf-8')
    else:
        messages_json_bytes = messages_json
    sys.stdout.write("### COMPILE_MESSAGES_START ###\n")
    sys.stdout.write(messages_json_bytes)
    sys.stdout.write("\n### COMPILE_MESSAGES_END ###\n")
    sys.stdout.flush()

    print("Compile Initiated For Application: %s" % app_name)
    print("In Project: %s" % project_name)
    print("Messages Found: %s" % messages_found)
    print("Message Count: %d" % len(messages))
    print("SCRIPT_SUCCESS: Application compilation initiated.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error initiating compilation for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
