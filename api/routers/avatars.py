from fastapi import APIRouter, HTTPException, UploadFile, File
import logging

from services.avatar_service import AvatarService
from models.avatars import AvatarResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["avatars"])

avatar_service = AvatarService()

@router.post("/avatars/{user_id}/generate", response_model=AvatarResponse)
def generate_avatar(user_id: str, selfie: UploadFile = File(...)):
    try:
        logger.info(f"[AVATAR] ▶︎ Route called for user_id={user_id}")
        selfie_bytes = selfie.file.read()
        logger.info(f"[AVATAR] Received selfie upload filename={selfie.filename} bytes={len(selfie_bytes)} content_type={selfie.content_type}")

        # Store selfie in bucket first (server-managed storage)
        storage = avatar_service.supabase.storage.from_(avatar_service.SELFIE_BUCKET)
        # Use user_id for consistent storage naming
        filename = f"{user_id}.png"
        try:
            content_type = selfie.content_type or "application/octet-stream"
            storage.upload(filename, selfie_bytes, {"content-type": content_type, "upsert": "true"})
            selfie_public_url = storage.get_public_url(filename)
            logger.info(f"[AVATAR] Selfie stored at {selfie_public_url}")
        except Exception as e:
            logger.exception(f"[AVATAR] Failed to store selfie for user_id={user_id}")
            raise HTTPException(status_code=500, detail=f"Failed to store selfie: {e}")

        # Generate avatar using the same bytes we just stored
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


