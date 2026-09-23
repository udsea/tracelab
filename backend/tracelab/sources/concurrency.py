import asyncio


async def blocking(function, *args, on_cancel=None):
    """Join worker threads before closing their generators, files, or cache connection."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        if on_cancel:
            on_cancel()
        try:
            await task
        except Exception:
            pass
        raise
