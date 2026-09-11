"""
Persistent watcher script for CODESYS IPC.
Runs inside CODESYS via --runscript, starts a background polling thread,
then RETURNS so the CODESYS UI stays interactive.

Commands are marshaled to the primary thread via execute_on_primary_thread.

{IPC_BASE_DIR} is interpolated by Node.js before launch.
"""
import sys
import os
import time
import traceback
import json

# --- Configuration ---
IPC_BASE_DIR = "{IPC_BASE_DIR}"
COMMANDS_DIR = os.path.join(IPC_BASE_DIR, "commands")
RESULTS_DIR = os.path.join(IPC_BASE_DIR, "results")
POLL_INTERVAL = 50  # milliseconds
WATCHER_VERSION = "0.3.0"

# --- Error capture file (written before anything else can fail) ---
_ERROR_FILE = os.path.join(IPC_BASE_DIR, "watcher_error.txt")

def _write_error(msg):
    try:
        with open(_ERROR_FILE, "a") as f:
            f.write("[%f] %s\n" % (time.time(), msg))
    except:
        pass

try:
    # --- Ensure directories exist ---
    if not os.path.exists(COMMANDS_DIR):
        os.makedirs(COMMANDS_DIR)
    if not os.path.exists(RESULTS_DIR):
        os.makedirs(RESULTS_DIR)

    # --- Atomic file write helper ---
    # Atomic via .NET System.IO.File.Replace on Windows NTFS (no os.remove +
    # os.rename window where readers see no file at all). Plain rename when
    # the destination doesn't yet exist. Falls back to retry-based remove +
    # rename only if the .NET interop is unavailable for some reason.
    def atomic_write(file_path, content):
        tmp_path = file_path + ".tmp"
        # Accept either bytes or unicode; serialize unicode as utf-8 bytes so
        # control-plane data with non-ASCII (e.g. project paths in error
        # strings) survives without a codec mismatch.
        if isinstance(content, unicode):
            content = content.encode('utf-8')
        with open(tmp_path, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        try:
            from System.IO import File as _NetFile
            if os.path.exists(file_path):
                _NetFile.Replace(tmp_path, file_path, None)
            else:
                _NetFile.Move(tmp_path, file_path)
        except Exception:
            # Fallback: retry-based remove + rename. Antivirus / Defender
            # scanning the .tmp file can hold a transient lock that os.remove
            # surfaces as WinError 32 (sharing violation); a short retry
            # usually clears it.
            for attempt in range(5):
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    os.rename(tmp_path, file_path)
                    return
                except OSError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05 * (attempt + 1))

    # --- Write ready signal EARLY (before .NET imports) ---
    ready_path = os.path.join(IPC_BASE_DIR, "ready.signal")
    # Record the launching profile so the Node launcher can adopt this exact
    # session on an MCP-server restart (single-instance reuse, no second window).
    _launch_profile = os.environ.get("INOPROSHOP_MCP_PROFILE", "")
    info = {
        "version": WATCHER_VERSION,
        "python_version": sys.version,
        "profile": _launch_profile,
        "platform": sys.platform,
        "ipc_dir": IPC_BASE_DIR,
        "timestamp": time.time(),
        "pid": os.getpid(),
    }
    atomic_write(ready_path, json.dumps(info, indent=2))
    print("[WATCHER] Ready signal written to %s" % ready_path)

    # --- Import .NET threading (after ready signal) ---
    _write_error("About to import clr")
    import clr
    _write_error("clr imported OK")
    from System.Threading import Thread, ThreadStart, ManualResetEvent
    _write_error("System.Threading imported OK")
    import scriptengine as se
    _write_error("scriptengine imported OK")

    # --- File-based logging (print from bg thread crashes CODESYS) ---
    _LOG_FILE = os.path.join(IPC_BASE_DIR, "watcher.log")

    def _log(msg):
        try:
            with open(_LOG_FILE, "a") as f:
                f.write("[%f] %s\n" % (time.time(), msg))
        except:
            pass

    # --- Output Capture ---
    class OutputCapture:
        def __init__(self):
            self._buffer = []
        def write(self, s):
            # IronPython 2.7 str(u'CJK') uses ascii and raises; keep unicode.
            if s is None:
                return
            if isinstance(s, unicode):
                self._buffer.append(s)
            else:
                try:
                    self._buffer.append(s.decode('utf-8'))
                except Exception:
                    try:
                        self._buffer.append(s.decode('gbk'))
                    except Exception:
                        self._buffer.append(unicode(repr(s), 'utf-8', 'replace'))
        def writelines(self, lines):
            for l in lines:
                self.write(l)
        def flush(self):
            pass
        def getvalue(self):
            if not self._buffer:
                return u""
            try:
                return u"".join(self._buffer)
            except Exception:
                parts = []
                for x in self._buffer:
                    if isinstance(x, unicode):
                        parts.append(x)
                    else:
                        parts.append(unicode(repr(x), 'utf-8', 'replace'))
                return u"".join(parts)

    # --- Stop event ---
    _stop_event = ManualResetEvent(False)

    def _do_exec(code, globs):
        # Top-level helper so IronPython 2.7 doesn't reject this as an
        # "unqualified exec in a nested function" - the rule fires when
        # exec sits inside a nested def, but not inside a module-level def.
        # NOTE: keep this file ASCII-only. IronPython 2.7 rejects non-ASCII
        # source without a "# -*- coding: utf-8 -*-" header.
        exec(code, globs)

    def process_command(command_file):
        """Process a single command. File I/O on bg thread, exec on primary thread."""
        command_path = os.path.join(COMMANDS_DIR, command_file)
        request_id = command_file.replace(".command.json", "")
        result_path = os.path.join(RESULTS_DIR, "%s.result.json" % request_id)

        _log("Processing command: %s" % request_id)

        # Read command and script as UTF-8 bytes. IronPython open(..., "r")
        # uses the ANSI codepage (GBK here) and mojibakes Chinese paths.
        try:
            with open(command_path, "rb") as f:
                raw_cmd = f.read()
            if isinstance(raw_cmd, str):
                try:
                    raw_cmd = raw_cmd.decode('utf-8')
                except UnicodeDecodeError:
                    raw_cmd = raw_cmd.decode('gbk')
            command_data = json.loads(raw_cmd)
            script_path = command_data.get("scriptPath", "")
            if not os.path.exists(script_path):
                raise IOError("Script file not found: %s" % script_path)
            with open(script_path, "rb") as f:
                script_code = f.read()
            if isinstance(script_code, str):
                try:
                    script_code = script_code.decode('utf-8')
                except UnicodeDecodeError:
                    script_code = script_code.decode('gbk')
            # IronPython exec() rejects raw \r in unicode source tokens.
            if isinstance(script_code, unicode):
                script_code = script_code.replace(u'\r\n', u'\n').replace(u'\r', u'\n')
        except Exception as read_err:
            _log("Error reading command: %s" % read_err)
            atomic_write(result_path, json.dumps({
                "requestId": request_id,
                "success": False,
                "output": "",
                "error": "Read error: %s" % read_err,
                "timestamp": time.time(),
            }))
            return

        # Cross-thread communication
        shared_result = [None]
        done_event = ManualResetEvent(False)

        def execute_on_ui():
            success = False
            output = ""
            error = ""
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            capture = OutputCapture()
            sys.stdout = capture
            sys.stderr = capture
            try:
                exec_globals = {
                    '__builtins__': __builtins__,
                    'sys': sys,
                    'os': os,
                    'time': time,
                    'traceback': traceback,
                    'shutil': __import__('shutil'),
                }
                _do_exec(script_code, exec_globals)
                output = capture.getvalue()
                if "SCRIPT_ERROR" in output:
                    success = False
                    error = "Script reported error via SCRIPT_ERROR marker"
                elif "SCRIPT_SUCCESS" in output:
                    success = True
                else:
                    success = True
            except SystemExit as e:
                output = capture.getvalue()
                exit_code = e.code
                if exit_code is None or exit_code == 0:
                    success = True
                    if "SCRIPT_ERROR" in output:
                        success = False
                        error = "Script reported error via SCRIPT_ERROR marker"
                elif isinstance(exit_code, int):
                    if "SCRIPT_SUCCESS" in output and "SCRIPT_ERROR" not in output:
                        success = True
                    else:
                        success = False
                        error = "Script exited with code %s" % exit_code
                elif isinstance(exit_code, str):
                    success = False
                    error = exit_code
            except Exception as e:
                output = capture.getvalue()
                error = "%s: %s\n%s" % (type(e).__name__, str(e), traceback.format_exc())
                success = False
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

            shared_result[0] = {
                "requestId": request_id,
                "success": success,
                "output": output,
                "error": error,
                "timestamp": time.time(),
            }
            done_event.Set()

        # Marshal execution to the primary thread
        _log("Marshaling to primary thread...")
        try:
            se.system.execute_on_primary_thread(execute_on_ui)
        except Exception as marshal_err:
            _log("Marshal error: %s" % marshal_err)
            shared_result[0] = {
                "requestId": request_id,
                "success": False,
                "output": "",
                "error": "Marshal error: %s" % marshal_err,
                "timestamp": time.time(),
            }
            done_event.Set()

        # Wait for completion (2 min default timeout for primary-thread exec)
        done_event.WaitOne(120000)

        # Write result (file I/O - safe from bg thread)
        if shared_result[0]:
            # ensure_ascii=False + unicode values: IronPython json.dumps(ensure_ascii=True)
            # is broken for non-ASCII (py_encode_basestring_ascii decodes as utf-8).
            try:
                payload = shared_result[0]
                for k in ("output", "error", "requestId"):
                    if k in payload and payload[k] is not None and not isinstance(payload[k], unicode):
                        try:
                            payload[k] = payload[k].decode('utf-8')
                        except Exception:
                            payload[k] = unicode(repr(payload[k]), 'utf-8', 'replace')
                atomic_write(result_path, json.dumps(payload, ensure_ascii=False))
            except Exception as dumps_err:
                _log("Result dumps error: %s" % dumps_err)
                atomic_write(result_path, json.dumps({
                    "requestId": request_id,
                    "success": bool(shared_result[0].get("success")),
                    "output": "",
                    "error": "Result serialize error: %s" % dumps_err,
                    "timestamp": time.time(),
                }, ensure_ascii=True))
            _log("Result written: success=%s" % shared_result[0].get("success"))
        else:
            _log("ERROR: No result after timeout")
            atomic_write(result_path, json.dumps({
                "requestId": request_id,
                "success": False,
                "output": "",
                "error": "Timeout waiting for primary thread execution",
                "timestamp": time.time(),
            }))

        # Cleanup command and script files
        try:
            if os.path.exists(command_path):
                os.remove(command_path)
            sp = os.path.join(COMMANDS_DIR, "%s.py" % request_id)
            if os.path.exists(sp):
                os.remove(sp)
        except:
            pass


    def worker():
        _log("Background worker started")
        while not _stop_event.WaitOne(POLL_INTERVAL):
            try:
                if os.path.exists(os.path.join(IPC_BASE_DIR, "terminate.signal")):
                    _log("Terminate signal received")
                    break
                cmd_files = sorted([
                    f for f in os.listdir(COMMANDS_DIR)
                    if f.endswith(".command.json")
                ])
                if cmd_files:
                    process_command(cmd_files[0])
            except Exception as e:
                _log("Worker error: %s" % e)
        _log("Background worker stopped")


    # --- Start background worker thread and RETURN ---
    print("[WATCHER] Starting background watcher v%s" % WATCHER_VERSION)
    print("[WATCHER] IPC directory: %s" % IPC_BASE_DIR)
    print("[WATCHER] Python version: %s" % sys.version)

    t = Thread(ThreadStart(worker))
    t.IsBackground = True
    t.Start()

    import System
    System.GC.KeepAlive(t)

    print("[WATCHER] Background thread started, script returning - UI is free")

except Exception as _fatal:
    _write_error("FATAL: %s\n%s" % (_fatal, traceback.format_exc()))
    print("[WATCHER] FATAL ERROR: %s" % _fatal)
    traceback.print_exc()
# Script returns here. CODESYS UI thread is freed.
