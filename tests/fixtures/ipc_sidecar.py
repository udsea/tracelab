"""Deterministic local echo server for the production Rust IPC tests; no TraceLab imports."""

import json
import os
import sys
import threading
import time

output_lock = threading.Lock()


def respond(request):
    method = request["method"]
    if method == "crash":
        os._exit(7)
    if method == "sleep":
        time.sleep(request["params"]["seconds"])
    with output_lock:
        if method == "malformed":
            print("not json", flush=True)
        print(
            json.dumps(
                {
                    "id": request["id"],
                    "result": {
                        "id": request["id"],
                        "pid": os.getpid(),
                        "method": method,
                        "params": request["params"],
                    },
                }
            ),
            flush=True,
        )


for line in sys.stdin:
    threading.Thread(target=respond, args=(json.loads(line),), daemon=True).start()
