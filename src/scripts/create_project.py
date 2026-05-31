import sys, scriptengine as script_engine, os, shutil, time, traceback
# Placeholders. The TS handler chooses ONE of two creation modes:
#   - mode="path": copy TEMPLATE_PROJECT_PATH to PROJECT_FILE_PATH, then open.
#   - mode="name": ask CODESYS's ScriptEngine to instantiate a registered
#                  template by TEMPLATE_NAME directly at PROJECT_FILE_PATH.
# The "name" mode is what's required for templates that live inside the
# CODESYS package manager (e.g. ifm AE3100), where no free-standing .project
# file exists on disk for "path" mode to copy.
TEMPLATE_MODE = "{TEMPLATE_MODE}"
TEMPLATE_PROJECT_PATH = "{TEMPLATE_PROJECT_PATH}"
TEMPLATE_NAME = "{TEMPLATE_NAME}"
PROJECT_FILE_PATH = "{PROJECT_FILE_PATH}"

try:
    print("DEBUG: create_project: mode=%s target=%s" % (TEMPLATE_MODE, PROJECT_FILE_PATH))
    if not PROJECT_FILE_PATH: raise ValueError("Target project file path empty.")

    target_dir = os.path.dirname(PROJECT_FILE_PATH)
    if target_dir and not os.path.exists(target_dir):
        print("DEBUG: Creating target directory: %s" % target_dir)
        os.makedirs(target_dir)

    # Resolve update flags once; used by both modes when re-opening.
    try:
        update_flags = script_engine.VersionUpdateFlags.NoUpdates | script_engine.VersionUpdateFlags.SilentMode
    except AttributeError:
        update_flags = 3  # NoUpdates | SilentMode integer fallback

    project = None

    if TEMPLATE_MODE == "name":
        # Option B: invoke CODESYS's native template-creation API.
        if not TEMPLATE_NAME:
            raise ValueError("TEMPLATE_NAME empty for mode=name.")
        if os.path.exists(PROJECT_FILE_PATH):
            print("WARN: Target project file already exists, overwriting: %s" % PROJECT_FILE_PATH)
            try: os.remove(PROJECT_FILE_PATH)
            except Exception as rm_err:
                print("WARN: Could not remove existing target: %s" % rm_err)

        projects = script_engine.projects
        # The exact entrypoint varies across CODESYS SPs. Probe in order of
        # specificity, capture the last error so the user gets a real message
        # if none work.
        attempts = [
            ('create_from_template',           (TEMPLATE_NAME, PROJECT_FILE_PATH)),
            ('create_new_project_from_template',(TEMPLATE_NAME, PROJECT_FILE_PATH)),
            ('create_new_from_template',       (TEMPLATE_NAME, PROJECT_FILE_PATH)),
            # Some SPs flip the arg order (target, template).
            ('create',                          (PROJECT_FILE_PATH, TEMPLATE_NAME)),
        ]
        last_err = None
        for method_name, args in attempts:
            method = getattr(projects, method_name, None)
            if method is None or not callable(method):
                continue
            try:
                print("DEBUG: Trying script_engine.projects.%s(...)" % method_name)
                project = method(*args)
                if project is not None:
                    print("DEBUG: script_engine.projects.%s succeeded." % method_name)
                    break
            except TypeError as e:
                last_err = "%s rejected args: %s" % (method_name, e)
                print("DEBUG: %s" % last_err)
            except Exception as e:
                last_err = "%s raised: %s" % (method_name, e)
                print("DEBUG: %s" % last_err)
        if project is None:
            # All ScriptEngine entrypoints failed. Surface what we tried so the
            # caller knows whether to retry via mode=path with a copied source.
            available = sorted([m for m in dir(projects) if not m.startswith('_')])
            raise RuntimeError(
                "No script_engine.projects.* template-creation method worked. "
                "Tried: %s. Last error: %s. Available on projects: %s" %
                (', '.join(a[0] for a in attempts), last_err, ', '.join(available))
            )

    else:
        # Option A (default): copy a known .project file and open it.
        if not TEMPLATE_PROJECT_PATH:
            raise ValueError("TEMPLATE_PROJECT_PATH empty for mode=path.")
        if not os.path.exists(TEMPLATE_PROJECT_PATH):
            raise IOError("Template project file not found: %s" % TEMPLATE_PROJECT_PATH)
        if os.path.exists(PROJECT_FILE_PATH):
            print("WARN: Target project file already exists, overwriting: %s" % PROJECT_FILE_PATH)
        print("DEBUG: Copying '%s' -> '%s'" % (TEMPLATE_PROJECT_PATH, PROJECT_FILE_PATH))
        shutil.copy2(TEMPLATE_PROJECT_PATH, PROJECT_FILE_PATH)
        print("DEBUG: File copy complete; opening...")
        project = script_engine.projects.open(PROJECT_FILE_PATH, update_flags=update_flags)

    if project is None:
        raise RuntimeError(
            "Project creation returned None for target %s (mode=%s)." % (PROJECT_FILE_PATH, TEMPLATE_MODE)
        )

    # Brief settle, then explicit save — same pattern as before. Save failures
    # don't fail the call; the project is still in memory and usable.
    print("DEBUG: Pausing briefly before save...")
    time.sleep(1.0)
    try:
        print("DEBUG: Saving project...")
        project.save()
        print("DEBUG: Project save succeeded.")
    except Exception as save_err:
        print("WARN: Explicit save after create failed: %s" % save_err)

    print("Project created at: %s" % PROJECT_FILE_PATH)
    print("SCRIPT_SUCCESS: Project created successfully (mode=%s)." % TEMPLATE_MODE)
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error creating project '%s' (mode=%s): %s\n%s" % (
        PROJECT_FILE_PATH, TEMPLATE_MODE, e, detailed_error
    )
    print(error_message)
    print("SCRIPT_ERROR: %s" % e)
    sys.exit(1)
