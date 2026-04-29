import asyncio
import logging
from typing import Awaitable, Set

logger = logging.getLogger(__name__)

_tasks: Set[asyncio.Task] = set()


def spawn(coro: Awaitable, *, name: str) -> asyncio.Task:
    """Track fire-and-forget work so shutdown can cancel it cleanly."""
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)

    def _done(completed: asyncio.Task) -> None:
        _tasks.discard(completed)
        if completed.cancelled():
            logger.info("Cancelled background task: %s", completed.get_name())
            return
        try:
            exc = completed.exception()
        except asyncio.CancelledError:
            return
        if exc:
            logger.error(
                "Background task failed (%s): %s",
                completed.get_name(),
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    task.add_done_callback(_done)
    return task


async def shutdown_background_tasks(timeout: float = 5.0) -> None:
    """Cancel tracked background tasks during server shutdown."""
    if not _tasks:
        return

    pending = list(_tasks)
    logger.info("Cancelling %d background task(s)", len(pending))
    for task in pending:
        task.cancel()

    done, still_pending = await asyncio.wait(pending, timeout=timeout)
    for task in done:
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Background task errored during shutdown: %s", exc)

    if still_pending:
        logger.warning(
            "%d background task(s) did not stop within %.1fs",
            len(still_pending),
            timeout,
        )
