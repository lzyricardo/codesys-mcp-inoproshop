import traceback
# --- Find object by path function ---
def find_object_by_path_robust(start_node, full_path, target_type_name="object"):
    # Handle both dot and slash separators. Normalise backslashes first.
    path_with_slashes = full_path.replace('\\', '/').strip('/')
    # Only treat '.' as a separator when no '/' separator was used at all -
    # otherwise we corrupt namespaced names like 'MyLib.MyType' that
    # legitimately contain a dot inside a single path segment.
    if '/' in path_with_slashes:
        normalized_path = path_with_slashes
    else:
        normalized_path = path_with_slashes.replace('.', '/')
    path_parts = [p for p in normalized_path.split('/') if p]
    if not path_parts:
        print("ERROR: Path is empty.")
        return None

    # Determine the actual starting node (project or application)
    project = start_node
    if not hasattr(start_node, 'active_application') and hasattr(start_node, 'project'):
         try: project = start_node.project
         except Exception as proj_ref_err:
             print("WARN: Could not get project reference from start_node: %s" % proj_ref_err)

    # Try to get the application object robustly if we think we have the project
    app = None
    if hasattr(project, 'active_application'):
        try: app = project.active_application
        except Exception: pass
        if not app:
            try:
                 apps = project.find("Application", True)
                 if apps: app = apps[0]
            except Exception: pass

    app_name_lower = ""
    if app:
        try: app_name_lower = (app.get_name() or "application").lower()
        except Exception: app_name_lower = "application"

    # Decide where to start the traversal
    current_obj = start_node
    if hasattr(project, 'active_application'):
        if app and path_parts[0].lower() == app_name_lower:
             current_obj = app
             path_parts = path_parts[1:]
             if not path_parts:
                 return current_obj
        else:
            current_obj = project

    # Traverse the remaining path parts
    parent_path_str = getattr(current_obj, 'get_name', lambda: str(current_obj))()

    for i, part_name in enumerate(path_parts):
        is_last_part = (i == len(path_parts) - 1)
        found_in_parent = None
        try:
            children_of_current = current_obj.get_children(False)
            for child in children_of_current:
                 child_name = getattr(child, 'get_name', lambda: None)()
                 if child_name == part_name:
                     found_in_parent = child
                     break

            # If not found directly AND it's the last part, try recursive find.
            if not found_in_parent and is_last_part:
                 found_recursive_list = current_obj.find(part_name, True)
                 if found_recursive_list:
                     # Refuse to silently pick the first match when ambiguous -
                     # the caller asked for a specific path.
                     if len(found_recursive_list) > 1:
                         print("ERROR: Recursive find for '%s' under '%s' is ambiguous (%d matches). Refusing to pick a winner." % (part_name, parent_path_str, len(found_recursive_list)))
                         return None
                     found_in_parent = found_recursive_list[0]

            if found_in_parent:
                current_obj = found_in_parent
                parent_path_str = getattr(current_obj, 'get_name', lambda: part_name)()
            else:
                print("ERROR: Path part '%s' not found under '%s'." % (part_name, parent_path_str))
                return None

        except Exception as find_err:
            print("ERROR: Exception while searching for '%s' under '%s': %s" % (part_name, parent_path_str, find_err))
            traceback.print_exc()
            return None

    # Final verification: name on the resolved object must match the last requested part.
    final_expected_name = path_parts[-1] if path_parts else full_path.split('/')[-1]
    found_final_name = getattr(current_obj, 'get_name', lambda: None)()

    if found_final_name == final_expected_name:
        return current_obj
    else:
        print("ERROR: Traversal ended on object '%s' but expected final name was '%s'." % (found_final_name, final_expected_name))
        return None

# --- End of find object function ---
