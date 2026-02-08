import sys, scriptengine as script_engine, os, traceback

FOLDER_NAME = "{FOLDER_NAME}"
PARENT_PATH_REL = "{PARENT_PATH}"

try:
    print("DEBUG: create_folder script: Name='%s', ParentPath='%s', Project='%s'" % (FOLDER_NAME, PARENT_PATH_REL, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not FOLDER_NAME: raise ValueError("Folder name empty.")
    if not PARENT_PATH_REL: raise ValueError("Parent path empty.")

    # Find parent object (same logic as create_pou)
    if PARENT_PATH_REL == "Application":
        project_name = os.path.splitext(os.path.basename(PROJECT_FILE_PATH))[0]
        potential_paths = [
            PARENT_PATH_REL,
            "%s.%s" % (project_name, PARENT_PATH_REL),
            "%s/%s" % (project_name, PARENT_PATH_REL),
        ]
        parent_object = None
        for path in potential_paths:
            parent_candidate = find_object_by_path_robust(primary_project, path, "parent container")
            if parent_candidate:
                parent_object = parent_candidate
                print("DEBUG: Found parent using path: '%s'" % path)
                break
        if not parent_object:
            try:
                if hasattr(primary_project, 'active_application'):
                    app = primary_project.active_application
                    if app:
                        parent_object = app
                        print("DEBUG: Found application directly: %s" % app.get_name())
                if not parent_object and hasattr(primary_project, 'find'):
                    apps = primary_project.find("Application", True)
                    if apps:
                        parent_object = apps[0]
            except Exception as e:
                print("ERROR: Direct application access failed: %s" % e)
    else:
        parent_object = find_object_by_path_robust(primary_project, PARENT_PATH_REL, "parent container")

    if not parent_object:
        raise ValueError("Parent object not found for path: %s" % PARENT_PATH_REL)

    parent_name = getattr(parent_object, 'get_name', lambda: str(parent_object))()
    print("DEBUG: Using parent object: %s" % parent_name)

    # Create the folder
    if not hasattr(parent_object, 'create_folder'):
        raise TypeError("Parent object '%s' of type %s does not support create_folder." % (parent_name, type(parent_object).__name__))

    print("DEBUG: Calling create_folder: Name='%s'" % FOLDER_NAME)
    new_folder = parent_object.create_folder(name=FOLDER_NAME)

    if new_folder:
        new_folder_name = getattr(new_folder, 'get_name', lambda: FOLDER_NAME)()
        print("DEBUG: Folder object created: %s" % new_folder_name)

        try:
            print("DEBUG: Saving Project...")
            primary_project.save()
            print("DEBUG: Project saved successfully after folder creation.")
        except Exception as save_err:
            print("ERROR: Failed to save Project after folder creation: %s" % save_err)
            detailed_error = traceback.format_exc()
            error_message = "Error saving Project after creating folder '%s': %s\n%s" % (FOLDER_NAME, save_err, detailed_error)
            print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)

        print("Folder Created: %s" % new_folder_name)
        print("Parent Path: %s" % PARENT_PATH_REL)
        print("SCRIPT_SUCCESS: Folder created successfully.")
        sys.exit(0)
    else:
        error_message = "Failed to create folder '%s'. create_folder returned None." % FOLDER_NAME
        print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error creating folder '%s' in project '%s': %s\n%s" % (FOLDER_NAME, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)
