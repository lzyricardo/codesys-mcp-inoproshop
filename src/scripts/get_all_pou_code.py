import sys, scriptengine as script_engine, os, traceback, json

try:
    print("DEBUG: get_all_pou_code script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    project_name = os.path.basename(PROJECT_FILE_PATH)

    all_code = []

    def collect_code(obj, path_prefix):
        # Recursively collect code from all objects that have textual content.
        obj_name = getattr(obj, 'get_name', lambda: '?')()
        current_path = "%s/%s" % (path_prefix, obj_name) if path_prefix else obj_name

        entry = None

        # Check for textual declaration
        decl_text = u""
        if hasattr(obj, 'textual_declaration'):
            try:
                td = obj.textual_declaration
                if td and hasattr(td, 'text'):
                    decl_text = _to_unicode(td.text) if td.text else u""
            except Exception:
                pass

        # Check for textual implementation
        impl_text = u""
        if hasattr(obj, 'textual_implementation'):
            try:
                ti = obj.textual_implementation
                if ti and hasattr(ti, 'text'):
                    impl_text = _to_unicode(ti.text) if ti.text else u""
            except Exception:
                pass

        if decl_text or impl_text:
            entry = {
                'path': _to_unicode(current_path),
                'type': _to_unicode(type(obj).__name__),
            }
            if decl_text:
                entry['declaration'] = decl_text
            if impl_text:
                entry['implementation'] = impl_text
            all_code.append(entry)

        # Recurse into children
        try:
            children = obj.get_children(False)
            for child in children:
                collect_code(child, current_path)
        except Exception:
            pass

    # Start from project root
    try:
        root_children = primary_project.get_children(False)
        for child in root_children:
            collect_code(child, "")
    except Exception as e:
        print("WARN: Error traversing project tree: %s" % e)

    code_json = json.dumps(all_code, ensure_ascii=False)
    if isinstance(code_json, unicode):
        code_json_bytes = code_json.encode('utf-8')
    else:
        code_json_bytes = code_json
    sys.stdout.write("### ALL_POU_CODE_START ###\n")
    sys.stdout.write(code_json_bytes)
    sys.stdout.write("\n### ALL_POU_CODE_END ###\n")
    sys.stdout.flush()
    print("Total POUs with code: %d" % len(all_code))
    print("SCRIPT_SUCCESS: All POU code retrieved.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error getting all POU code for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
