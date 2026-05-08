import sys, scriptengine as script_engine, os, traceback

POU_FULL_PATH = "{POU_FULL_PATH}"
CODE_START_MARKER = "### POU CODE START ###"
CODE_END_MARKER = "### POU CODE END ###"
DECL_START_MARKER = "### POU DECLARATION START ###"
DECL_END_MARKER = "### POU DECLARATION END ###"
IMPL_START_MARKER = "### POU IMPLEMENTATION START ###"
IMPL_END_MARKER = "### POU IMPLEMENTATION END ###"

def _emit_text(s):
    """Write a possibly-non-ASCII string to stdout as utf-8 bytes.

    Avoids `print` of unicode under IronPython subprocess stdout where the
    codec is undefined. Falls back through _to_unicode if the input is bytes.
    """
    if s is None:
        return
    if isinstance(s, unicode):
        sys.stdout.write(s.encode('utf-8'))
    else:
        try:
            sys.stdout.write(_to_unicode(s).encode('utf-8'))
        except Exception:
            sys.stdout.write(str(s))

try:
    print("DEBUG: Getting code: POU_FULL_PATH='%s', Project='%s'" % (POU_FULL_PATH, PROJECT_FILE_PATH))
    # Resource read - refuse to silently switch projects.
    primary_project = require_project_open(PROJECT_FILE_PATH)
    if not POU_FULL_PATH: raise ValueError("POU full path empty.")

    # Find the target POU/Method/Property object
    target_object = find_object_by_path_robust(primary_project, POU_FULL_PATH, "target object")
    if not target_object: raise ValueError("Target object not found using path: %s" % POU_FULL_PATH)

    target_name = getattr(target_object, 'get_name', lambda: POU_FULL_PATH)()
    print("DEBUG: Found target object: %s" % target_name)

    declaration_code = u""; implementation_code = u""

    # --- Get Declaration Part ---
    if hasattr(target_object, 'textual_declaration'):
        decl_obj = target_object.textual_declaration
        if decl_obj and hasattr(decl_obj, 'text'):
            try:
                declaration_code = _to_unicode(decl_obj.text) if decl_obj.text else u""
                print("DEBUG: Got declaration text.")
            except Exception as decl_read_err:
                print("ERROR: Failed to read declaration text: %s" % decl_read_err)
                declaration_code = u"/* ERROR reading declaration: %s */" % decl_read_err
        else:
            print("WARN: textual_declaration exists but is None or has no 'text' attribute.")
    else:
        print("WARN: No textual_declaration attribute.")

    # --- Get Implementation Part ---
    if hasattr(target_object, 'textual_implementation'):
        impl_obj = target_object.textual_implementation
        if impl_obj and hasattr(impl_obj, 'text'):
            try:
                implementation_code = _to_unicode(impl_obj.text) if impl_obj.text else u""
                print("DEBUG: Got implementation text.")
            except Exception as impl_read_err:
                print("ERROR: Failed to read implementation text: %s" % impl_read_err)
                implementation_code = u"/* ERROR reading implementation: %s */" % impl_read_err
        else:
            print("WARN: textual_implementation exists but is None or has no 'text' attribute.")
    else:
        print("WARN: No textual_implementation attribute.")


    print("Code retrieved for: %s" % target_name)
    sys.stdout.write("\n" + DECL_START_MARKER + "\n")
    _emit_text(declaration_code)
    sys.stdout.write("\n" + DECL_END_MARKER + "\n\n")
    sys.stdout.write(IMPL_START_MARKER + "\n")
    _emit_text(implementation_code)
    sys.stdout.write("\n" + IMPL_END_MARKER + "\n\n")
    sys.stdout.flush()

    print("SCRIPT_SUCCESS: Code retrieved.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error getting code for object '%s' in project '%s': %s\\n%s" % (POU_FULL_PATH, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
