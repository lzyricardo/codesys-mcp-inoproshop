import sys, scriptengine as script_engine, os, traceback, re

OLD_NAME = "{OLD_NAME}"
NEW_NAME = "{NEW_NAME}"
DRY_RUN = "{DRY_RUN}"  # "1" / "0"
INCLUDE_DECL = "{INCLUDE_DECL}"  # "1" / "0"
INCLUDE_IMPL = "{INCLUDE_IMPL}"  # "1" / "0"

# IEC 61131-3 reserved keywords - rename_symbol refuses these as the new name
# to avoid producing uncompilable projects.
IEC_KEYWORDS = set([
    'IF', 'THEN', 'ELSIF', 'ELSE', 'END_IF', 'CASE', 'OF', 'END_CASE',
    'FOR', 'TO', 'BY', 'DO', 'END_FOR', 'WHILE', 'END_WHILE', 'REPEAT',
    'UNTIL', 'END_REPEAT', 'EXIT', 'CONTINUE', 'RETURN', 'JMP',
    'PROGRAM', 'END_PROGRAM', 'FUNCTION', 'END_FUNCTION', 'FUNCTION_BLOCK',
    'END_FUNCTION_BLOCK', 'VAR', 'VAR_INPUT', 'VAR_OUTPUT', 'VAR_IN_OUT',
    'VAR_GLOBAL', 'VAR_TEMP', 'VAR_EXTERNAL', 'VAR_CONFIG', 'VAR_ACCESS',
    'END_VAR', 'CONSTANT', 'RETAIN', 'NON_RETAIN', 'PERSISTENT',
    'TYPE', 'END_TYPE', 'STRUCT', 'END_STRUCT', 'ARRAY', 'STRING', 'WSTRING',
    'TRUE', 'FALSE', 'AT', 'NULL',
    'AND', 'OR', 'XOR', 'NOT', 'MOD',
    'BOOL', 'BYTE', 'WORD', 'DWORD', 'LWORD',
    'SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT',
    'REAL', 'LREAL', 'TIME', 'DATE', 'TIME_OF_DAY', 'TOD', 'DATE_AND_TIME', 'DT',
])

