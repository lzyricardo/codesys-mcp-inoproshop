import sys, scriptengine as script_engine, os, traceback

ARCHIVE_PATH = "{ARCHIVE_PATH}"
COMMENT = "{COMMENT}"
INCLUDE_LIBRARIES = "{INCLUDE_LIBRARIES}"  # "1" / "0"
INCLUDE_COMPILED = "{INCLUDE_COMPILED}"  # "1" / "0"

try:
    print("DEBUG: create_project_archive: Path='%s' Comment='%s' Libs=%s Compiled=%s" %
          (ARCHIVE_PATH, COMMENT, INCLUDE_LIBRARIES, INCLUDE_COMPILED))
    if not ARCHIVE_PATH:
        raise ValueError("Archive output path empty.")

    # Read-only verifier - the project must already be open. We don't open
    # arbitrary projects from this tool because creating an archive of the
    # wrong project would silently produce a misleading artefact.
    primary_project = require_project_open(PROJECT_FILE_PATH)

    include_libs = (INCLUDE_LIBRARIES == "1")
    include_compiled = (INCLUDE_COMPILED == "1")

    # CODESYS exposes a few archive APIs across versions. The most common is
    # `primary.save_archive(path, comment=None, content=...)`. We probe for
    # the method shape live and fall back through the alternatives so this
    # works on SP16 / SP19 / SP21 without per-version branching.
    save_fn = None
    for fn_name in ('save_archive', 'save_as_archive', 'archive', 'save_archived'):
        if hasattr(primary_project, fn_name):
            save_fn = getattr(primary_project, fn_name)
            print("DEBUG: Using primary_project.%s" % fn_name)
            break
    if save_fn is None:
        raise RuntimeError(
            "No archive method found on the project object. "
            "Tried: save_archive, save_as_archive, archive, save_archived. "
            "This CODESYS version may not expose archiving via the scripting API."
        )

    # Resolve the content flag set. Older versions accept an integer bitmask
    # via script_engine.ProjectArchive; newer ones use enum members. Either
    # way, "include nothing extra" is the safe default to keep archives
    # small (the project file itself is always included).
    content_flag = None
    try:
        archive_consts = getattr(script_engine, 'ProjectArchive', None)
        if archive_consts is not None:
            # Build flag by exclusion - start from "all", subtract the bits the
            # caller asked to exclude. If the caller asked for both, we leave
            # content_flag=None so the API uses its default (everything).
            wants_default = include_libs and include_compiled
            if not wants_default:
                # Some versions name flags `NoLibraries`, `NoCompiledLibraries`,
                # `OnlyDocumentation` etc. We assemble whichever exclusions match.
                mask = 0
                exclusions = []
                if not include_libs and hasattr(archive_consts, 'NoLibraries'):
                    exclusions.append('NoLibraries')
                if not include_compiled and hasattr(archive_consts, 'NoCompiledLibraries'):
                    exclusions.append('NoCompiledLibraries')
                for name in exclusions:
                    val = getattr(archive_consts, name)
                    try:
                        mask |= int(val)
                    except Exception:
                        # Some versions return enum-like objects rather than ints
                        mask = val if mask == 0 else mask | val
                if exclusions:
                    content_flag = mask
                    print("DEBUG: Archive content flag exclusions: %s" % ','.join(exclusions))
    except Exception as flag_err:
        print("DEBUG: Could not resolve ProjectArchive flag enum: %s. Using default content." % flag_err)

    # Save unsaved edits first - the archive captures the on-disk project,
    # so without this step a "snapshot" tool would silently miss recent edits.
    try:
        primary_project.save()
        print("DEBUG: Saved unsaved edits before archiving.")
    except Exception as save_err:
        # Save can fail in narrow edge cases (read-only mount, etc.). The
        # archive is still useful from on-disk state; warn and continue.
        print("WARN: pre-archive save failed (%s); archive will reflect last on-disk state." % save_err)

    # Make the parent directory exist - save_archive does NOT create it.
    parent_dir = os.path.dirname(ARCHIVE_PATH)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir)

    # Some method signatures take (path, comment, content); others take only
    # (path) or (path, content). Try in order of preference.
    try:
        if content_flag is not None and COMMENT:
            save_fn(ARCHIVE_PATH, COMMENT, content_flag)
        elif content_flag is not None:
            save_fn(ARCHIVE_PATH, None, content_flag)
        elif COMMENT:
            save_fn(ARCHIVE_PATH, COMMENT)
        else:
            save_fn(ARCHIVE_PATH)
    except TypeError as sig_err:
        print("DEBUG: Signature mismatch (%s); retrying with path-only." % sig_err)
        save_fn(ARCHIVE_PATH)

    # Sanity-check the file was actually written.
    if not os.path.exists(ARCHIVE_PATH):
        raise RuntimeError(
            "Archive call returned without error but output file '%s' does not exist." %
            ARCHIVE_PATH
        )

    size_bytes = os.path.getsize(ARCHIVE_PATH)
    emit_result({
        u"archive_path": _to_unicode(ARCHIVE_PATH),
        u"size_bytes": size_bytes,
        u"comment": _to_unicode(COMMENT) if COMMENT else None,
        u"include_libraries": include_libs,
        u"include_compiled_libraries": include_compiled,
    })
    print("Archive created: %s (%d bytes)" % (ARCHIVE_PATH, size_bytes))
    print("SCRIPT_SUCCESS: Project archive saved.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error creating project archive: %s\n%s" % (e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
