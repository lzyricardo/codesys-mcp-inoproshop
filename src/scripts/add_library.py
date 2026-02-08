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

    # Try to add the library using various API patterns
    added = False

    # Pattern 1: lib_manager.add_library(name)
    if hasattr(lib_manager, 'add_library'):
        try:
            result = lib_manager.add_library(LIBRARY_NAME)
            added = True
            print("DEBUG: add_library succeeded: %s" % result)
        except Exception as e:
            print("DEBUG: add_library failed: %s" % e)

    # Pattern 2: lib_manager.insert_library(name)
    if not added and hasattr(lib_manager, 'insert_library'):
        try:
            result = lib_manager.insert_library(LIBRARY_NAME)
            added = True
            print("DEBUG: insert_library succeeded: %s" % result)
        except Exception as e:
            print("DEBUG: insert_library failed: %s" % e)

    # Pattern 3: lib_manager.add_reference(name)
    if not added and hasattr(lib_manager, 'add_reference'):
        try:
            result = lib_manager.add_reference(LIBRARY_NAME)
            added = True
            print("DEBUG: add_reference succeeded: %s" % result)
        except Exception as e:
            print("DEBUG: add_reference failed: %s" % e)

    if not added:
        raise RuntimeError("Could not add library '%s'. Library Manager does not support known add methods (add_library, insert_library, add_reference)." % LIBRARY_NAME)

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
