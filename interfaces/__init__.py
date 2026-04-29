"""Interfaces layer: database/storage persistence boundaries.

The Supabase Python SDK is synchronous. Calling it from an async context
freezes the event loop, which under any non-trivial load (frontend polling
+ multiple in-flight outfit generations) starves health checks, queues
incoming TCP connections, and looks like the local network has crashed.

Async paths must run Supabase work through :func:`aexec`, which dispatches
the synchronous call to a worker thread so the event loop stays
responsive. Sync FastAPI routes already run in the threadpool and may
call the interfaces directly.
"""
import asyncio
from typing import Callable, TypeVar

from interfaces._retry import with_retry, is_transient_supabase_error
from interfaces.outfits_interface import OutfitsInterface
from interfaces.outfit_items_interface import OutfitItemsInterface
from interfaces.threads_interface import ThreadsInterface
from interfaces.users_interface import UsersInterface
from interfaces.saved_products_interface import SavedProductsInterface
from interfaces import db

T = TypeVar("T")


async def aexec(fn: Callable[..., T], *args, **kwargs) -> T:
	"""Run a sync DB / Supabase call in a worker thread.

	Use everywhere the caller is `async def` and the callee is sync.
	"""
	return await asyncio.to_thread(fn, *args, **kwargs)


__all__ = [
	"aexec",
	"db",
	"with_retry",
	"is_transient_supabase_error",
	"OutfitsInterface",
	"OutfitItemsInterface",
	"ThreadsInterface",
	"UsersInterface",
	"SavedProductsInterface",
]
