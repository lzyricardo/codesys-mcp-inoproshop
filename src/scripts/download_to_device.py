import sys, scriptengine as script_engine, os, traceback

# MODE controls download strategy:
#   'auto' (default) - try online change, fall back to full download.
#   'online_change'  - online change only; raise if rejected (no fallback).
#   'full'           - skip online change attempt, force full download.
MODE = "{MODE}"


def _login(online_app, mode):
    """Perform the login that pushes new code to the PLC.

    In CODESYS V3 there's no separate `download()` method on
    `IScriptOnlineApplication` — the download happens as part of login,
    driven by the `OnlineChangeOption` argument. So this is really the
    "push code" function:
      - `.Force` = full download
      - `.Try`   = try online change, server-side falls back to full if
                   the change is rejected
      - `.Never` = online change only; raises if the change is rejected
      - `.Keep`  = leave existing application on the PLC, attach to it

    All calls go through `with_executor` so the scripting executor
    fires Executing/Executed and the IDE-internal _executionStack is
    populated; otherwise login also hits "Stack empty" on a real PLC.
    """
    if not hasattr(online_app, 'login'):
        raise TypeError("Online application does not support login().")

    has_oco = hasattr(script_engine, 'OnlineChangeOption')

    if mode == 'full':
        if has_oco:
            with_executor(
                online_app.login,
                script_engine.OnlineChangeOption.Force,
                False,
            )
            print("DEBUG: Logged in (Force / full download).")
        else:
            with_executor(online_app.login)
            print("DEBUG: Logged in (no OnlineChangeOption, plain login).")
        return

    if mode == 'online_change':
        if not has_oco:
            raise RuntimeError(
                "OnlineChangeOption not available in this CODESYS "
                "version; use mode='full' instead."
            )
        try:
            with_executor(
                online_app.login,
                script_engine.OnlineChangeOption.Never,
                False,
            )
            print("DEBUG: Logged in (online-change-only mode).")
        except Exception as e:
            raise RuntimeError(
                "Online change rejected: %s. The change may be "
                "structural; use mode='full' or mode='auto' to allow a "
                "full download." % e
            )
        return

    # mode == 'auto' (default)
    if not has_oco:
        with_executor(online_app.login)
        print("DEBUG: Logged in (no OnlineChangeOption, plain login).")
        return

    try:
        with_executor(
            online_app.login,
            script_engine.OnlineChangeOption.Try,
            False,
        )
        print("DEBUG: Logged in (Try online change).")
    except Exception as e:
        print("DEBUG: Try login failed, falling back to Force: %s" % e)
        with_executor(
            online_app.login,
            script_engine.OnlineChangeOption.Force,
            False,
        )
        print("DEBUG: Logged in (Force after Try fallback).")


try:
    print("DEBUG: download_to_device: Project='%s' Mode='%s'" % (
        PROJECT_FILE_PATH, MODE))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    _login(online_app, MODE)

    # After login the new code is on the PLC. Build the boot
    # application so the change survives a power cycle. Not all
    # IScriptOnlineApplication implementations expose this — skip
    # silently if unavailable.
    if hasattr(online_app, 'create_boot_application'):
        try:
            with_executor(online_app.create_boot_application)
            print("DEBUG: Boot application created.")
        except Exception as boot_err:
            # Boot creation failure is non-fatal for the download
            # itself — the runtime has the new code, it just won't
            # survive power-cycle. Log and move on.
            print("WARN: create_boot_application failed: %s" % boot_err)

    print("Downloaded to device for application: %s" % app_name)
    print("SCRIPT_SUCCESS: Application downloaded to device successfully.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error downloading to device for project %s: %s\n%s" % (
        PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
