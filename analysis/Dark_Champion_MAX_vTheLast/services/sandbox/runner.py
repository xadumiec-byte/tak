"""Runs ONLY in a disposable networkless container; never on the Colab host."""
import json
import os
import selectors
import signal
import subprocess
import sys
import time

LIMIT = 40000

def execute(code, timeout):
    process = subprocess.Popen([sys.executable, "-I", "-u", "-c", code],
        cwd="/tmp", stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True, env={"PATH": "/usr/local/bin:/usr/bin:/bin"})
    output = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + timeout
    status = None
    try:
        while selector.get_map():
            if time.monotonic() >= deadline:
                status = 124
                break
            for key, _ in selector.select(min(.1, max(0, deadline - time.monotonic()))):
                data = os.read(key.fd, 4096)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                remaining = LIMIT - sum(len(v) for v in output.values())
                output[key.data].extend(data[:remaining])
                if len(data) > remaining:
                    status = 125
                    break
            if status is not None:
                break
        if status is None:
            try:
                status = process.wait(timeout=max(.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                status = 124
    finally:
        # Also kill surviving descendants after the parent exits normally.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        selector.close()
        process.stdout.close()
        process.stderr.close()
    return {"exit_code": status, **{k: bytes(v).decode("utf-8", "replace") for k, v in output.items()},
            "output_limited": status == 125, "timed_out": status == 124}

if __name__ == "__main__":
    request = json.loads(sys.argv[1])
    print(json.dumps(execute(request["code"], request["timeout"])))
