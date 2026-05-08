import sys, scriptengine as script_engine, os, traceback

VENDOR_FILTER = "{VENDOR_FILTER}"  # case-insensitive substring; empty = no filter
NAME_FILTER = "{NAME_FILTER}"  # case-insensitive substring; empty = no filter
MAX_RESULTS_STR = "{MAX_RESULTS}"  # numeric string

# Read-only against the GLOBAL device repository - no project state needed.
# This is the substrate that validates inputs to add_device: instead of asking
# users to copy numeric ids out of the CODESYS UI, they enumerate the catalog
# here and pass canonical values.

try:
    print("DEBUG: list_device_repository: vendor='%s' name='%s' max=%s" %
          (VENDOR_FILTER, NAME_FILTER, MAX_RESULTS_STR))

    max_results = int(MAX_RESULTS_STR) if MAX_RESULTS_STR else 500
    vendor_filter_lc = VENDOR_FILTER.lower() if VENDOR_FILTER else ''
    name_filter_lc = NAME_FILTER.lower() if NAME_FILTER else ''

    # The repository accessor varies across CODESYS versions. Try the canonical
    # paths in order; the first one that returns an iterable wins.
    repo = None
    repo_attr_tried = []
    for attr in ('device_repository', 'device_descriptions', 'devicerepository'):
        repo_attr_tried.append(attr)
        candidate = getattr(script_engine, attr, None)
        if candidate is not None:
            repo = candidate
            print("DEBUG: Using script_engine.%s" % attr)
            break
    if repo is None:
        raise RuntimeError(
            "Could not locate the CODESYS device repository on script_engine. "
            "Tried: %s. Use the IDE Tools -> Device Repository dialog instead." %
            ', '.join(repo_attr_tried)
        )

    # Different SP versions expose the descriptor list under different names.
    # SP14+: get_all_devices() / get_devices(...); some builds also expose
    # a `devices` property. Probe methods FIRST (most reliable in modern SPs).
    listing = None
    listing_attr = None
    for method_name in ('get_all_devices', 'get_devices', 'list_all_devices'):
        method = getattr(repo, method_name, None)
        if method is not None and callable(method):
            try:
                listing = list(method())
                listing_attr = method_name + '()'
                print("DEBUG: Got listing via repo.%s() (%d entries)" % (method_name, len(listing)))
                break
            except Exception as e:
                print("DEBUG: repo.%s() failed: %s" % (method_name, e))
    if listing is None:
        for attr in ('devices', 'all_devices', 'descriptions'):
            candidate = getattr(repo, attr, None)
            if candidate is not None:
                try:
                    listing = list(candidate) if not callable(candidate) else list(candidate())
                    listing_attr = attr
                    print("DEBUG: Got listing via repo.%s (%d entries)" % (attr, len(listing)))
                    break
                except Exception as e:
                    print("DEBUG: repo.%s not iterable: %s" % (attr, e))
    if listing is None:
        # Final fallback: enumerate dir() and pick anything that looks like a
        # plural-noun property/method, so a future SP rename surfaces in the
        # error message rather than just dying with "not iterable".
        public = sorted([m for m in dir(repo) if not m.startswith('_')])
        try:
            listing = list(repo)
            listing_attr = 'iter(repo)'
            print("DEBUG: Got listing via iter(repo) (%d entries)" % len(listing))
        except Exception as e:
            raise RuntimeError(
                "Could not enumerate device repository. Tried get_all_devices, get_devices, "
                "list_all_devices, devices, all_devices, descriptions, and iter(repo). "
                "Repository object exposes: %s. Last error: %s" % (', '.join(public), e)
            )

    # `get_all_devices()` returns lightweight DeviceID handles (type/Id/Version
    # tuple). The actual descriptor metadata - name, vendor, category, etc. -
    # lives on a separate DeviceDescription object that we fetch via
    # `repo.get_device_description(device_id)`.
    get_desc = getattr(repo, 'get_device_description', None)

    def _coerce(v):
        if v is None:
            return None
        if isinstance(v, (int, long)):
            return int(v)
        try:
            return _to_unicode(unicode(v) if not isinstance(v, unicode) else v)
        except Exception:
            return None

    def _probe(obj, attrs):
        for a in attrs:
            if obj is not None and hasattr(obj, a):
                try:
                    v = getattr(obj, a)
                    if v is not None:
                        out = _coerce(v)
                        if out is not None and out != u"":
                            return out
                except Exception:
                    continue
        return None

    devices = []
    truncated = False
    for entry in listing:
        # Pull the structural ID from the entry (DeviceID has type/Id/Version).
        device_type = _probe(entry, ('type', 'device_type', 'type_id'))
        device_id_raw = _probe(entry, ('Id', 'id', 'device_id'))
        version_raw = _probe(entry, ('Version', 'version', 'device_version'))

        # Resolve the descriptor for human-readable fields. Cheap call - the
        # repo caches descriptors internally.
        desc = None
        if callable(get_desc):
            try:
                desc = get_desc(entry)
            except Exception:
                desc = None

        rec = {
            u'name': _probe(desc, ('name', 'display_name', 'description')) or _probe(entry, ('name', 'display_name')),
            u'vendor': _probe(desc, ('vendor', 'manufacturer')) or _probe(entry, ('vendor', 'manufacturer')),
            u'description': _probe(desc, ('description_text', 'description', 'long_description')),
            u'device_type': device_type if device_type is not None else _probe(desc, ('device_type', 'type', 'type_id')),
            u'device_id': device_id_raw if device_id_raw is not None else _probe(desc, ('device_id', 'id')),
            u'version': version_raw if version_raw is not None else _probe(desc, ('version', 'device_version')),
            u'category': _probe(desc, ('category', 'category_path')) or _probe(entry, ('category',)),
        }

        # Skip entries that don't match the optional filters (substring,
        # case-insensitive). An entry with a null vendor never matches a
        # vendor filter - that's the right semantic.
        if vendor_filter_lc and (rec[u'vendor'] is None or vendor_filter_lc not in rec[u'vendor'].lower()):
            continue
        if name_filter_lc and (rec[u'name'] is None or name_filter_lc not in rec[u'name'].lower()):
            continue

        devices.append(rec)
        if len(devices) >= max_results:
            truncated = True
            break

    emit_result({
        u"devices": devices,
        u"count": len(devices),
        u"truncated": truncated,
        u"total_in_repo": len(listing),
        u"repo_attribute": _to_unicode(listing_attr) if listing_attr else None,
        u"vendor_filter": _to_unicode(VENDOR_FILTER) if VENDOR_FILTER else None,
        u"name_filter": _to_unicode(NAME_FILTER) if NAME_FILTER else None,
    })
    print("Devices listed: %d / %d (truncated=%s)" % (len(devices), len(listing), truncated))
    print("SCRIPT_SUCCESS: list_device_repository complete.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error listing device repository: %s\n%s" % (e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
