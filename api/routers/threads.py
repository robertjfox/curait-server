from fastapi import APIRouter, HTTPException
import logging

from models import ThreadCreateRequest, ThreadChatRequest
from services.thread_service import get_thread_service
from services.outfit_generation_service import get_outfit_generation_service
from services.prompt_suggestions_service import get_prompt_suggestions_service
from interfaces import db, aexec
from utils.background_tasks import spawn

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/threads", tags=["threads"])


@router.post("/create", response_model=dict)
async def create_thread(request: ThreadCreateRequest):
	"""Create a new conversation thread for a user."""
	try:
		thread_id = await aexec(db.threads.create, user_id=request.user_id)
		if not thread_id:
			raise HTTPException(status_code=500, detail="Failed to create thread")

		logger.info(f"🧵 Created thread {thread_id[:6]}")

		# Fire-and-forget: refresh prompt suggestions for the user.
		try:
			spawn(
				get_prompt_suggestions_service().generate_and_save(
					request.user_id,
					ignore_throttle=True,
				),
				name=f"prompt-suggestions:{request.user_id[:6]}",
			)
		except Exception:
			pass

		return {"success": True, "thread_id": thread_id}

	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"❌ Error creating thread: {e}")
		raise HTTPException(status_code=500, detail=f"Thread creation failed: {e}")


@router.post("/{thread_id}/chat", response_model=dict)
async def chat_in_thread(thread_id: str, request: ThreadChatRequest):
	"""Append a message to a thread and trigger outfit generation."""
	try:
		await get_thread_service().route_user_message(
			thread_id=thread_id,
			user_message=request.message,
		)
		return {"success": True, "thread_id": thread_id}

	except Exception as e:
		logger.error(f"❌ Error in thread chat: {e}")
		raise HTTPException(status_code=500, detail=f"Chat failed: {e}")


@router.get("/by-user/{user_id}", response_model=dict)
async def list_threads_for_user(user_id: str):
	"""Return thread summaries (id, title, timestamps) for a user."""
	try:
		threads = await aexec(db.threads.list_summaries_by_user, user_id)
		return {"success": True, "threads": threads}
	except Exception as e:
		logger.error(f"❌ Error listing threads: {e}")
		raise HTTPException(status_code=500, detail=f"List threads failed: {e}")


@router.get("/{thread_id}", response_model=dict)
async def get_thread(thread_id: str):
	"""Return a single thread including its comments."""
	try:
		thread = await aexec(db.threads.get, thread_id)
		if not thread:
			raise HTTPException(status_code=404, detail="Thread not found")
		return {"success": True, "thread": thread}
	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"❌ Error getting thread: {e}")
		raise HTTPException(status_code=500, detail=f"Get thread failed: {e}")


@router.get("/{thread_id}/outfits", response_model=dict)
async def list_outfits_for_thread(thread_id: str):
	"""Return all outfits (with items) for a thread, ordered for display."""
	try:
		outfits = await aexec(db.outfits.list_for_thread_with_items, thread_id)
		return {"success": True, "outfits": outfits}
	except Exception as e:
		logger.error(f"❌ Error listing outfits: {e}")
		raise HTTPException(status_code=500, detail=f"List outfits failed: {e}")


@router.post("/{thread_id}/outfits/next", response_model=dict)
async def reveal_next_outfit_for_thread(thread_id: str):
	"""Reveal the next cached outfit and refill the hidden deck."""
	try:
		result = await get_outfit_generation_service().reveal_next_cached_outfit(
			thread_id=thread_id,
		)
		if not result.get("success", False):
			message = result.get("message") or "Could not reveal next outfit"
			if message == "Thread not found":
				raise HTTPException(status_code=404, detail=message)
			raise HTTPException(status_code=400, detail=message)
		return result
	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"❌ Error revealing next outfit: {e}")
		raise HTTPException(status_code=500, detail=f"Reveal next outfit failed: {e}")


@router.delete("/{thread_id}", response_model=dict)
async def delete_thread(thread_id: str):
	"""Delete a thread and all its outfits/items."""
	try:
		ok = await aexec(db.threads.delete, thread_id)
		if not ok:
			raise HTTPException(status_code=500, detail="Delete failed")
		return {"success": True, "thread_id": thread_id}
	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"❌ Error deleting thread: {e}")
		raise HTTPException(status_code=500, detail=f"Delete thread failed: {e}")
