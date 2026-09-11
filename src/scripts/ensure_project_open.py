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

def _close_project(proj):
    """Best-effort close of a project.

    CODESYS keeps a SINGLE primary project per IDE instance. If a different
    project is already primary, projects.open() for our target fails with
    "A primary project is already open." — so close the incumbent first when
    switching targets. Returns True if the close appears to have succeeded.
    """
    if proj is None:
        return False
    for how in ('module', 'method'):
        try:
            if how == 'module':
                script_engine.projects.close(proj)
            else:
                proj.close()
            return True
        except Exception as close_err:
            print("DEBUG: close via %s failed: %s" % (how, close_err))
    return False

def ensure_project_open(target_project_path):
    path_to_use = clean_path(target_project_path)
    normalized_target_path = os.path.normcase(os.path.abspath(path_to_use))

    # Track the most recent open() error so the final RuntimeError can include
    # the actual root cause (locked project, missing file, version mismatch,
    # etc.) instead of a generic "after 3 attempts" message.
    last_open_error = None

    # ── Open-flag strategy ───────────────────────────────────────────────
    # VersionUpdateFlags members (confirmed in VersionCompatibilityManager.dll):
    #   NoUpdates, SilentMode, UpdateAll, UpdateDevices, UpdateAllCustomProviders
    #
    # 1) NoUpdates|SilentMode — fast path. Correct when the project was saved
    #    by the SAME InoProShop version now running (no migration needed).
    #
    # 2) UpdateAll|UpdateDevices|SilentMode — MIGRATION path. Essential when an
    #    older project (saved by V1.9.1.6) is opened by a newer IDE (V1.10.0.3).
    #    With NoUpdates the object store keeps STALE GUIDs: the project opens,
    #    but the language-model/compile step later calls GetByGuid() and throws
    #    InvalidObjectGuidException ("对象 GUID ... 无效"), which raises a
    #    blocking GUI error dialog and wedges the IDE primary thread (every
    #    further script then hangs at "Marshaling to primary thread").
    #    Allowing the update performs migration and refreshes the GUIDs.
    VUF = script_engine.VersionUpdateFlags

    def _flag(name):
        return getattr(VUF, name, 0)

    f_noupdates = _flag('NoUpdates')
    f_silent = _flag('SilentMode')
    f_update_all = _flag('UpdateAll')
    f_update_dev = _flag('UpdateDevices')

    update_modes = []
    _seen = set()

    def _add(label, value):
        if value in _seen:
            return
        _seen.add(value)
        update_modes.append((label, value))

    _add('NoUpdates', f_noupdates | f_silent)
    if f_update_all:
        _add('UpdateAll', f_update_all | f_silent | f_update_dev)
    elif f_update_dev:
        _add('UpdateDevices', f_update_dev | f_silent)

    print("DEBUG: ensure_project_open modes=%s target='%s'"
          % ([m[0] for m in update_modes], normalized_target_path))

    for attempt in range(MAX_RETRIES):
        primary_project = None
        try:
            primary_project = script_engine.projects.primary
        except Exception as primary_err:
             print("WARN: Error getting primary project: %s. Assuming none." % primary_err)
             primary_project = None

        if primary_project:
            try:
                current_project_path = os.path.normcase(os.path.abspath(primary_project.path))
                if current_project_path == normalized_target_path:
                    # Right project is primary; sanity-check accessibility before returning.
                    try:
                         _ = len(primary_project.get_children(False))
                         return primary_project
                    except Exception as access_err:
                         # Present but unreadable — typically the stale-GUID state.
                         # Fall through so the migration modes get a chance.
                         print("WARN: Primary project access check failed for '%s': %s. Will attempt reopen." % (current_project_path, access_err))
                         primary_project = None
                else:
                     # Different project is primary: must close it first, otherwise
                     # open() fails with "A primary project is already open."
                     print("DEBUG: Primary is '%s'; closing it to open '%s'."
                           % (current_project_path, normalized_target_path))
                     if not _close_project(primary_project):
                         print("WARN: Could not close incumbent project; open() may fail.")
                     primary_project = None
            except Exception as path_err:
                 print("WARN: Could not get path of current primary project: %s. Assuming not the target." % path_err)
                 primary_project = None

        # Try each flag combination in order (fast path first, migration last).
        for mode_label, update_mode in update_modes:
            try:
                opened_project = script_engine.projects.open(
                    target_project_path, update_flags=update_mode)

                if not opened_project:
                    print("ERROR: projects.open returned None for %s (mode=%s, attempt %d)"
                          % (target_project_path, mode_label, attempt + 1))
                    continue

                time.sleep(RETRY_DELAY)
                recheck_primary = None
                try:
                    recheck_primary = script_engine.projects.primary
                except Exception as recheck_primary_err:
                    print("WARN: Error getting primary project after reopen: %s" % recheck_primary_err)

                if not recheck_primary:
                    print("WARN: No primary project found after reopening (mode=%s, attempt %d)!"
                          % (mode_label, attempt + 1))
                    continue

                recheck_path = ""
                try:
                    recheck_path = os.path.normcase(os.path.abspath(recheck_primary.path))
                except Exception as recheck_path_err:
                    print("WARN: Failed to get path after reopen: %s" % recheck_path_err)

                if recheck_path != normalized_target_path:
                    print("WARN: Different project is primary after reopening! Expected '%s', got '%s'."
                          % (normalized_target_path, recheck_path))
                    continue

                try:
                    _ = len(recheck_primary.get_children(False))
                    print("DEBUG: Project opened OK (mode=%s, attempt %d)." % (mode_label, attempt + 1))
                    return recheck_primary
                except Exception as access_err_reopen:
                    # Opened but unreadable — stale GUIDs. Try the next (migration) mode.
                    last_open_error = access_err_reopen
                    print("WARN: Reopened project unreadable (mode=%s): %s. Trying next mode."
                          % (mode_label, access_err_reopen))

            except Exception as open_err:
                 print("ERROR: Exception during projects.open (mode=%s, attempt %d): %s"
                       % (mode_label, attempt + 1, open_err))
                 last_open_error = open_err

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
