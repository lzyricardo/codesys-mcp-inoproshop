import sys, scriptengine as script_engine, os, traceback, json

try:
    print("DEBUG: list_project_libraries script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    project_name = os.path.basename(PROJECT_FILE_PATH)

    libraries = []
    lib_manager = None

    # Find the Library Manager node. CODESYS localizes this node name, so a
    # bare find("Library Manager") misses it on non-English installs (e.g.
    # Chinese InoProShop calls it "库管理器"). We try:
    #   1. find() by a set of known localized names,
    #   2. a type-based scan of the project tree (robust to any locale).
    _LIB_MANAGER_NAMES = (
        "Library Manager",          # English
        "库管理器",                  # Chinese (InoProShop)
        "Bibliotheksverwaltung",    # German
        "Gestionnaire de bibliothèques",  # French
    )
    try:
        for nm in _LIB_MANAGER_NAMES:
            try:
                found_list = primary_project.find(nm, True)
                if found_list:
                    lib_manager = found_list[0]
                    print("DEBUG: Found Library Manager via find('%s')" % nm)
                    break
            except Exception:
                continue
    except Exception as e:
        print("DEBUG: localized find for Library Manager failed: %s" % e)

    if not lib_manager:
        try:
            for child in primary_project.get_children(True):
                try:
                    tname = type(child).__name__
                except Exception:
                    tname = ''
                if 'librarymanager' in tname.lower() or 'libman' in tname.lower():
                    lib_manager = child
                    print("DEBUG: Found Library Manager by type scan: %s" % tname)
                    break
                cname = getattr(child, 'get_name', lambda: '')()
                if cname and ('librarymanager' in cname.lower() or 'libman' in cname.lower()):
                    lib_manager = child
                    print("DEBUG: Found Library Manager by type-name scan: %s" % cname)
                    break
        except Exception as e:
            print("DEBUG: type-scan for Library Manager failed: %s" % e)

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

    for entry in libraries:
        for k in ('name', 'version', 'company'):
            if k in entry:
                entry[k] = _to_unicode(entry[k])
    libs_json = json.dumps(libraries, ensure_ascii=False)
    if isinstance(libs_json, unicode):
        libs_json_bytes = libs_json.encode('utf-8')
    else:
        libs_json_bytes = libs_json
    sys.stdout.write("### LIBRARIES_START ###\n")
    sys.stdout.write(libs_json_bytes)
    sys.stdout.write("\n### LIBRARIES_END ###\n")
    sys.stdout.flush()
    print("Library Count: %d" % len(libraries))
    print("SCRIPT_SUCCESS: Project libraries listed.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error listing libraries for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
