import os
import scriptengine as script_engine


def require_project_open(target_project_path):
    """Read-only sibling of ensure_project_open.

    Returns the primary project iff its path matches the requested one.
    Never opens, closes, or switches projects - this is the helper to use
    in resource handlers and any tool that should fail loudly rather than
    silently swap project context.

    Raises RuntimeError with a clear message when no project is open or
    when a different project is currently primary.
    """
    cleaned = target_project_path.strip('"\'')
    normalized = os.path.normcase(os.path.abspath(cleaned))

    try:
        primary = script_engine.projects.primary
    except Exception as e:
        raise RuntimeError(
            "Could not access script_engine.projects.primary: %s. "
            "CODESYS may be in an unstable state - try get_codesys_status." % e
        )
    if primary is None:
        raise RuntimeError(
            "No project is currently open. Call open_project('%s') first; "
            "this tool is read-only and will not open a project on your behalf." %
            target_project_path
        )

    try:
        primary_path = os.path.normcase(os.path.abspath(primary.path))
    except Exception as e:
        raise RuntimeError(
            "Could not read path of currently-primary project: %s" % e
        )

    if primary_path != normalized:
        raise RuntimeError(
            "Requested project '%s' is not the currently-open one (primary is '%s'). "
            "This is a read-only tool and refuses to switch projects; call "
            "open_project explicitly first." % (target_project_path, primary.path)
        )
    return primary


# Placeholder for the project file path (must be set in scripts using this helper).
# Mirrors the same convention as ensure_project_open.py.
PROJECT_FILE_PATH = "{PROJECT_FILE_PATH}"
