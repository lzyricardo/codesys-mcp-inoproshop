import sys, scriptengine as script_engine, os, traceback

LIBRARY_NAME = "{LIBRARY_NAME}"

try:
    print("DEBUG: add_library script: Library='%s', Project='%s'" % (LIBRARY_NAME, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not LIBRARY_NAME: raise ValueError("Library name empty.")

    project_name = os.path.basename(PROJECT_FILE_PATH)
    lib_manager = None

    # Find Library Manager object
    try:
        found_list = primary_project.find("Library Manager", True)
        if found_list:
            lib_manager = found_list[0]
            print("DEBUG: Found Library Manager via find('Library Manager')")
    except Exception as e:
        print("DEBUG: find('Library Manager') failed: %s" % e)

    if not lib_manager:
        try:
            all_children = primary_project.get_children(True)
            for child in all_children:
                child_name = getattr(child, 'get_name', lambda: '')()
                if 'library' in child_name.lower() and 'manager' in child_name.lower():
                    lib_manager = child
                    print("DEBUG: Found Library Manager by name search: %s" % child_name)
                    break
        except Exception as e:
            print("DEBUG: Children search for Library Manager failed: %s" % e)

    if not lib_manager:
        raise RuntimeError("Library Manager not found in project '%s'." % project_name)

    print("DEBUG: Library Manager found: %s" % getattr(lib_manager, 'get_name', lambda: '?')())

    # Try to add the library using known API patterns. If a method exists
    # but raises (e.g. "placeholder library X could not be resolved"), capture
    # the first such error and surface it as the failure reason - that's far
    # more actionable than the generic "no add method found" message.
    added = False
    last_real_error = None  # exception text from a method that DOES exist
    candidate_methods = ('add_library', 'insert_library', 'add_reference')

    for method_name in candidate_methods:
        if not hasattr(lib_manager, method_name):
            continue
        method = getattr(lib_manager, method_name)
        try:
            result = method(LIBRARY_NAME)
            added = True
            print("DEBUG: %s succeeded: %s" % (method_name, result))
            break
        except Exception as e:
            err_text = "%s: %s" % (type(e).__name__, e)
            print("DEBUG: %s raised: %s" % (method_name, err_text))
            if last_real_error is None:
                last_real_error = (method_name, err_text)

    if not added:
        if last_real_error is not None:
            raise RuntimeError(
                "Library Manager.%s('%s') failed: %s. The library is likely "
                "not installed in the CODESYS library repository, or the name "
                "needs a fully-qualified placeholder (e.g. "
                "'Standard, * (System)' or 'Util, 3.5.16.0 (3S - Smart Software Solutions GmbH)')." % (
                    last_real_error[0], LIBRARY_NAME, last_real_error[1])
            )
        raise RuntimeError(
            "Could not add library '%s'. Library Manager does not expose "
            "any known add method (tried add_library, insert_library, "
            "add_reference)." % LIBRARY_NAME
        )

    try:
        print("DEBUG: Saving Project...")
        primary_project.save()
        print("DEBUG: Project saved successfully after adding library.")
    except Exception as save_err:
        print("ERROR: Failed to save Project after adding library: %s" % save_err)
        detailed_error = traceback.format_exc()
        error_message = "Error saving Project after adding library '%s': %s\n%s" % (LIBRARY_NAME, save_err, detailed_error)
        print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)

    print("Library Added: %s" % LIBRARY_NAME)
    print("Project: %s" % project_name)
    print("SCRIPT_SUCCESS: Library added successfully.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error adding library '%s' to project '%s': %s\n%s" % (LIBRARY_NAME, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)
