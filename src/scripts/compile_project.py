import sys, scriptengine as script_engine, os, traceback, json
import tempfile
try:
    import StringIO  # IronPython 2.7 / Python 2
except ImportError:
    try:
        from io import StringIO as _IOStringIO
        class StringIO(object):  # shim that quacks like StringIO.StringIO
            class StringIO(_IOStringIO):
                pass
    except Exception:
        StringIO = None

# Build / code-check message category GUIDs (CODESYS V3 internal).
# These are the categories that contain the actual compile-time errors /
# warnings, discovered via system.get_message_categories().
#
# - 'Build'                  : 97F48D64-A2A3-4856-B640-75C046E37EA9
# - 'Additional code checks' : 220493A1-F49B-4416-9A3F-A545DB707CBE
# - 'Precompile'             : 217BC73E-759B-4A3C-BFA1-991C938A6541
#
# These are kept only as a fallback when system.get_message_categories()
# enumeration fails. The script now scans every category the runtime
# exposes (see "Discover all message categories dynamically" below).
COMPILE_CATEGORY_GUIDS = [
    '97F48D64-A2A3-4856-B640-75C046E37EA9',  # Build
    '220493A1-F49B-4416-9A3F-A545DB707CBE',  # Additional code checks
    '217BC73E-759B-4A3C-BFA1-991C938A6541',  # Precompile
]

# --- Stable post-mortem debug file ---
# Mirror every print() this script emits to a file at a deterministic
# location. The Node-side server.ts handler can swallow result.output in
# certain success branches, leaving callers unable to see the DEBUG/WARN
# diagnostics that the script generates. With this mirror, the full
# diagnostic trace is always retrievable via:
#   %TEMP%\codesys-mcp-compile-debug.txt
# Overwritten on every compile_project call -- treat as "last run only".
_COMPILE_DEBUG_PATH = os.path.join(tempfile.gettempdir(), 'codesys-mcp-compile-debug.txt')
_ORIG_STDOUT = sys.stdout
_DEBUG_BUFFER = StringIO.StringIO() if StringIO is not None else None

class _Tee(object):
    """Write to multiple sinks. Tolerant of any sink raising on write."""
    def __init__(self, *sinks):
        self._sinks = sinks
    def write(self, data):
        for s in self._sinks:
            try:
                s.write(data)
            except Exception:
                pass
    def flush(self):
        for s in self._sinks:
            try:
                if hasattr(s, 'flush'):
                    s.flush()
            except Exception:
                pass

if _DEBUG_BUFFER is not None:
    sys.stdout = _Tee(_ORIG_STDOUT, _DEBUG_BUFFER)

def _flush_debug_to_file():
    """Write the captured stdout to the debug file. Best effort."""
    if _DEBUG_BUFFER is None:
        return
    try:
        content = _DEBUG_BUFFER.getvalue()
        if isinstance(content, unicode):
            content_bytes = content.encode('utf-8')
        else:
            content_bytes = content
        with open(_COMPILE_DEBUG_PATH, 'wb') as f:
            f.write(content_bytes)
    except Exception:
        pass

