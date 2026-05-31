import sys, scriptengine as script_engine, os, traceback

# Optional extra directory the caller wants scanned (in addition to defaults).
EXTRA_TEMPLATE_DIR = "{EXTRA_TEMPLATE_DIR}"

# Lists project templates known to this CODESYS install via two channels:
#   1) ScriptEngine API (if exposed in this SP) — picks up templates registered
#      by package installers (e.g. the ifm "CODESYS for all ifm edgeController"
#      package), which don't necessarily exist as free-standing .project files.
#   2) Filesystem scan of well-known template directories — picks up any
#      `.project` / `.projecttemplate` left behind by users or installers that
#      bypass the registered Template Manager.
#
# Names returned here can be passed to create_project(templateName=...). Paths
# returned can be passed to create_project(templatePath=...).

def _to_text(v):
    if v is None:
        return None
    try:
        if isinstance(v, unicode):
            return v
        return unicode(v)
    except Exception:
        try:
            return str(v)
        except Exception:
            return None

def _probe(obj, attrs):
    """Read the first attribute on obj that returns a non-empty value.

    Tries plain attribute access first; if the attribute is callable, calls it
    with no args, then with ('en',) (CODESYS localised getters take a locale).
    """
    for a in attrs:
        if obj is None or not hasattr(obj, a):
            continue
        try:
            v = getattr(obj, a)
            if callable(v):
                try:
                    v = v()
                except TypeError:
                    try:
                        v = v(u'en')
                    except Exception:
                        continue
                except Exception:
                    continue
            if v is None:
                continue
            t = _to_text(v)
            if t is not None and t != u"":
                return t
        except Exception:
            continue
    return None

try:
    templates = []
    seen = set()
    api_attempts = []

    # 1) ScriptEngine API probe. The exact attribute differs by SP.
    projects = getattr(script_engine, 'projects', None)
    if projects is not None:
        for attr_name in ('templates', 'list_templates', 'get_templates', 'get_all_templates'):
            attr = getattr(projects, attr_name, None)
            if attr is None:
                continue
            api_attempts.append(attr_name)
            try:
                listing = attr() if callable(attr) else attr
                try:
                    listing = list(listing)
                except TypeError:
                    listing = [listing]
                print("DEBUG: script_engine.projects.%s -> %d entries" % (attr_name, len(listing)))
                for t in listing:
                    name = _probe(t, ('name', 'display_name', 'title', 'identifier'))
                    tpath = _probe(t, ('path', 'file', 'location', 'filename'))
                    key = (name or u'', tpath or u'')
                    if not name and not tpath:
                        continue
                    if key in seen:
                        continue
                    templates.append({
                        u'name': name,
                        u'path': tpath,
                        u'source': u'scriptengine.projects.%s' % attr_name,
                    })
                    seen.add(key)
            except Exception as e:
                print("DEBUG: script_engine.projects.%s failed: %s" % (attr_name, e))

    # 2) Filesystem scan.
    program_data = os.environ.get('ProgramData') or os.environ.get('ALLUSERSPROFILE') or 'C:\\ProgramData'
    candidate_dirs = []
    candidate_dirs.append(os.path.join(program_data, 'CODESYS', 'Templates'))
    candidate_dirs.append(os.path.join(program_data, 'CODESYS', 'CODESYS', 'Templates'))
    # Devices/ holds device packages; some ifm packages drop .project templates
    # inside their device subtree. We don't walk all 100k+ entries — limit to
    # one level deep on each device to keep this fast.
    devices_root = os.path.join(program_data, 'CODESYS', 'Devices')
    if EXTRA_TEMPLATE_DIR:
        candidate_dirs.append(EXTRA_TEMPLATE_DIR)

    template_exts = ('.project', '.projecttemplate', '.projectarchive')
    fs_hits = 0

    def _scan(dir_path, depth_limit=None):
        global fs_hits
        if not os.path.isdir(dir_path):
            return
        start_depth = dir_path.count(os.sep)
        for root, dirs, files in os.walk(dir_path):
            if depth_limit is not None and (root.count(os.sep) - start_depth) > depth_limit:
                dirs[:] = []
                continue
            for f in files:
                fl = f.lower()
                if not any(fl.endswith(ext) for ext in template_exts):
                    continue
                full = os.path.join(root, f)
                name = os.path.splitext(f)[0]
                key = (_to_text(name) or u'', _to_text(full) or u'')
                if key in seen:
                    continue
                templates.append({
                    u'name': _to_text(name),
                    u'path': _to_text(full),
                    u'source': u'filesystem:%s' % _to_text(dir_path),
                })
                seen.add(key)
                fs_hits += 1

    for d in candidate_dirs:
        _scan(d)
    # Devices tree can be very deep; cap depth.
    _scan(devices_root, depth_limit=4)

    # Final result. Caller sees both sources so they know whether the template
    # came from the registered Template Manager (use mode=name) or a file on
    # disk (use mode=path). emit_result is provided by _text_utils, which the
    # TS-side prepares via prepareScriptWithHelpers and prepends inline.
    emit_result({
        u'templates': templates,
        u'count': len(templates),
        u'api_attempts': api_attempts,
        u'filesystem_hits': fs_hits,
    })
    print("Templates listed: %d (api_attempts=%s, fs_hits=%d)" % (len(templates), api_attempts, fs_hits))
    print("SCRIPT_SUCCESS: list_project_templates complete.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error listing project templates: %s\n%s" % (e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
