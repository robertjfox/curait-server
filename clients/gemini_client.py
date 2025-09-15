import os
import logging
from io import BytesIO
from typing import List, Optional, Dict, Any
import json
import asyncio
import uuid
import _config as config
from clients.supabase_client import get_supabase_client
from interfaces.outfits_interface import OutfitsInterface
from utils.image_processing.image_gen import prepare_pil_for_upload, detect_image_mime_and_ext, compose_user_images_row, split_row_image_into_cells
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
			response = self.client.models.generate_content(
				model=self.MODEL,
				contents=contents,
				config=genai_types.GenerateContentConfig(
					temperature=0.4, top_p=0.8, top_k=32, candidate_count=1, response_modalities=["Image"]
				) if contents and len(contents) > 1 else None
			)
			end_time = time.time()
			logger.info(f"Gemini generation time: {end_time - start_time:.2f}s")
			return self._extract_image_bytes(response)
		except Exception as e:
			logger.error(f"Gemini generation error: {e}")
			return None

	def generate_virtual_tryon(self, *, grid_bytes: bytes) -> Optional[bytes]:
		"""Generate virtual try-on using product grid."""
		user_img = prepare_pil_for_upload(Image.open("_assets/user_full_body_female.png"))
		grid_img = prepare_pil_for_upload(Image.open(BytesIO(grid_bytes)))
		
		prompt = "Use the first image (user model) as base. Use the second image (clothing grid) to dress them. Same size, no text."
		return self._generate_image([prompt, user_img, grid_img])


	async def generate_flatlay_and_upload(self, outfits: List[Dict[str, Any]], *, user_gender: Optional[str] = None, thread_id: Optional[str] = None) -> List[Optional[str]]:
		"""Generate and upload flatlay images for multiple outfits."""
		def _generate():
			# Combine all outfits into a single prompt
			combined_prompt = """
			Dress the avatars in the following outfits from left to right.
			And provide individual background that fits the vibe of each outfit and is not distracting.
			The background should a scene that the user fits into naturally, not something that is contrived or abstract.
			Do not make the background or the lighting of the image too dark or too light.
			Keep each avatars body proportions EXACTLY as they are now, do not increase the height.
			You may slightly change the body positioning to give a bit of movement, like in a model photoshoot.
			The user should be looking directly at the camera. KEEP A HIGH FIDELITY OF THE USER'S FACE.
			Keep a bold red line between each cell.
			"""
			for i, outfit in enumerate(outfits):
				combined_prompt += f"Outfit {i+1}:\n{json.dumps(outfit, ensure_ascii=False)}\n\n"
			
			try:
				gender = (user_gender or "").strip().lower()
				if gender == "male":
					base_image = Image.open("_assets/user_full_body_male.png")
				else:
					base_image = Image.open("_assets/user_full_body_female.png")

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
				supabase.storage.from_(bucket).upload(filename, img_bytes, {"content-type": mime_type})
				url = supabase.storage.from_(bucket).get_public_url(filename)
				urls.append(url)
			else:
				urls.append(None)
		
		return urls


	def launch_flatlay_task(self, outfits: List[Dict[str, Any]], *, thread_id: Optional[str] = None, outfit_ids: Optional[List[str]] = None, user_gender: Optional[str] = None) -> asyncio.Task:
		"""Spawn flatlay generation task for multiple outfits."""
		outfits_interface = OutfitsInterface()

		async def _task() -> None:
			logger.debug(f'Generating Image for {len(outfits)} outfits')
			urls = await self.generate_flatlay_and_upload(outfits, thread_id=thread_id, user_gender=user_gender)
			
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