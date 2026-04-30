import logging
from typing import Optional, Dict, Any

from clients.supabase_client import get_supabase_client
from clients.gemini_client import get_gemini_client
from interfaces import db
from interfaces._retry import with_retry
from utils.image_processing.image_gen import detect_image_mime_and_ext


logger = logging.getLogger(__name__)


class AvatarService:
	"""Create and persist a standardized full-body user avatar from a selfie.

	Avatar generation runs from the synchronous ``/api/avatars/.../generate``
	endpoint, which FastAPI dispatches into a worker thread. So all of
	this service's calls are intentionally sync; they just must not be
	called from the asyncio event loop directly.
	"""

	SELFIE_BUCKET = "user-selfies"
	AVATAR_BUCKET = "user-avatars"

	def __init__(self) -> None:
		self.gemini = get_gemini_client()

	def _download_selfie_bytes(self, user_id: str) -> bytes:
		logger.info(f"[AVATAR] Looking for selfie in '{self.SELFIE_BUCKET}' for user_id={user_id}")
		exts = [".png", ".jpg", ".jpeg", ".webp"]
		last_error: Optional[Exception] = None
		for ext in exts:
			path = f"{user_id}{ext}"
			try:
				logger.debug(f"[AVATAR] Trying selfie path: {path}")
				def _download() -> bytes:
					return get_supabase_client().storage.from_(self.SELFIE_BUCKET).download(path)
				data = with_retry(_download)
				if data:
					logger.info(f"[AVATAR] Found selfie: {path} bytes={len(data)}")
					return data
			except Exception as e:
				last_error = e
				logger.debug(f"[AVATAR] No selfie at {path}: {e}")
		try:
			fallback = "user_face.png"
			logger.debug(f"[AVATAR] Trying fallback selfie: {fallback}")
			def _download_fallback() -> bytes:
				return get_supabase_client().storage.from_(self.SELFIE_BUCKET).download(fallback)
			data = with_retry(_download_fallback)
			if data:
				logger.info(f"[AVATAR] Using fallback selfie: {fallback} bytes={len(data)}")
				return data
		except Exception:
			pass
		raise FileNotFoundError(f"No selfie found for user {user_id}. Last error: {last_error}")

	def _get_user_metrics(
		self,
		user_id: str,
	) -> tuple[Optional[float], Optional[float], Optional[str]]:
		"""Fetch height_cm, weight_kg, gender either from top-level fields or context JSON."""
		logger.info(f"[AVATAR] Fetching user metrics for user_id={user_id}")
		user = db.users.get(user_id)
		if not user:
			return None, None, None
		height_cm = user.get("height_cm")
		weight_kg = user.get("weight_kg")
		gender = (user.get("gender") or "") or None
		raw_context: Dict[str, Any] = user.get("onboarding_raw_context") or {}
		if height_cm is None or weight_kg is None:
			ctx: Dict[str, Any] = user.get("context") or {}
			height_cm = height_cm if height_cm is not None else raw_context.get("height_cm") or ctx.get("height_cm")
			weight_kg = weight_kg if weight_kg is not None else raw_context.get("weight_kg") or ctx.get("weight_kg")
			gender = gender or ctx.get("gender")
		gender = gender or raw_context.get("gender")
		try:
			height_cm = float(height_cm) if height_cm is not None else None
		except Exception:
			height_cm = None
		try:
			weight_kg = float(weight_kg) if weight_kg is not None else None
		except Exception:
			weight_kg = None
		if isinstance(gender, str):
			gender = gender.strip().lower() or None
		else:
			gender = None
		logger.info(f"[AVATAR] Metrics height_cm={height_cm} weight_kg={weight_kg} gender={gender}")
		return height_cm, weight_kg, gender

	def _upload_avatar(self, *, user_id: str, image_bytes: bytes) -> str:
		mime_type, ext = detect_image_mime_and_ext(image_bytes)
		filename = f"{user_id}{ext}"
		file_options = {"content-type": mime_type, "upsert": "true"}

		def _upload() -> str:
			storage = get_supabase_client().storage.from_(self.AVATAR_BUCKET)
			storage.upload(filename, image_bytes, file_options)
			return storage.get_public_url(filename)

		try:
			return with_retry(_upload)
		except Exception as e:
			logger.error(f"Failed to upload avatar for {user_id}: {e}")
			raise

	def get_current_avatar_url(self, user_id: str) -> Optional[str]:
		try:
			def _list_avatars():
				return get_supabase_client().storage.from_(self.AVATAR_BUCKET).list()
			for item in with_retry(_list_avatars):
				name = item.get("name") if isinstance(item, dict) else None
				if isinstance(name, str) and name.startswith(f"{user_id}."):
					storage = get_supabase_client().storage.from_(self.AVATAR_BUCKET)
					return storage.get_public_url(name)
		except Exception as e:
			logger.warning(f"[AVATAR] Failed to list avatar for user_id={user_id}: {e}")
		return None

	def generate_and_store_avatar(
		self,
		*,
		user_id: str,
		selfie_bytes: Optional[bytes] = None,
	) -> Dict[str, str]:
		"""End-to-end: selfie -> Gemini -> avatar upload. Returns public URL."""
		logger.info(f"[AVATAR] ▶︎ Starting avatar generation for user_id={user_id}")
		if selfie_bytes is None:
			selfie_bytes = self._download_selfie_bytes(user_id)
		height_cm, weight_kg, gender = self._get_user_metrics(user_id)

		logger.info("[AVATAR] Calling Gemini for full-body avatar…")
		image_bytes = self.gemini.generate_fullbody_avatar(
			selfie_bytes=selfie_bytes,
			height_cm=height_cm,
			weight_kg=weight_kg,
			gender=gender,
		)
		if not image_bytes:
			raise RuntimeError("Gemini did not return an image for avatar generation")

		logger.info("[AVATAR] Uploading avatar to Supabase storage…")
		url = self._upload_avatar(user_id=user_id, image_bytes=image_bytes)
		logger.info(f"[AVATAR] ✔︎ Avatar stored user_id={user_id} url={url}")
		return {"image_url": url}


_service: Optional[AvatarService] = None


def get_avatar_service() -> AvatarService:
	global _service
	if _service is None:
		_service = AvatarService()
	return _service
