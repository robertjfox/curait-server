import os
import logging
from collections import OrderedDict
from io import BytesIO
from typing import List, Optional, Dict, Any
import asyncio
import uuid

import _config as config
from clients.supabase_client import get_supabase_client
from interfaces import db, aexec
from utils.background_tasks import spawn
from utils.image_processing.image_gen import (
	prepare_pil_for_upload,
	detect_image_mime_and_ext,
	load_user_avatar_from_url,
)
from utils.image_processing.user_selfie_handler import get_user_avatar_urls
from ai.prompts.image_generation import (
	create_flatlay_prompt,
	create_virtual_tryon_prompt,
	create_fullbody_avatar_prompt,
)
import time

from PIL import Image

# Extra suppression in case this module is imported standalone (outside main)
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("GRPC_LOG_SEVERITY_LEVEL", "ERROR")
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("GLOG_logtostderr", "1")
try:
	import absl.logging as absl_logging  # type: ignore
	absl_logging.set_verbosity(absl_logging.ERROR)
	absl_logging.use_python_logging()
except Exception:
	pass
for name, level in (("google", logging.WARNING), ("google.genai", logging.ERROR), ("grpc", logging.ERROR)):
	try:
		lg = logging.getLogger(name)
		lg.setLevel(level)
		lg.propagate = False
	except Exception:
		pass

try:
	from google import genai
	from google.genai import types as genai_types
	GEMINI_AVAILABLE = True
except ImportError:
	GEMINI_AVAILABLE = False
	genai = None
	genai_types = None

logger = logging.getLogger(__name__)

_gemini_image_semaphore = asyncio.Semaphore(max(1, int(config.GEMINI_IMAGE_CONCURRENCY)))

_AVATAR_CACHE_MAX = 8


