"""Shared transient-error helpers for the interface layer.

The Supabase Python SDK keeps HTTP connections alive between requests.
When the edge closes one server-side (idle timeouts, NAT drops, etc.)
the next reuse fails with errors like:

    Server disconnected without sending a response.

The error is fully recoverable — a second attempt opens a fresh socket.
This module centralises detection of that class of error so any
interface method can retry once before giving up.
"""
from __future__ import annotations
import logging
import time
from typing import Callable, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


_TRANSIENT_ERROR_MARKERS = (
	"server disconnected",
	"connection aborted",
	"remote end closed connection",
	"connection reset",
	"econnreset",
)


def is_transient_supabase_error(exc: BaseException) -> bool:
	message = (str(exc) or "").lower()
	return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)


def with_retry(fn: Callable[..., T], *args, attempts: int = 2, delay: float = 0.1, **kwargs) -> T:
	"""Run ``fn`` and retry on transient Supabase / httpx errors.

	Non-transient errors are re-raised immediately. Defaults to 2 total
	attempts (1 retry).
	"""
	last_exc: BaseException | None = None
	for attempt in range(1, attempts + 1):
		try:
			return fn(*args, **kwargs)
		except Exception as exc:
			if not is_transient_supabase_error(exc):
				raise
			last_exc = exc
			if attempt >= attempts:
				break
			logger.warning(
				"Supabase transient error (%s: %s) — retrying %d/%d",
				type(exc).__name__,
				exc,
				attempt + 1,
				attempts,
			)
			time.sleep(delay)
	assert last_exc is not None
	raise last_exc
