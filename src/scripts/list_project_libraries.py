import sys, scriptengine as script_engine, os, traceback, json

try:
    print("DEBUG: list_project_libraries script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    project_name = os.path.basename(PROJECT_FILE_PATH)

    libraries = []
    lib_manager = None

    # Find Library Manager object
    # Pattern 1: Search for it by name in project tree
    try:
        found_list = primary_project.find("Library Manager", True)
        if found_list:
            lib_manager = found_list[0]
            print("DEBUG: Found Library Manager via find('Library Manager')")
    except Exception as e:
        print("DEBUG: find('Library Manager') failed: %s" % e)

    # Pattern 2: Search all children
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

    if lib_manager:
        print("DEBUG: Library Manager found: %s" % getattr(lib_manager, 'get_name', lambda: '?')())

        # Try to enumerate libraries
        try:
            lib_children = lib_manager.get_children(False)
            for lib_child in lib_children:
                lib_name = getattr(lib_child, 'get_name', lambda: '?')()
                lib_entry = {'name': lib_name}

                # Try to get version info
                if hasattr(lib_child, 'version'):
                    try:
                        lib_entry['version'] = str(lib_child.version)
                    except Exception:
                        pass
                if hasattr(lib_child, 'get_version'):
                    try:
                        lib_entry['version'] = str(lib_child.get_version())
                    except Exception:
                        pass

                # Try to get company/vendor
                if hasattr(lib_child, 'company'):
                    try:
                        lib_entry['company'] = str(lib_child.company)
                    except Exception:
                        pass

                libraries.append(lib_entry)
                print("DEBUG: Found library: %s" % lib_name)
        except Exception as e:
            print("WARN: Error enumerating libraries: %s" % e)
    else:
        print("WARN: Library Manager not found in project.")

    libs_json = json.dumps(libraries)
    print("### LIBRARIES_START ###")
    print(libs_json)
    print("### LIBRARIES_END ###")
    print("Library Count: %d" % len(libraries))
    print("SCRIPT_SUCCESS: Project libraries listed.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error listing libraries for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