try:
    print("DEBUG: rename_symbol: '%s' -> '%s' dryRun=%s decl=%s impl=%s" %
          (OLD_NAME, NEW_NAME, DRY_RUN, INCLUDE_DECL, INCLUDE_IMPL))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not OLD_NAME:
        raise ValueError("oldName is required.")
    if not NEW_NAME:
        raise ValueError("newName is required.")
    if OLD_NAME == NEW_NAME:
        raise ValueError("oldName and newName are identical; nothing to do.")
    if NEW_NAME.upper() in IEC_KEYWORDS:
        raise ValueError(
            "newName '%s' is an IEC 61131-3 reserved keyword. Renaming to a "
            "keyword would produce an uncompilable project." % NEW_NAME
        )
    # Basic IEC identifier syntax check on newName: must start with a letter
    # or underscore, contain only [A-Za-z0-9_]. CODESYS will reject worse
    # things later but a clear error here is friendlier.
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', NEW_NAME):
        raise ValueError(
            "newName '%s' is not a valid IEC identifier (must start with letter "
            "or underscore, contain only [A-Za-z0-9_])." % NEW_NAME
        )

    dry_run = (DRY_RUN == "1")
    include_decl = (INCLUDE_DECL == "1")
    include_impl = (INCLUDE_IMPL == "1")

    rx = re.compile(r"\b" + re.escape(OLD_NAME) + r"\b")

    # Phase 1: collect all (section_obj, original_text, new_text, hits) tuples.
    # No writes happen here. If anything throws during traversal we just abort
    # before mutating the project.
    plan = []  # list of {section_obj, current_path, section, original_text, new_text, hits, match_count}

    def _scan_section(obj, section_name, attr_name, current_path):
        if not hasattr(obj, attr_name):
            return
        try:
            section_obj = getattr(obj, attr_name)
        except Exception:
            return
        if section_obj is None or not hasattr(section_obj, 'text'):
            return
        try:
            text = section_obj.text
        except Exception:
            return
        if not text:
            return
        text_u = _to_unicode(text)
        match_count = 0
        line_hits = []
        for line_no, line in enumerate(text_u.splitlines(), start=1):
            for m in rx.finditer(line):
                match_count += 1
                line_hits.append({
                    u"line": line_no,
                    u"col": m.start() + 1,
                    u"before": line.rstrip(),
                })
        if match_count == 0:
            return
        new_text = rx.sub(NEW_NAME, text_u)
        plan.append({
            'section_obj': section_obj,
            'current_path': current_path,
            'section': section_name,
            'original_text': text_u,
            'new_text': new_text,
            'hits': line_hits,
            'match_count': match_count,
        })

    def _walk(obj, path_prefix):
        obj_name = getattr(obj, 'get_name', lambda: '?')()
        current_path = "%s/%s" % (path_prefix, obj_name) if path_prefix else obj_name
        if include_decl:
            _scan_section(obj, u"declaration", 'textual_declaration', current_path)
        if include_impl:
            _scan_section(obj, u"implementation", 'textual_implementation', current_path)
        try:
            for child in obj.get_children(False):
                _walk(child, current_path)
        except Exception:
            pass

    try:
        for child in primary_project.get_children(False):
            _walk(child, "")
    except Exception as walk_err:
        raise RuntimeError("Traversal failed before any writes: %s" % walk_err)

    total_matches = sum(p['match_count'] for p in plan)
    changes = []  # public per-section change records returned to caller

    if dry_run or total_matches == 0:
        for p in plan:
            changes.append({
                u"path": _to_unicode(p['current_path']),
                u"section": p['section'],
                u"match_count": p['match_count'],
                u"hits": p['hits'],
                u"applied": False,
            })
    else:
        # Phase 2: apply writes. We track which sections succeeded so the caller
        # can recover or revert via reopen if anything fails. CODESYS scripting
        # has no transaction primitive - we save() ONLY when every section
        # rewrites cleanly. If a section throws, we DO NOT save, leaving the
        # on-disk project untouched and surfacing the partial in-memory state
        # to the caller.
        applied_sections = []
        first_failure = None
        for p in plan:
            try:
                if not hasattr(p['section_obj'], 'replace'):
                    raise TypeError("section has no replace() method")
                p['section_obj'].replace(p['new_text'])
                applied_sections.append(p)
                changes.append({
                    u"path": _to_unicode(p['current_path']),
                    u"section": p['section'],
                    u"match_count": p['match_count'],
                    u"hits": p['hits'],
                    u"applied": True,
                })
            except Exception as write_err:
                if first_failure is None:
                    first_failure = (p, write_err)
                changes.append({
                    u"path": _to_unicode(p['current_path']),
                    u"section": p['section'],
                    u"match_count": p['match_count'],
                    u"hits": p['hits'],
                    u"applied": False,
                    u"error": _to_unicode(str(write_err)),
                })

        if first_failure is not None:
            # Don't save - the project on disk stays clean. The in-memory
            # state has partial mutations though, so we tell the caller to
            # reopen the project to discard them.
            failed_path = first_failure[0]['current_path']
            failed_err = first_failure[1]
            raise RuntimeError(
                "Rename failed at section '%s/%s' (%s). %d/%d sections were "
                "rewritten in memory but the project was NOT saved - reopen "
                "the project to discard the in-memory changes." %
                (failed_path, first_failure[0]['section'], failed_err,
                 len(applied_sections), len(plan))
            )

        try:
            print("DEBUG: All sections rewritten; saving project...")
            primary_project.save()
            print("DEBUG: Saved.")
        except Exception as save_err:
            raise RuntimeError(
                "All %d sections rewritten in memory but project.save() failed: %s. "
                "Reopen the project to discard the in-memory changes." %
                (len(applied_sections), save_err)
            )

    applied_count = sum(1 for c in changes if c.get(u"applied"))

    emit_result({
        u"old_name": _to_unicode(OLD_NAME),
        u"new_name": _to_unicode(NEW_NAME),
        u"dry_run": dry_run,
        u"changes": changes,
        u"total_matches": total_matches,
        u"applied_count": applied_count,
        u"section_count": len(plan),
    })
    print("Total matches: %d (applied=%d, dry_run=%s)" % (total_matches, applied_count, dry_run))
    print("SCRIPT_SUCCESS: rename_symbol complete.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error in rename_symbol: %s\n%s" % (e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