try:
    print("DEBUG: compile_project script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    project_name = os.path.basename(PROJECT_FILE_PATH)

    # --- Locate the application to compile ---
    # --- Locate target: application (standard project) OR pool root (library) ---
    #
    # Standard `.project` files have an Application node under which Build
    # (F11) runs. Library `.library` files do NOT; their POU/DUT/GVL live
    # as Pool Objects at the project root, and the UI equivalent of F11 is
    # "Build > Check all Pool Objects". We detect the project kind and dispatch
    # accordingly. Detection order:
    #   1. active_application (fastest, works on any standard project)
    #   2. iterate children for is_application markers
    #   3. file extension is .library
    #   4. give up
    target_app = None
    app_name = "N/A"
    project_kind = "unknown"  # 'application' | 'library' | 'unknown'

    try:
        target_app = primary_project.active_application
        if target_app:
            app_name = getattr(target_app, 'get_name', lambda: "Unnamed App (Active)")()
            print("DEBUG: Found active application: %s" % app_name)
            project_kind = "application"
    except Exception as active_err:
        print("WARN: Could not get active application: %s. Searching..." % active_err)

    if not target_app:
        print("DEBUG: Searching for first compilable application...")
        apps = []
        try:
            all_children = primary_project.get_children(True)
            for child in all_children:
                if hasattr(child, 'is_application') and child.is_application and hasattr(child, 'generate_code'):
                    app_name_found = getattr(child, 'get_name', lambda: "Unnamed App")()
                    print("DEBUG: Found potential application object: %s" % app_name_found)
                    apps.append(child)
                    break
        except Exception as find_err:
            print("WARN: Error finding application object: %s" % find_err)

        if apps:
            target_app = apps[0]
            app_name = getattr(target_app, 'get_name', lambda: "Unnamed App (First Found)")()
            project_kind = "application"
            print("WARN: Compiling first found application: %s" % app_name)
        else:
            # No Application node anywhere. Could be a library project.
            is_library_ext = PROJECT_FILE_PATH.lower().endswith('.library')
            has_lib_marker = (
                (hasattr(primary_project, 'is_library') and getattr(primary_project, 'is_library', False)) or
                (hasattr(primary_project, 'IsLibrary') and getattr(primary_project, 'IsLibrary', False))
            )
            if is_library_ext or has_lib_marker:
                project_kind = "library"
                app_name = "(library pool)"
                print("DEBUG: Library project detected (ext=%s, marker=%s); will use Check-all-Pool-Objects path."
                      % (is_library_ext, has_lib_marker))
            else:
                raise RuntimeError(
                    "No compilable target found in project '%s' (no Application node and not a .library file)." % project_name
                )

    # --- Save any pending edits so the build sees them ---
    try:
        if hasattr(primary_project, 'dirty') and primary_project.dirty:
            if hasattr(primary_project, 'save'):
                primary_project.save()
                print("DEBUG: Saved dirty project before build.")
    except Exception as save_err:
        print("WARN: Pre-build save failed (continuing): %s" % save_err)

    # --- Discover all message categories dynamically ---
    #
    # Hardcoded GUIDs (Build / Additional code checks / Precompile) cover the
    # common cases but on bigger projects compile errors land in OTHER
    # categories too (e.g. Library Manager, POU-specific, project-tree).
    # Enumerate every category exposed by the runtime; fall back to the
    # hardcoded triple if enumeration fails. Each entry is (Guid, name_str).
    # NOTE: Guid is the .NET type exposed as script_engine.Guid, not a Python
    # builtin -- using bare Guid("{...}") raises NameError silently.
    all_categories = []
    enum_used = "unknown"
    try:
        cats = script_engine.system.get_message_categories() if hasattr(
            script_engine.system, 'get_message_categories'
        ) else None
        if cats is not None:
            enum_used = "dynamic"
            for cat in cats:
                cat_guid = None
                cat_name = None
                try:
                    if hasattr(cat, 'guid'):
                        cat_guid = cat.guid
                        cat_name = getattr(cat, 'description', None) or getattr(cat, 'name', None)
                    elif isinstance(cat, (tuple, list)) and len(cat) > 0:
                        cat_guid = cat[0]
                        if len(cat) > 1:
                            cat_name = cat[1]
                    else:
                        # Probably a bare Guid
                        cat_guid = cat
                except Exception:
                    pass
                if cat_guid is None:
                    continue
                if cat_name is None:
                    try:
                        cat_name = script_engine.system.get_message_category_description(cat_guid)
                    except Exception:
                        cat_name = str(cat_guid)
                all_categories.append((cat_guid, cat_name))
    except Exception as cat_enum_err:
        print("WARN: get_message_categories() enumeration failed: %s" % cat_enum_err)

    if not all_categories:
        print("DEBUG: Dynamic enumeration empty -- falling back to hardcoded compile categories.")
        enum_used = "fallback"
        for guid_str in COMPILE_CATEGORY_GUIDS:
            try:
                cat_guid = script_engine.Guid('{%s}' % guid_str)
                try:
                    cat_name = script_engine.system.get_message_category_description(cat_guid)
                except Exception:
                    cat_name = guid_str
                all_categories.append((cat_guid, cat_name))
            except Exception as fallback_err:
                print("WARN: hardcoded fallback for %s failed: %s" % (guid_str, fallback_err))

    print("DEBUG: %d message categories will be scanned (source: %s)"
          % (len(all_categories), enum_used))
    for idx, (cg, cn) in enumerate(all_categories):
        print("DEBUG:   [%d] %s   (guid=%s)" % (idx, cn, cg))

    # --- Clear cached messages in every discovered category ---
    # Without this, get_message_objects() returns stale entries from prior
    # builds and severity counts are wrong.
    for cat_guid, cat_name in all_categories:
        try:
            script_engine.system.clear_messages(cat_guid)
        except Exception as clr_err:
            print("WARN: clear_messages('%s') failed: %s" % (cat_name, clr_err))

    # --- Trigger build ---
    # Dispatch based on project kind:
    #   - application: clean() + build() + generate_code() on the app node
    #   - library:     Check-all-Pool-Objects path (no Application exists)
    build_invoked = False

    if project_kind == "application":
        # Force a full rebuild by invalidating any precompile cache. Bigger
        # projects ship a `<name>.precompilecache` file; when valid, the
        # runtime may skip the semantic check entirely and emit zero errors
        # for code the UI would flag.
        if hasattr(target_app, 'clean'):
            try:
                target_app.clean()
                print("DEBUG: target_app.clean() executed for '%s'." % app_name)
            except Exception as clean_err:
                print("WARN: target_app.clean() raised: %s" % clean_err)
        if hasattr(target_app, 'clean_all'):
            try:
                target_app.clean_all()
                print("DEBUG: target_app.clean_all() executed for '%s'." % app_name)
            except Exception as clean_err:
                print("WARN: target_app.clean_all() raised: %s" % clean_err)

        # Call BOTH build() (F11 semantic check) and generate_code() (codegen).
        # On bigger applications generate_code() alone can short-circuit and
        # miss semantic errors; running both with clear_messages() upfront
        # keeps the message store correct.
        if hasattr(target_app, 'build'):
            try:
                target_app.build()
                print("DEBUG: build() executed for application '%s'." % app_name)
                build_invoked = True
            except Exception as build_err:
                print("WARN: build() raised: %s" % build_err)
        if hasattr(target_app, 'generate_code'):
            try:
                target_app.generate_code()
                print("DEBUG: generate_code() executed for application '%s'." % app_name)
                build_invoked = True
            except Exception as gen_err:
                print("WARN: generate_code() raised: %s" % gen_err)

    elif project_kind == "library":
        # Library projects have no Application node. The UI equivalent of F11
        # here is "Build > Check all Pool Objects". The scripting API exposes
        # this under one of several names depending on AB / CODESYS version;
        # try the documented ones and fall back to iterating pool objects.
        pool_method_names = (
            'check_all_pool_objects',
            'checkall_pool_objects',
            'check_pool_objects',
            'compile_pool_objects',
            'build_all',
            'check_all',
        )
        for mname in pool_method_names:
            if hasattr(primary_project, mname):
                try:
                    getattr(primary_project, mname)()
                    print("DEBUG: primary_project.%s() executed for library." % mname)
                    build_invoked = True
                    break
                except Exception as pool_err:
                    print("WARN: primary_project.%s() raised: %s" % (mname, pool_err))

        if not build_invoked:
            # Fallback: iterate every child, call .check()/.compile() on each
            # POU/DUT/GVL-like object. This is what AB's UI menu does under
            # the hood for libraries.
            print("DEBUG: No project-level pool-compile method worked; iterating children.")
            try:
                checked = 0
                for child in primary_project.get_children(True):
                    # Skip folders / namespaces / managers
                    if getattr(child, 'is_folder', False):
                        continue
                    for verb in ('check', 'compile', 'build'):
                        if hasattr(child, verb):
                            try:
                                getattr(child, verb)()
                                checked += 1
                                build_invoked = True
                            except Exception:
                                pass
                            break
                print("DEBUG: iterated pool: %d objects had a check/compile/build method that ran" % checked)
            except Exception as iter_err:
                print("WARN: pool-object iteration failed: %s" % iter_err)

    if not build_invoked:
        raise TypeError(
            "Target '%s' (kind=%s) supports no known compile entry point." % (app_name, project_kind)
        )

    # --- Collect messages from every compile category ---
    #
    # No severity_filter_mask passed to get_message_objects(): the bitwise OR
    # of Severity enum members is fragile across CODESYS versions (Severity is
    # sometimes a plain Enum, not [Flags]) and produces silent under-counts
    # where Warning messages come through but Error messages do not. On
    # AB 2.9 / CODESYS V3.5 SP19 this reproduces deterministically: a project
    # with 2 errors + 1 warning returns 1 entry (the warning), 0 errors.
    # Fetch everything and filter Python-side via the decoded severity string
    # -- robust across runtime versions.
    messages = []
    severity_labels = {}
    try:
        Severity = script_engine.Severity
        severity_labels = {
            Severity.FatalError: 'fatal',
            Severity.Error: 'error',
            Severity.Warning: 'warning',
            Severity.Information: 'info',
            Severity.Text: 'text',
        }
    except Exception as se_err:
        print("WARN: Could not set up severity labels: %s" % se_err)

    def _sev_to_string(sev):
        try:
            return severity_labels.get(sev, str(sev).lower())
        except Exception:
            return 'unknown'

    # Severities worth reporting. Info/text are noise (Build started, etc.).
    KEEP_SEVS = ('fatal', 'error', 'warning')

    # Helper to extract message fields uniformly.
    def _build_entry(msg, cat_name_override=None, sev_str_override=None):
        sev_str = sev_str_override or _sev_to_string(getattr(msg, 'severity', None))
        entry = {
            'category': cat_name_override or 'unknown',
            'severity': sev_str,
            'text': getattr(msg, 'text', getattr(msg, 'message', str(msg))),
        }
        if hasattr(msg, 'prefix') and hasattr(msg, 'number'):
            try:
                entry['code'] = "%s%s" % (msg.prefix, msg.number)
            except Exception:
                pass
        if hasattr(msg, 'object_name'):
            entry['object'] = msg.object_name
        elif hasattr(msg, 'source'):
            entry['object'] = str(msg.source)
        if hasattr(msg, 'line_number'):
            entry['line'] = msg.line_number
        elif hasattr(msg, 'position'):
            entry['line'] = msg.position
        return entry

    # Iterate the dynamic category list. Print a per-category severity
    # histogram unconditionally for diagnostic purposes (even when empty)
    # so the watcher.log captures the full state.
    seen_keys = set()
    for cat_guid, cat_name in all_categories:
        try:
            cat_msgs = script_engine.system.get_message_objects(cat_guid)
            if cat_msgs is None:
                print("DEBUG: category '%s': get_message_objects returned None" % cat_name)
                continue
            counts = {}
            collected_in_cat = 0
            for msg in cat_msgs:
                sev_raw = getattr(msg, 'severity', None)
                sev_str = _sev_to_string(sev_raw)
                counts[sev_str] = counts.get(sev_str, 0) + 1
                if sev_str not in KEEP_SEVS:
                    continue
                collected_in_cat += 1
                entry = _build_entry(msg, cat_name_override=cat_name)
                key = (entry.get('category'), entry.get('text'), entry.get('object'), entry.get('line'))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                messages.append(entry)
            print("DEBUG: category '%s' (%d msgs total, %d kept): %s"
                  % (cat_name, sum(counts.values()), collected_in_cat, counts))
        except Exception as cat_err:
            print("WARN: failed to collect messages for category '%s': %s"
                  % (cat_name, cat_err))

    # Defensive: ALSO query without a category filter. This catches messages
    # emitted into categories that get_message_categories() did not return
    # (newly-created categories, or categories owned by plugins not loaded
    # at enumeration time).
    try:
        if hasattr(script_engine.system, 'get_message_objects'):
            global_msgs = script_engine.system.get_message_objects()
            if global_msgs is not None:
                global_counts = {}
                added_from_global = 0
                for msg in global_msgs:
                    sev_raw = getattr(msg, 'severity', None)
                    sev_str = _sev_to_string(sev_raw)
                    global_counts[sev_str] = global_counts.get(sev_str, 0) + 1
                    if sev_str not in KEEP_SEVS:
                        continue
                    entry = _build_entry(msg, cat_name_override='(global)')
                    key = (None, entry.get('text'), entry.get('object'), entry.get('line'))
                    # Don't double-count messages already captured per-category.
                    # Match on (text, object, line) ignoring category.
                    alt_key_cat = lambda kc: (kc, entry.get('text'), entry.get('object'), entry.get('line'))
                    if any(alt_key_cat(c) in seen_keys for c in (entry.get('category'), 'unknown')):
                        # already covered (matched on (cat, text, obj, line)); leave it
                        # but the seen_keys is per-cat so global one with category=(global)
                        # might still slip in. Use a separate global de-dup:
                        pass
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    messages.append(entry)
                    added_from_global += 1
                print("DEBUG: GLOBAL get_message_objects() (no category filter): %d msgs total, %d added from global path: %s"
                      % (sum(global_counts.values()), added_from_global, global_counts))
    except Exception as global_err:
        print("WARN: global get_message_objects() failed: %s" % global_err)

    # --- Serialize as JSON between markers for the Node.js side to parse ---
    for entry in messages:
        for k in ('text', 'object', 'severity', 'category', 'code'):
            if k in entry:
                entry[k] = _to_unicode(entry[k])

    messages_json = json.dumps(messages, ensure_ascii=False, default=_json_default)
    if isinstance(messages_json, unicode):
        messages_json_bytes = messages_json.encode('utf-8')
    else:
        messages_json_bytes = messages_json
    sys.stdout.write("### COMPILE_MESSAGES_START ###\n")
    sys.stdout.write(messages_json_bytes)
    sys.stdout.write("\n### COMPILE_MESSAGES_END ###\n")
    sys.stdout.flush()

    print("Compile Initiated For Application: %s" % app_name)
    print("In Project: %s" % project_name)
    print("Message Count: %d" % len(messages))
    print("SCRIPT_SUCCESS: Application compilation initiated.")
    print("DEBUG: post-mortem debug trace at %s" % _COMPILE_DEBUG_PATH)
    _flush_debug_to_file()
    sys.stdout = _ORIG_STDOUT
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error initiating compilation for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    _flush_debug_to_file()
    sys.stdout = _ORIG_STDOUT
    sys.exit(1)
