"""Shared transient-error helpers for the interface layer.

The Supabase Python SDK keeps HTTP connections alive between requests.
When the edge closes one server-side (idle timeouts, NAT drops, etc.)
the next reuse fails with errors like:

    Server disconnected without sending a response.

The error is fully recoverable — a fresh socket succeeds. This module
centralises detection, exponential backoff, and *connection-pool
eviction* between attempts so a retry doesn't immediately pick up
another dead socket from the same pool (which is what causes the
"retrying 2/2 → Failed" pattern in the logs).
"""
from __future__ import annotations
import logging
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


_TRANSIENT_ERROR_MARKERS = (
	"server disconnected",
	"connection aborted",
	"remote end closed connection",
	"connection reset",
	"econnreset",
	"client has been closed",
	"cannot send a request",
)


def is_transient_supabase_error(exc: BaseException) -> bool:
	message = (str(exc) or "").lower()
	return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)


def _reset_supabase_pool() -> None:
	"""Replace the Supabase SDK client so the next request uses fresh sessions.

	Walks several possible attribute paths because supabase-py's internal
	layout has shifted across versions; silently no-ops if none match.
	"""
	try:
		from clients.supabase_client import get_supabase_client, reset_supabase_client
		reset_supabase_client()
		client = get_supabase_client()
	except Exception:
		return

	try:
		from interfaces import db
		for interface in (
			db.outfits,
			db.outfit_items,
			db.threads,
			db.users,
			db.saved_products,
			getattr(db.outfits, "outfit_items_interface", None),
		):
			if interface is not None and hasattr(interface, "_supabase"):
				setattr(interface, "_supabase", client)
	except Exception:
		pass


def with_retry(
	fn: Callable[..., T],
	*args: Any,
	attempts: int = 3,
	delay: float = 0.1,
	backoff: float = 3.0,
	**kwargs: Any,
) -> T:
	"""Run ``fn`` and retry on transient Supabase / httpx errors.

	Uses exponential backoff (default 0.1s → 0.3s → 0.9s …) and resets
	the SDK connection pool between attempts. Defaults to 3 total
	attempts (2 retries). Non-transient errors are re-raised immediately.
	"""
	last_exc: BaseException | None = None
	current_delay = delay
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
				"Supabase transient error (%s: %s) — retrying %d/%d in %.2fs",
				type(exc).__name__,
				exc,
				attempt + 1,
				attempts,
				current_delay,
			)
			_reset_supabase_pool()
			time.sleep(current_delay)
			current_delay *= backoff
	assert last_exc is not None
	raise last_exc