class GeminiClient:
	"""Wrapper around Google Gemini image generation."""

	MODEL = "gemini-2.5-flash-image"

	def __init__(self, *, api_key: Optional[str] = None):
		if not GEMINI_AVAILABLE:
			raise RuntimeError("Google Gemini SDK not available. Install with: pip install google-genai")
		self.client = genai.Client(
			api_key=(api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
		)
		# Bounded LRU cache so a long-running server doesn't accumulate
		# unbounded PIL images in memory across many users.
		self._avatar_cache: "OrderedDict[str, Image.Image]" = OrderedDict()

	def _cache_get_avatar(self, user_id: str) -> Optional[Image.Image]:
		img = self._avatar_cache.get(user_id)
		if img is not None:
			self._avatar_cache.move_to_end(user_id)
			return img.copy()
		return None

	def _cache_put_avatar(self, user_id: str, img: Image.Image) -> None:
		self._avatar_cache[user_id] = img
		self._avatar_cache.move_to_end(user_id)
		while len(self._avatar_cache) > _AVATAR_CACHE_MAX:
			self._avatar_cache.popitem(last=False)

	def _extract_image_bytes(self, response) -> Optional[bytes]:
		if not response.candidates:
			return None
		for part in response.candidates[0].content.parts:
			if hasattr(part, "inline_data") and part.inline_data:
				return part.inline_data.data
		return None

	def _generate_image(self, contents: List) -> Optional[bytes]:
		try:
			start_time = time.time()
			logger.info("[GEMINI] ▶︎ request started")
			response = self.client.models.generate_content(
				model=self.MODEL,
				contents=contents,
				config=genai_types.GenerateContentConfig(
					temperature=0.4,
					top_p=0.8,
					top_k=32,
					candidate_count=1,
					response_modalities=["IMAGE"],
					image_config=genai_types.ImageConfig(
						aspect_ratio="9:16",
						image_size="1K",
					),
				) if contents and len(contents) > 1 else None,
			)
			elapsed = time.time() - start_time
			logger.info(f"[GEMINI] ✔︎ generation time: {elapsed:.2f}s")
			return self._extract_image_bytes(response)
		except Exception as e:
			logger.error(f"[GEMINI] ❌ generation error: {e}")
			return None

	def _get_flatlay_avatar(self, user_id: str) -> Optional[Image.Image]:
		cached = self._cache_get_avatar(user_id)
		if cached is not None:
			return cached

		start_time = time.time()
		avatar = None
		for avatar_url in get_user_avatar_urls(user_id):
			avatar = load_user_avatar_from_url(avatar_url)
			if avatar is not None:
				logger.info(f"[GEMINI] using avatar base image: {avatar_url}")
				break
		if avatar is None:
			logger.info(f"[GEMINI] no stored avatar found for {user_id[:8]}; using text-only generation")
			return None

		prepared = prepare_pil_for_upload(avatar)
		self._cache_put_avatar(user_id, prepared.copy())
		logger.info(f"[GEMINI] avatar loaded in {time.time() - start_time:.2f}s")
		return prepared

	def generate_virtual_tryon(self, *, grid_bytes: bytes, user_id: str) -> Optional[bytes]:
		"""Generate virtual try-on using product grid. Requires a user avatar."""
		avatar = None
		for avatar_url in get_user_avatar_urls(user_id):
			avatar = load_user_avatar_from_url(avatar_url)
			if avatar is not None:
				break
		if avatar is None:
			logger.info(f"⏭️  Skipping VTON for {user_id[:8]}: no avatar uploaded")
			return None
		user_img = prepare_pil_for_upload(avatar)
		grid_img = prepare_pil_for_upload(Image.open(BytesIO(grid_bytes)))

		prompt = create_virtual_tryon_prompt()
		return self._generate_image([prompt, user_img, grid_img])

	def generate_fullbody_avatar(
		self,
		*,
		selfie_bytes: bytes,
		height_cm: float | None,
		weight_kg: float | None,
		gender: str | None = None,
	) -> Optional[bytes]:
		try:
			selfie_img = prepare_pil_for_upload(Image.open(BytesIO(selfie_bytes)))
		except Exception:
			logger.exception("Failed to load selfie bytes for avatar generation")
			raise

		prompt = create_fullbody_avatar_prompt(
			height_cm=height_cm,
			weight_kg=weight_kg,
			gender=gender,
		)
		return self._generate_image([prompt, selfie_img])

	async def generate_flatlay_and_upload(
		self,
		outfits: List[Dict[str, Any]],
		*,
		user_id: str,
		thread_id: Optional[str] = None,
	) -> List[Optional[str]]:
		"""Generate and upload one image per outfit."""
		async with _gemini_image_semaphore:
			avatar = await asyncio.to_thread(self._get_flatlay_avatar, user_id)
			urls: List[Optional[str]] = []

			supabase = get_supabase_client()
			bucket = getattr(config.model_config, "FLATLAY_RENDERING", {}).get(
				"bucket", "outfit-flatlay-images"
			)

			for outfit in outfits:
				def _generate_single() -> Optional[bytes]:
					prompt = create_flatlay_prompt([outfit])
					logger.info("Gemini prompt for 1 outfit")

					if avatar is None:
						return self._generate_image([prompt])

					try:
						return self._generate_image([prompt, avatar.copy()])
					except Exception:
						logger.exception("Single flatlay generation failed, falling back to text-only")
						return self._generate_image([prompt])

				image_bytes = await asyncio.to_thread(_generate_single)
				if not image_bytes:
					urls.append(None)
					continue

				mime_type, ext = detect_image_mime_and_ext(image_bytes)
				filename = f"outfit_tryon_{uuid.uuid4().hex}{ext}"

				def _upload(payload: bytes = image_bytes, name: str = filename, mt: str = mime_type) -> Optional[str]:
					storage = supabase.storage.from_(bucket)
					storage.upload(name, payload, {"content-type": mt})
					return storage.get_public_url(name)

				url: Optional[str] = None
				max_retries = 3
				for attempt in range(max_retries):
					try:
						url = await asyncio.to_thread(_upload)
						break
					except Exception as e:
						if attempt == max_retries - 1:
							logger.error(f"Failed to upload after {max_retries} attempts: {e}")
						else:
							logger.warning(f"Upload attempt {attempt + 1} failed, retrying: {e}")
							await asyncio.sleep(1)
				urls.append(url)

			return urls

	def launch_flatlay_task(
		self,
		*,
		outfits: List[Dict[str, Any]],
		thread_id: Optional[str] = None,
		outfit_ids: Optional[List[str]] = None,
		user_id: str,
	) -> asyncio.Task:
		"""Spawn flatlay generation task for multiple outfits."""

		async def _task() -> None:
			logger.debug(f"Generating Image for {len(outfits)} outfits")
			urls = await self.generate_flatlay_and_upload(
				outfits, thread_id=thread_id, user_id=user_id,
			)

			for i, (outfit, url) in enumerate(zip(outfits, urls)):
				if url:
					outfit["default_rendering_url"] = url
					if outfit_ids and i < len(outfit_ids) and outfit_ids[i]:
						try:
							await aexec(
								db.outfits.update_default_rendering_url,
								outfit_ids[i],
								url,
							)
						except Exception:
							pass

		return spawn(_task(), name=f"flatlay:{(thread_id or 'unknown')[:6]}")


_gemini_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
	"""Process-wide Gemini client."""
	global _gemini_client
	if _gemini_client is None:
		_gemini_client = GeminiClient()
	return _gemini_client
