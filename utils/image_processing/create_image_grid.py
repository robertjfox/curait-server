import io
import math
import time
import uuid
import logging
import asyncio
from typing import List, Tuple, Optional

import requests
import httpx
from PIL import Image, ImageDraw, ImageFont

from clients.supabase_client import get_supabase_client


logger = logging.getLogger(__name__)

# Reserved bands so metadata does not overlay product imagery
METADATA_TOP_HEIGHT = 56
METADATA_BOTTOM_HEIGHT = 34


async def _download_image(url: str, timeout: float = 10.0) -> Optional[Image.Image]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=timeout)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
            img = img.convert("RGB")
            return img
    except Exception as e:
        logger.warning(f"Failed to download image from {url[:100]}...: {e}")
        return None


async def _download_image_with_client(client: httpx.AsyncClient, url: str) -> Optional[Image.Image]:
    """Download image using a shared client to avoid resource leaks."""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        img = img.convert("RGB")
        return img
    except Exception as e:
        logger.warning(f"Failed to download image from {url[:100]}...: {e}")
        return None


def _fit_into_cell(img: Image.Image, cell_size: Tuple[int, int]) -> Image.Image:
    cell_w, cell_h = cell_size
    w, h = img.size
    scale = min(cell_w / max(1, w), cell_h / max(1, h))
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    # paste onto white background centered
    canvas = Image.new("RGB", (cell_w, cell_h), (255, 255, 255))
    off_x = (cell_w - new_w) // 2
    off_y = (cell_h - new_h) // 2
    canvas.paste(img, (off_x, off_y))
    return canvas


def _draw_index_badge(img: Image.Image, index_label: str, cell_size: Tuple[int, int]) -> None:
    draw = ImageDraw.Draw(img)
    cell_w, cell_h = cell_size
    
    # Use a larger, bolder font for better readability
    try:
        # Try to use a larger default font or create a bigger one
        font = ImageFont.load_default()
        # Scale up the font size for better visibility
        font_size = 16
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
            except:
                font = ImageFont.load_default()
    except Exception:
        font = None
    
    # Larger padding for better visibility
    padding = 8
    text_w, text_h = draw.textbbox((0, 0), index_label, font=font)[2:]
    box_w = text_w + padding * 2
    box_h = text_h + padding * 2

    # bottom-right position inside the footer band
    x0 = cell_w - box_w - 8
    y0 = cell_h - box_h - 8

    # Solid dark background for better contrast
    box = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 220))
    img_rgba = img.convert("RGBA")
    img_rgba.paste(box, (x0, y0), box)

    # draw white text with better contrast
    draw = ImageDraw.Draw(img_rgba)
    draw.text((x0 + padding, y0 + padding), index_label, fill=(255, 255, 255, 255), font=font)
    img.paste(img_rgba.convert("RGB"))


def _draw_product_title(img: Image.Image, title: str, source: str, cell_size: Tuple[int, int]) -> None:
    """Draw product title and source in the reserved top band (no overlay)."""
    draw = ImageDraw.Draw(img)
    cell_w, cell_h = cell_size
    
    # Font for title and source - make source slightly larger/bolder for readability
    try:
        title_font_size = 16
        source_font_size = 18
        try:
            title_font = ImageFont.truetype("arial.ttf", title_font_size)
            source_font = ImageFont.truetype("arial.ttf", source_font_size)
        except:
            try:
                title_font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", title_font_size)
                source_font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", source_font_size)
            except:
                title_font = ImageFont.load_default()
                source_font = ImageFont.load_default()
    except Exception:
        title_font = source_font = None
    
    # Truncate long titles to fit in cell width
    max_text_width = cell_w - 16  # padding
    truncated_title = title
    if title_font:
        title_width = draw.textbbox((0, 0), title, font=title_font)[2]
        if title_width > max_text_width:
            while len(truncated_title) > 10 and draw.textbbox((0, 0), truncated_title + "...", font=title_font)[2] > max_text_width:
                truncated_title = truncated_title[:-1]
            truncated_title += "..."
    
    truncated_source = source
    if source_font:
        source_width = draw.textbbox((0, 0), source, font=source_font)[2]
        if source_width > max_text_width:
            while len(truncated_source) > 5 and draw.textbbox((0, 0), truncated_source + "...", font=source_font)[2] > max_text_width:
                truncated_source = truncated_source[:-1]
            truncated_source += "..."

    # Draw in the reserved top band, on a solid white background
    title_height = draw.textbbox((0, 0), truncated_title, font=title_font)[3] if title_font else 16
    title_y = 8
    draw.text((10, title_y), truncated_title, fill=(40, 40, 40), font=title_font)

    source_y = title_y + title_height + 4
    # Clamp to top band
    if source_y > METADATA_TOP_HEIGHT - 20:
        source_y = METADATA_TOP_HEIGHT - 20
    draw.text((10, source_y), truncated_source, fill=(20, 20, 20), font=source_font)


