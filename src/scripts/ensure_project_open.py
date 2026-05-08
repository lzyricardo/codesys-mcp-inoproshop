import sys
import scriptengine as script_engine
import os
import time
import traceback

# --- Function to ensure the correct project is open ---
MAX_RETRIES = 3
RETRY_DELAY = 2.0

def clean_path(path_str):
    return path_str.strip('"\'')

def ensure_project_open(target_project_path):
    path_to_use = clean_path(target_project_path)
    normalized_target_path = os.path.normcase(os.path.abspath(path_to_use))

    # Track the most recent open() error so the final RuntimeError can include
    # the actual root cause (locked project, missing file, version mismatch,
    # etc.) instead of a generic "after 3 attempts" message.
    last_open_error = None

    for attempt in range(MAX_RETRIES):
        primary_project = None
        try:
            primary_project = script_engine.projects.primary
        except Exception as primary_err:
             print("WARN: Error getting primary project: %s. Assuming none." % primary_err)
             primary_project = None

        current_project_path = ""
        project_ok = False

        if primary_project:
            try:
                current_project_path = os.path.normcase(os.path.abspath(primary_project.path))
                if current_project_path == normalized_target_path:
                    # Right project is primary; sanity-check accessibility before returning.
                    try:
                         _ = len(primary_project.get_children(False))
                         project_ok = True
                         return primary_project
                    except Exception as access_err:
                         print("WARN: Primary project access check failed for '%s': %s. Will attempt reopen." % (current_project_path, access_err))
                         primary_project = None
                else:
                     primary_project = None
            except Exception as path_err:
                 print("WARN: Could not get path of current primary project: %s. Assuming not the target." % path_err)
                 primary_project = None

        if not project_ok:
            try:
                update_mode = script_engine.VersionUpdateFlags.NoUpdates | script_engine.VersionUpdateFlags.SilentMode

                try:
                     opened_project = script_engine.projects.open(target_project_path, update_flags=update_mode)

                     if not opened_project:
                         print("ERROR: projects.open returned None for %s on attempt %d" % (target_project_path, attempt + 1))
                     else:
                         time.sleep(RETRY_DELAY)
                         recheck_primary = None
                         try:
                             recheck_primary = script_engine.projects.primary
                         except Exception as recheck_primary_err:
                             print("WARN: Error getting primary project after reopen: %s" % recheck_primary_err)
                             traceback.print_exc()

                         if recheck_primary:
                              recheck_path = ""
                              try:
                                  recheck_path = os.path.normcase(os.path.abspath(recheck_primary.path))
                              except Exception as recheck_path_err:
                                  print("WARN: Failed to get path after reopen: %s" % recheck_path_err)

                              if recheck_path == normalized_target_path:
                                   try:
                                       _ = len(recheck_primary.get_children(False))
                                       return recheck_primary
                                   except Exception as access_err_reopen:
                                        print("WARN: Reopened project (%s) basic access check failed: %s." % (normalized_target_path, access_err_reopen))
                              else:
                                   print("WARN: Different project is primary after reopening! Expected '%s', got '%s'." % (normalized_target_path, recheck_path))
                         else:
                               print("WARN: No primary project found after reopening attempt %d!" % (attempt+1))

                except Exception as open_err:
                     print("ERROR: Exception during projects.open call on attempt %d: %s" % (attempt + 1, open_err))
                     traceback.print_exc()
                     last_open_error = open_err

            except Exception as outer_open_err:
                 print("ERROR: Unexpected error during open setup/logic attempt %d: %s" % (attempt + 1, outer_open_err))
                 traceback.print_exc()

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
        else:
             print("ERROR: Failed all ensure_project_open attempts for %s." % normalized_target_path)

    # If all retries fail, include the most recent open() error so callers can
    # distinguish "file locked", "file missing", "version mismatch", etc.
    if last_open_error is not None:
        raise RuntimeError(
            "Failed to ensure project '%s' is open and accessible after %d attempts. Last error: %s: %s" %
            (target_project_path, MAX_RETRIES, type(last_open_error).__name__, last_open_error)
        )
    raise RuntimeError(
        "Failed to ensure project '%s' is open and accessible after %d attempts." %
        (target_project_path, MAX_RETRIES)
    )
# --- End of function ---

# Placeholder for the project file path (must be set in scripts using this snippet)
PROJECT_FILE_PATH = "{PROJECT_FILE_PATH}"
