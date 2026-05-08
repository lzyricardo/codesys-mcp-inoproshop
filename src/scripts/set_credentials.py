import sys, traceback

USERNAME = "{USERNAME}"
PASSWORD = "{PASSWORD}"

try:
    print("DEBUG: set_credentials: user='%s' password=<%d chars>" % (
        USERNAME, len(PASSWORD)))
    if not USERNAME:
        raise ValueError(
            "Username is required. CODESYS set_default_credentials rejects "
            "empty strings. If your runtime has no authentication, simply "
            "do not call set_credentials and let connect_to_device proceed."
        )
    import scriptengine as se
    if not hasattr(se.online, 'set_default_credentials'):
        raise RuntimeError(
            "scriptengine.online.set_default_credentials is not available "
            "in this CODESYS version."
        )
    se.online.set_default_credentials(USERNAME, PASSWORD)
    print("Credentials set on default scope (applies to subsequent logins).")
    print("SCRIPT_SUCCESS")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error setting credentials: %s\n%s" % (e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
