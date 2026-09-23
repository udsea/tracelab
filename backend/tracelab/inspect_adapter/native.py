import asyncio
import socket
import sys


async def open_native(service, experiment, sample_id):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    args = service.adapter.open_native_view(experiment) + ["--port", str(port)]
    command = (
        [sys.executable, "--inspect-view"]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-m", "inspect_ai"]
    )
    process = await asyncio.create_subprocess_exec(
        *command,
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    service.native_processes.append(process)
    for _ in range(40):
        if process.returncode is not None:
            raise RuntimeError(
                "Inspect viewer exited before opening. Check the installed Inspect CLI."
            )
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return {
                "url": f"http://127.0.0.1:{port}",
                "sampleId": sample_id,
                "note": f"Opened the containing log directory. Select sample {sample_id}.",
            }
        except OSError:
            await asyncio.sleep(0.1)
    raise RuntimeError("Inspect viewer did not become ready")