async def create_product_grid_and_upload(
    products: List[dict],
    index_labels: Optional[List[int]] = None,
    *,
    max_cols: int = 4,
    cell_size: Tuple[int, int] = (256, 256),
    padding: int = 8,
    background_color: Tuple[int, int, int] = (255, 255, 255),
    bucket: str = "product-ranking-grids",
    filename_prefix: str = "product_grid",
) -> Tuple[bytes, Optional[str], str]:
    """
    Create a composite grid image from given product data with non-overlapping metadata bands
    and upload to Supabase storage. Returns (png_bytes, public_url_or_none, filename).

    - products: List of product dicts with 'imageUrl', 'title', 'source' keys
    - index_labels: optional labels to overlay; defaults to 0..n-1
    """
    
    if not products:
        raise ValueError("products list is empty")

    start_time = time.time()
    n = len(products)
    logger.debug(f"🖼️ Starting grid creation for {n} products")
    labels = index_labels if (index_labels and len(index_labels) == n) else list(range(n))

    # Grid geometry
    cols = max(1, min(max_cols, n))
    rows = math.ceil(n / cols)
    cell_w, base_cell_h = cell_size

    # Expand cell height to include reserved bands if caller passed a "pure image" height
    cell_h = base_cell_h
    if cell_h < METADATA_TOP_HEIGHT + METADATA_BOTTOM_HEIGHT + 64:  # ensure minimum area for image
        cell_h = METADATA_TOP_HEIGHT + METADATA_BOTTOM_HEIGHT + max(64, base_cell_h)

    grid_w = cols * cell_w + (cols + 1) * padding
    grid_h = rows * cell_h + (rows + 1) * padding

    grid = Image.new("RGB", (grid_w, grid_h), background_color)

    # Download all images in parallel using a shared client
    download_start = time.time()
    async with httpx.AsyncClient(timeout=10.0) as shared_client:
        download_tasks = []
        for i, product in enumerate(products):
            image_url = product.get("imageUrl")
            if image_url:
                download_tasks.append(_download_image_with_client(shared_client, image_url))
            else:
                download_tasks.append(asyncio.create_task(asyncio.sleep(0, result=None)))
        
        downloaded_images = await asyncio.gather(*download_tasks, return_exceptions=True)
    
    download_time = time.time() - download_start
    logger.debug(f"🖼️ Downloaded {len(products)} images in parallel in {download_time:.1f}s")
    
    # Build cells
    successful_images = 0
    failed_images = 0
    
    image_area_h = cell_h - METADATA_TOP_HEIGHT - METADATA_BOTTOM_HEIGHT
    
    for i, (product, label) in enumerate(zip(products, labels)):
        image_url = product.get("imageUrl")
        title = product.get("title", "Unknown Product")
        source = product.get("source", "Unknown Source")
        
        # Use pre-downloaded image
        img = downloaded_images[i] if i < len(downloaded_images) else None
        
        if img is None or isinstance(img, Exception):
            failed_images += 1
            if image_url:
                logger.warning(f"🖼️ Failed to use image {i+1}/{n}: {image_url}")
            continue
            
        successful_images += 1

        # Create the full cell canvas (white)
        cell_img = Image.new("RGB", (cell_w, cell_h), (255, 255, 255))

        # Fit product image into the middle image area and paste it
        fitted_img = _fit_into_cell(img, (cell_w, image_area_h))
        cell_img.paste(fitted_img, (0, METADATA_TOP_HEIGHT))
        
        # Top band: product title and source
        _draw_product_title(cell_img, title, source, (cell_w, cell_h))
        
        # Bottom band: price (left) and index badge (right)
        price = product.get("price", "")
        if price and "$" in price:
            price_text = f"${price.split('.')[0].split('$')[-1]}"
            draw, font = ImageDraw.Draw(cell_img), ImageFont.load_default()
            tw, th = draw.textbbox((0, 0), price_text, font=font)[2:]
            text_x = 10
            # vertically center in footer band
            text_y = cell_h - METADATA_BOTTOM_HEIGHT + (METADATA_BOTTOM_HEIGHT - th) // 2
            # Draw simple text without overlay box (footer is already white)
            draw.text((text_x, text_y), price_text, fill=(40, 40, 40), font=font)
        
        # Index badge on bottom-right inside the footer band
        _draw_index_badge(cell_img, str(label), (cell_w, cell_h))

        r = i // cols
        c = i % cols
        x = padding + c * (cell_w + padding)
        y = padding + r * (cell_h + padding)
        grid.paste(cell_img, (x, y))
    
    # Encode to JPEG bytes (smaller for prompt)
    out = io.BytesIO()
    grid.save(out, format="JPEG", quality=85)
    img_bytes = out.getvalue()

    # Upload to Supabase
    public_url: Optional[str] = None
    filename = f"{filename_prefix}_{int(time.time())}_{uuid.uuid4().hex}.jpg"
    
    upload_start = time.time()
    try:
        supabase = get_supabase_client()
        supabase.storage.from_(bucket).upload(
            path=filename,
            file=img_bytes,
            file_options={"content-type": "image/jpeg"},
        )
        
        public_url = supabase.storage.from_(bucket).get_public_url(filename)
        upload_time = time.time() - upload_start
        logger.debug(f"🖼️ Uploaded grid to Supabase in {upload_time:.1f}s")
        
    except Exception as e:
        upload_time = time.time() - upload_start
        logger.error(f"Failed to upload grid to bucket '{bucket}' after {upload_time:.1f}s: {e}")
        public_url = None  # Ensure public_url is explicitly set to None on failure

    return img_bytes, public_url, filename 