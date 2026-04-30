from fastapi import APIRouter, HTTPException, UploadFile, File
import logging

from services.avatar_service import get_avatar_service
from models.avatars import AvatarResponse, CurrentAvatarResponse
from clients.supabase_client import get_supabase_client
from interfaces._retry import with_retry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["avatars"])


@router.get("/avatars/{user_id}", response_model=CurrentAvatarResponse)
def get_current_avatar(user_id: str):
	avatar_service = get_avatar_service()
	image_url = avatar_service.get_current_avatar_url(user_id)
	return CurrentAvatarResponse(image_url=image_url)


@router.post("/avatars/{user_id}/generate", response_model=AvatarResponse)
def generate_avatar(user_id: str, selfie: UploadFile = File(...)):
	"""Sync route: FastAPI runs it in the threadpool, so blocking
	Supabase / Gemini calls do not stall the asyncio event loop."""
	avatar_service = get_avatar_service()
	try:
		logger.info(f"[AVATAR] ▶︎ Route called for user_id={user_id}")
		selfie_bytes = selfie.file.read()
		logger.info(
			f"[AVATAR] Received selfie upload filename={selfie.filename} "
			f"bytes={len(selfie_bytes)} content_type={selfie.content_type}"
		)

		# Store selfie in bucket first.
		filename = f"{user_id}.png"
		try:
			content_type = selfie.content_type or "application/octet-stream"
			def _upload_selfie() -> str:
				storage = get_supabase_client().storage.from_(avatar_service.SELFIE_BUCKET)
				storage.upload(filename, selfie_bytes, {"content-type": content_type, "upsert": "true"})
				return storage.get_public_url(filename)
			selfie_public_url = with_retry(_upload_selfie)
			logger.info(f"[AVATAR] Selfie stored at {selfie_public_url}")
		except Exception as e:
			logger.exception(f"[AVATAR] Failed to store selfie for user_id={user_id}")
			raise HTTPException(status_code=500, detail=f"Failed to store selfie: {e}")

		result = avatar_service.generate_and_store_avatar(user_id=user_id, selfie_bytes=selfie_bytes)
		image_url = result.get("image_url", "")
		logger.info(f"[AVATAR] ✔︎ Completed for user_id={user_id} url={image_url}")
		return AvatarResponse(image_url=image_url)
	except FileNotFoundError as e:
		logger.warning(f"[AVATAR] ✖︎ Selfie not found for user_id={user_id}: {e}")
		raise HTTPException(status_code=404, detail=str(e))
	except Exception as e:
		logger.exception(f"[AVATAR] ✖︎ Avatar generation failed for user_id={user_id}")
		raise HTTPException(status_code=500, detail=str(e))
