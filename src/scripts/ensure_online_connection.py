import traceback

# --- Function to ensure an online connection to the active application ---
def ensure_online_connection(primary_project):
    """Get or create an online application connection for the active application."""
    print("DEBUG: Ensuring online connection...")

    target_app = None
    app_name = "N/A"

    # Try getting active application
    try:
        target_app = primary_project.active_application
        if target_app:
            app_name = getattr(target_app, 'get_name', lambda: "Unnamed App")()
    except Exception as e:
        print("WARN: Could not get active application: %s" % e)

    # Search for first application if no active
    if not target_app:
        try:
            all_children = primary_project.get_children(True)
            for child in all_children:
                if hasattr(child, 'is_application') and child.is_application:
                    target_app = child
                    app_name = getattr(child, 'get_name', lambda: "Unnamed App")()
                    break
        except Exception as e:
            print("WARN: Error finding application: %s" % e)

    if not target_app:
        raise RuntimeError("No application found in project.")

    print("DEBUG: Using application: %s" % app_name)

    # Try to get or create online application
    online_app = None

    # Pattern 1: app.create_online_application()
    if hasattr(target_app, 'create_online_application'):
        try:
            online_app = target_app.create_online_application()
            if online_app:
                print("DEBUG: Created online application via app.create_online_application()")
                return online_app, target_app
        except Exception as e:
            print("DEBUG: app.create_online_application() failed: %s" % e)

    # Pattern 2: scriptengine online module
    try:
        import scriptengine as se
        if hasattr(se, 'online'):
            online_module = se.online
            if hasattr(online_module, 'create_online_application'):
                try:
                    online_app = online_module.create_online_application(target_app)
                    if online_app:
                        print("DEBUG: Created online application via scriptengine.online.create_online_application()")
                        return online_app, target_app
                except Exception as e:
                    print("DEBUG: scriptengine.online.create_online_application() failed: %s" % e)
    except Exception as e:
        print("DEBUG: scriptengine online module access failed: %s" % e)

    # Pattern 3: Check if there's already an online_application property
    if hasattr(target_app, 'online_application'):
        try:
            online_app = target_app.online_application
            if online_app:
                print("DEBUG: Found existing online application via app.online_application")
                return online_app, target_app
        except Exception as e:
            print("DEBUG: app.online_application failed: %s" % e)

    if not online_app:
        raise RuntimeError("Could not create online application connection. Ensure a device/gateway is configured in the project.")

    return online_app, target_app
# --- End of ensure_online_connection function ---
