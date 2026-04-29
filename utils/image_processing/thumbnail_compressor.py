import io
import time
import uuid
import logging
import asyncio
from typing import List, Optional, Tuple, Dict, Any

from PIL import Image, ImageOps, ImageDraw, ImageFont
import httpx
from clients.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
	"""Wrap text to fit within max_width, returning at most 2 lines."""
	words = text.split()
	lines: List[str] = []
	current_line = ""

	for word in words:
		test_line = current_line + (" " if current_line else "") + word
		bbox = font.getbbox(test_line)
		text_width = bbox[2] - bbox[0]

		if text_width <= max_width:
			current_line = test_line
		else:
			if current_line:
				lines.append(current_line)
				current_line = word
			else:
				current_line = word[:20] + "..." if len(word) > 20 else word

		if len(lines) >= 2:
			break

	if current_line and len(lines) < 2:
		lines.append(current_line)

	return lines[:2]


def _compose_grid(
	product_data: List[Dict[str, Any]],
	*,
	cell_size: int,
	final_max_side: int,
	jpeg_quality: int,
) -> bytes:
	"""Synchronous PIL grid composition (run in a worker thread)."""
	header_height = 50
	total_cell_height = cell_size + header_height

	grid_width = cell_size * 2
	grid_height = total_cell_height * 2
	grid = Image.new("RGB", (grid_width, grid_height), (255, 255, 255))

	try:
		font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 12)
	except Exception:
		font = ImageFont.load_default()

	draw = ImageDraw.Draw(grid)

	for i, item in enumerate(product_data):
		img: Image.Image = item["image"]
		label: str = item["label"]

		img = ImageOps.contain(img, (cell_size, cell_size), Image.LANCZOS)

		col = i % 2
		row = i // 2
		x = col * cell_size
		y = row * total_cell_height + header_height

		grid.paste(img, (x, y))

		label_y = row * total_cell_height + 5
		max_text_width = cell_size - 10
		wrapped_lines = wrap_text(label, font, max_text_width)

		line_height = 16
		for line_idx, line in enumerate(wrapped_lines):
			bbox = font.getbbox(line)
			text_width = bbox[2] - bbox[0]
			if col == 0:
				line_x = x + 5
			else:
				line_x = x + cell_size - text_width - 5
			line_y = label_y + (line_idx * line_height)
			draw.text((line_x, line_y), line, fill=(0, 0, 0), font=font)

	w, h = grid.size
	scale = min(final_max_side / max(w, h), 1.0)
	if scale < 1.0:
		grid = grid.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

	buf = io.BytesIO()
	grid.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
	return buf.getvalue()


async def compress_thumbnails_to_grid(
	products: List[Dict[str, Any]],
	cell_size: int = 240,
	final_max_side: int = 512,
	jpeg_quality: int = 70,
) -> Optional[Tuple[bytes, Optional[str]]]:
	"""Download up to 4 product images and compose them into a 2x2 grid JPEG.

	Network I/O uses httpx async; PIL composition runs in a worker thread
	(off the event loop); the Supabase upload also runs in a worker thread.
	"""
	if not products:
		return None

	product_data: List[Dict[str, Any]] = []
	async with httpx.AsyncClient(
		timeout=10.0,
		limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
	) as client:
		for i, product in enumerate(products[:4]):
			try:
				url = product.get("imageUrl", "")
				label = product.get("title", f"Item {i+1}")
				if not url:
					logger.warning(f"⚠️  Product {i+1} missing imageUrl, skipping")
					continue

				response = await client.get(url)
				response.raise_for_status()
				img = Image.open(io.BytesIO(response.content)).convert("RGB")

				product_data.append({"image": img, "label": label})
			except Exception as e:
				logger.warning(f"❌ Failed to load product {i+1}: {str(e)}")
				continue

	if not product_data:
		return None

	img_bytes = await asyncio.to_thread(
		_compose_grid,
		product_data,
		cell_size=cell_size,
		final_max_side=final_max_side,
		jpeg_quality=jpeg_quality,
	)

	filename = f"vton_grid_{int(time.time())}_{uuid.uuid4().hex[:8]}.jpg"

	def _upload() -> Optional[str]:
		try:
			supabase = get_supabase_client()
			storage = supabase.storage.from_("vton-image-input-grid")
			storage.upload(
				path=filename,
				file=img_bytes,
				file_options={"content-type": "image/jpeg"},
			)
			return storage.get_public_url(filename)
		except Exception as e:
			logger.error(f"❌ Failed to upload VTON grid to Supabase: {str(e)}")
			return None

	public_url = await asyncio.to_thread(_upload)
	return img_bytes, public_url
