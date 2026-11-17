"""Isolated macOS pilot executor; never executes model code in the host process."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import sys


def execute(script: str, timeout: float = 5, *, runtime: bool = False) -> dict:
    with tempfile.TemporaryDirectory(prefix="meta_n_") as directory:
        root = Path(directory).resolve()
        source = root / "solution.py"
        source.write_text(script)
        # Deny user files, other temporary workspaces, network and external writes.
        allowed = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()]
        if runtime:
            import meta_n
            allowed.append(Path(meta_n.__file__).resolve().parent)
        exceptions = " ".join('(require-not (subpath "%s"))' % p for p in allowed) if runtime else ""
        profile = '''(version 1)(allow default)
(deny network*)
(deny file-read-data (require-all (subpath "/Users") %s) (subpath "/Volumes")
 (require-all (subpath "/private/var/folders") (require-not (subpath "%s")) %s))
(deny file-write* (require-all (require-not (subpath "%s"))
 (require-not (literal "/dev/null"))))
''' % (exceptions, root, exceptions, root)
        # Return value wins; stdout is a fallback only for solve() returning None.
        wrapper = '''import contextlib, io, json, resource
resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
ns = {}
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    exec(compile(open("solution.py").read(), "solution.py", "exec"), ns)
    value = ns["solve"]()
answer = str(value) if value is not None else buf.getvalue().strip()
print(json.dumps({"answer": answer, "stdout": buf.getvalue()}))
'''
        out = root / "stdout"
        err = root / "stderr"
        with out.open("w+") as stdout, err.open("w+") as stderr:
            proc = subprocess.Popen(
                ["/usr/bin/sandbox-exec", "-p", profile, sys.executable if runtime else "/Library/Developer/CommandLineTools/usr/bin/python3", "-I", "-c", wrapper],
                cwd=root, env={"PATH": "/usr/bin:/bin", "TMPDIR": str(root)},
                stdout=stdout, stderr=stderr, start_new_session=True,
            )
            timed_out = False
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    if proc.poll() is None:
                        proc.kill()
                proc.wait()
            stdout.seek(0)
            stderr.seek(0)
            raw = stdout.read(65536)
            error = stderr.read(65536)
        result = {"answer": "", "stdout": raw, "stderr": error,
                  "exit_code": proc.returncode, "timed_out": timed_out}
        if not timed_out and proc.returncode == 0:
            try:
                result.update(json.loads(raw))
            except (ValueError, TypeError):
                result["stderr"] += "\nInvalid executor output"
                result["exit_code"] = -1
        return result
