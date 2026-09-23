import argparse
import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path

from platformdirs import user_data_dir


async def serve(data_dir):
    os.environ["INSPECT_DISPLAY"] = "none"
    # Stdout is exclusively the IPC channel. Inspect and dependencies may print progress.
    channel = sys.stdout
    sys.stdout = sys.stderr
    from tracelab.api.service import Service

    service = Service(data_dir)
    tasks = set()
    lock = asyncio.Lock()

    async def respond(line):
        id = None
        try:
            request = json.loads(line)
            id = request["id"]
            result = await service.dispatch(request["method"], request.get("params") or {})
            response = {"id": id, "result": result}
        except Exception as exc:
            response = {"id": id, "error": {"message": str(exc), "type": type(exc).__name__}}
        async with lock:
            channel.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n")
            channel.flush()

    try:
        while line := await asyncio.to_thread(sys.stdin.readline):
            task = asyncio.create_task(respond(line))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)
        await service.close()


def main():
    if "--inspect-view" in sys.argv:
        # Bundled runtime re-enters Inspect's public CLI without requiring a system Python.
        import runpy

        sys.argv.remove("--inspect-view")
        runpy.run_module("inspect_ai", run_name="__main__")
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument(
        "--data-dir", default=os.getenv("TRACELAB_DATA_DIR", user_data_dir("TraceLab"))
    )
    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(Path(args.data_dir)))


if __name__ == "__main__":
    main()
