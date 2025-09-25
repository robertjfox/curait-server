import os
import logging
from io import BytesIO
from typing import List, Optional, Dict, Any
import asyncio
import uuid
import _config as config
from clients.supabase_client import get_supabase_client
from interfaces.outfits_interface import OutfitsInterface
from utils.image_processing.image_gen import prepare_pil_for_upload, detect_image_mime_and_ext, compose_user_images_row, split_row_image_into_cells, load_user_avatar_from_url
from utils.image_processing.user_selfie_handler import get_user_avatar_url
from ai.prompts.image_generation import create_flatlay_prompt, create_virtual_tryon_prompt, create_fullbody_avatar_prompt
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
for name, level in ("google", logging.WARNING), ("google.genai", logging.ERROR), ("grpc", logging.ERROR):
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


class GeminiClient:
	"""Thin wrapper around Google Gemini image generation for VTON and related tasks."""
	
	MODEL = "gemini-2.5-flash-image-preview"

	def __init__(self, *, api_key: Optional[str] = None):
		if not GEMINI_AVAILABLE:
			raise RuntimeError("Google Gemini SDK not available. Install with: pip install google-genai")
		self.client = genai.Client(api_key=(api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")))

	def _extract_image_bytes(self, response) -> Optional[bytes]:
		"""Extract image bytes from Gemini response."""
		if not response.candidates:
			return None
		for part in response.candidates[0].content.parts:
			if hasattr(part, "inline_data") and part.inline_data:
				return part.inline_data.data
		return None

	def _generate_image(self, contents: List) -> Optional[bytes]:
		"""Core image generation with error handling."""
		try:
			start_time = time.time()
			logger.info("[GEMINI] ▶︎ request started")
			response = self.client.models.generate_content(
				model=self.MODEL,
				contents=contents,
				config=genai_types.GenerateContentConfig(
					temperature=0.4, top_p=0.8, top_k=32, candidate_count=1, response_modalities=["Image"]
				) if contents and len(contents) > 1 else None
			)
			end_time = time.time()
			logger.info(f"[GEMINI] ✔︎ generation time: {end_time - start_time:.2f}s")
			return self._extract_image_bytes(response)
		except Exception as e:
			logger.error(f"[GEMINI] ❌ generation error: {e}")
			return None

	def generate_virtual_tryon(self, *, grid_bytes: bytes, user_id: str) -> Optional[bytes]:
		"""Generate virtual try-on using product grid."""
		avatar_url = get_user_avatar_url(user_id)
		user_img = prepare_pil_for_upload(load_user_avatar_from_url(avatar_url))
		grid_img = prepare_pil_for_upload(Image.open(BytesIO(grid_bytes)))
		
		prompt = create_virtual_tryon_prompt()
		return self._generate_image([prompt, user_img, grid_img])

	def generate_fullbody_avatar(self, *, selfie_bytes: bytes, height_cm: float | None, weight_kg: float | None, gender: str | None = None) -> Optional[bytes]:
		"""Generate a full-body studio avatar from a selfie using Gemini.

		The selfie should depict the user's face clearly. The output will be a
		front-facing full-body shot matching our standard reference style.
		"""
		try:
			selfie_img = prepare_pil_for_upload(Image.open(BytesIO(selfie_bytes)))
		except Exception:
			# If bytes fail to open, rethrow after logging
			logger.exception("Failed to load selfie bytes for avatar generation")
			raise

		prompt = create_fullbody_avatar_prompt(height_cm=height_cm, weight_kg=weight_kg, gender=gender)
		return self._generate_image([prompt, selfie_img])

	async def generate_flatlay_and_upload(self, outfits: List[Dict[str, Any]], *, user_id: str, thread_id: Optional[str] = None) -> List[Optional[str]]:
		"""Generate and upload flatlay images for multiple outfits."""
		def _generate():
			# Generate the prompt using the extracted function
			combined_prompt = create_flatlay_prompt(outfits)
			
			try:
				avatar_url = get_user_avatar_url(user_id)
				base_image = load_user_avatar_from_url(avatar_url)
				base_image = compose_user_images_row(base_image, len(outfits))

				logger.info(f"Gemini prompt for {len(outfits)} outfits")

				return self._generate_image([combined_prompt, base_image])
			except Exception:
				return self._generate_image([combined_prompt])  # Text-only fallback
		
		image_bytes = await asyncio.to_thread(_generate)
		if not image_bytes:
			return [None] * len(outfits)
		
		individual_images = split_row_image_into_cells(image_bytes, expected_cells=len(outfits))
		
		# Upload each individual image
		urls = []
		for i, img in enumerate(individual_images):
			if img:
				# Convert PIL Image to bytes for upload
				buffer = BytesIO()
				img_rgb = img.convert("RGB") if img.mode != "RGB" else img
				img_rgb.save(buffer, format="JPEG", quality=85)
				img_bytes = buffer.getvalue()
				
				mime_type, ext = detect_image_mime_and_ext(img_bytes)
				filename = f"outfit_tryon_{uuid.uuid4().hex}{ext}"
				bucket = getattr(config.model_config, 'FLATLAY_RENDERING', {}).get("bucket", "outfit-flatlay-images")
				
				supabase = get_supabase_client()
				
				# Simple retry logic for SSL issues
				max_retries = 3
				for attempt in range(max_retries):
					try:
						supabase.storage.from_(bucket).upload(filename, img_bytes, {"content-type": mime_type})
						url = supabase.storage.from_(bucket).get_public_url(filename)
						urls.append(url)
						break
					except Exception as e:
						if attempt == max_retries - 1:
							logger.error(f"Failed to upload after {max_retries} attempts: {e}")
							urls.append(None)
						else:
							logger.warning(f"Upload attempt {attempt + 1} failed, retrying: {e}")
							await asyncio.sleep(1)
			else:
				urls.append(None)
		
		return urls

	def launch_flatlay_task(
			self, 
			*, 
			outfits: List[Dict[str, Any]], 
			thread_id: Optional[str] = None, 
			outfit_ids: Optional[List[str]] = None, 
			user_id: str) -> asyncio.Task:
		"""Spawn flatlay generation task for multiple outfits."""
		outfits_interface = OutfitsInterface()

		async def _task() -> None:
			logger.debug(f'Generating Image for {len(outfits)} outfits')
			urls = await self.generate_flatlay_and_upload(outfits, thread_id=thread_id, user_id=user_id)
			
			for i, (outfit, url) in enumerate(zip(outfits, urls)):
				if url:
					outfit["default_rendering_url"] = url
					if outfit_ids and i < len(outfit_ids) and outfit_ids[i]:
						try:
							outfits_interface.update_default_rendering_url(outfit_ids[i], url)
						except Exception:
							pass

		return asyncio.create_task(_task())

def get_gemini_client() -> GeminiClient:
	"""Get or create a GeminiClient instance."""
	return GeminiClient() 