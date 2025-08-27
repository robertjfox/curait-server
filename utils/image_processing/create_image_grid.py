import io
import math
import time
import uuid
import logging
import asyncio
from typing import List, Tuple, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

import requests
import httpx
from PIL import Image, ImageDraw, ImageFont

from clients.supabase_client import get_supabase_client


logger = logging.getLogger(__name__)

# Reserved bands so metadata does not overlay product imagery - BALANCED for readability + image space
METADATA_TOP_HEIGHT = 24  # Increased for better text readability
METADATA_BOTTOM_HEIGHT = 16  # Increased for better text readability

# Cache for fonts to avoid repeated loading
_font_cache: Dict[int, Any] = {}

def _get_cached_font(size: int, bold: bool = False) -> Any:
    """Get cached font or create and cache it."""
    cache_key = f"{size}{'_bold' if bold else ''}"
    if cache_key not in _font_cache:
        try:
            if bold:
                _font_cache[cache_key] = ImageFont.truetype("/System/Library/Fonts/Arial Bold.ttf", size)
            else:
                _font_cache[cache_key] = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", size)
        except:
            try:
                if bold:
                    _font_cache[cache_key] = ImageFont.truetype("arialbd.ttf", size)
                else:
                    _font_cache[cache_key] = ImageFont.truetype("arial.ttf", size)
            except:
                _font_cache[cache_key] = ImageFont.load_default()
    return _font_cache[cache_key]

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

def _fit_into_cell(img: Image.Image, cell_size: Tuple[int, int], max_fill: bool = True) -> Image.Image:
    cell_w, cell_h = cell_size
    w, h = img.size
    
    if max_fill:
        # Fill the entire cell, cropping if necessary for maximum visibility
        scale = max(cell_w / max(1, w), cell_h / max(1, h))
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        
        # Resize image
        img = img.resize((new_w, new_h), Image.LANCZOS)
        
        # Create canvas and center the (potentially larger) image
        canvas = Image.new("RGB", (cell_w, cell_h), (255, 255, 255))
        off_x = (cell_w - new_w) // 2
        off_y = (cell_h - new_h) // 2
        
        # Crop the image if it's larger than the cell
        if new_w > cell_w or new_h > cell_h:
            crop_x = max(0, -off_x)
            crop_y = max(0, -off_y)
            crop_w = min(new_w, cell_w)
            crop_h = min(new_h, cell_h)
            img = img.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
            off_x = max(0, off_x)
            off_y = max(0, off_y)
        
        canvas.paste(img, (off_x, off_y))
        return canvas
    else:
        # Original fit-to-contain logic
        scale = min(cell_w / max(1, w), cell_h / max(1, h))
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGB", (cell_w, cell_h), (255, 255, 255))
        off_x = (cell_w - new_w) // 2
        off_y = (cell_h - new_h) // 2
        canvas.paste(img, (off_x, off_y))
        return canvas

def _draw_index_badge(img: Image.Image, index_label: str, cell_size: Tuple[int, int]) -> None:
    draw = ImageDraw.Draw(img)
    cell_w, cell_h = cell_size
    
    # Larger, bold font for better visibility
    font = _get_cached_font(12, bold=True)  # Larger and bold for clarity
    
    # Adequate padding for readability
    padding = 3  # Slightly more padding for better appearance
    text_w, text_h = draw.textbbox((0, 0), index_label, font=font)[2:]
    box_w = text_w + padding * 2
    box_h = text_h + padding * 2

    # bottom-right position inside the footer band
    x0 = cell_w - box_w - 3
    y0 = cell_h - box_h - 3

    # High contrast background for better visibility
    draw.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=(0, 0, 0))
    draw.text((x0 + padding, y0 + padding), index_label, fill=(255, 255, 255), font=font)

def _draw_product_title(img: Image.Image, title: str, source: str, cell_size: Tuple[int, int]) -> None:
    """Draw product source in the reserved top band (larger and centered)."""
    draw = ImageDraw.Draw(img)
    cell_w, cell_h = cell_size
    
    # Larger, bold font for better source visibility
    source_font = _get_cached_font(12, bold=True)  # Increased from 9 to 12
    
    # Smarter truncation logic based on actual text width
    max_chars = cell_w // 6  # Adjusted for larger font
    truncated_source = source[:max_chars] + "..." if len(source) > max_chars else source

    # Center the source text horizontally in the top band
    bbox = draw.textbbox((0, 0), truncated_source, font=source_font)
    text_w = bbox[2] - bbox[0]
    x_pos = (cell_w - text_w) // 2
    y_pos = (METADATA_TOP_HEIGHT - bbox[3]) // 2  # Center vertically in the top band
    
    draw.text((x_pos, y_pos), truncated_source, fill=(0, 0, 0), font=source_font)  # Black for better contrast

def _process_single_image(args: Tuple[Any, int, int, int, int, str, str, str]) -> Optional[Image.Image]:
    """Process a single image in a thread for parallel processing."""
    try:
        img, cell_w, cell_h, image_area_h, label, title, source, price = args
        if img is None or isinstance(img, Exception):
            return None
            
        # Create the full cell canvas (white)
        cell_img = Image.new("RGB", (cell_w, cell_h), (255, 255, 255))

        # Fit product image into the middle image area and paste it
        fitted_img = _fit_into_cell(img, (cell_w, image_area_h))
        cell_img.paste(fitted_img, (0, METADATA_TOP_HEIGHT))
        
        # Add source metadata - centered and larger
        _draw_product_title(cell_img, title, source, (cell_w, cell_h))
        
        # Index badge in bottom right
        _draw_index_badge(cell_img, str(label), (cell_w, cell_h))
        
        return cell_img
    except Exception as e:
        logger.warning(f"Failed to process image: {e}")
        return None

async def create_product_grid_and_upload(
    products: List[dict],
    index_labels: Optional[List[int]] = None,
    *,
    max_cols: int = 4,
    cell_size: Tuple[int, int] = (160, 160),  # Reduced from (256, 256)
    padding: int = 4,  # Reduced from 8
    background_color: Tuple[int, int, int] = (255, 255, 255),
    bucket: str = "product-ranking-grids",
    filename_prefix: str = "product_grid",
    ranking_keywords: Optional[str] = None,
) -> Tuple[bytes, Optional[str], str]:
    """
    OPTIMIZED: Create a composite grid image from given product data with minimal metadata
    and upload to Supabase storage. Returns (png_bytes, public_url_or_none, filename).

    Performance optimizations:
    - Smaller cell size (160x160 vs 256x256)
    - Reduced metadata bands
    - Simplified drawing operations
    - Parallel image processing
    - Lower JPEG quality for smaller files
    - Cached fonts
    """
    
    if not products:
        raise ValueError("products list is empty")

    n = len(products)   
    labels = index_labels if (index_labels and len(index_labels) == n) else list(range(n))

    # Calculate header height if we have ranking keywords
    header_height = 0
    if ranking_keywords:
        header_height = 80  # Fixed height for a two-line header
    
    # Grid geometry
    cols = max(1, min(max_cols, n))
    rows = math.ceil(n / cols)
    cell_w, base_cell_h = cell_size

    # Expand cell height to include reserved bands if caller passed a "pure image" height
    cell_h = base_cell_h
    if cell_h < METADATA_TOP_HEIGHT + METADATA_BOTTOM_HEIGHT + 64:  # Ensure adequate image space
        cell_h = METADATA_TOP_HEIGHT + METADATA_BOTTOM_HEIGHT + max(64, base_cell_h)

    grid_w = cols * cell_w + (cols + 1) * padding
    grid_h = rows * cell_h + (rows + 1) * padding + header_height

    grid = Image.new("RGB", (grid_w, grid_h), background_color)
    
    # Draw header if we have ranking keywords
    if ranking_keywords:
        draw = ImageDraw.Draw(grid)
        # Fixed, bold font size; we split into two lines to avoid cropping
        header_font = _get_cached_font(24, bold=True)
        sub_font = _get_cached_font(20, bold=True)
        
        line1 = "RANKING GOAL:"
        line2 = str(ranking_keywords)
        
        # Measure lines
        bbox1 = draw.textbbox((0, 0), line1, font=header_font)
        text_w1 = bbox1[2] - bbox1[0]
        text_h1 = bbox1[3] - bbox1[1]
        
        bbox2 = draw.textbbox((0, 0), line2, font=sub_font)
        text_w2 = bbox2[2] - bbox2[0]
        text_h2 = bbox2[3] - bbox2[1]
        
        # Compute positions: center both lines, stacked
        total_text_h = text_h1 + 6 + text_h2
        start_y = (header_height - total_text_h) // 2
        x1 = (grid_w - text_w1) // 2
        x2 = (grid_w - text_w2) // 2
        
        # Draw lines
        draw.text((x1, start_y), line1, fill=(0, 0, 0), font=header_font)
        draw.text((x2, start_y + text_h1 + 6), line2, fill=(0, 0, 0), font=sub_font)

    # Download all images in parallel with reduced timeout
    async with httpx.AsyncClient(timeout=5.0) as shared_client:  # Reduced timeout from 10s
        download_tasks = []
        for i, product in enumerate(products):
            image_url = product.get("imageUrl")
            if image_url:
                download_tasks.append(_download_image_with_client(shared_client, image_url))
            else:
                download_tasks.append(asyncio.create_task(asyncio.sleep(0, result=None)))
        
        downloaded_images = await asyncio.gather(*download_tasks, return_exceptions=True)
    
    
    # Process images in parallel using thread pool
    image_area_h = cell_h - METADATA_TOP_HEIGHT - METADATA_BOTTOM_HEIGHT
    
    # Prepare arguments for parallel processing
    process_args = []
    for i, (product, label) in enumerate(zip(products, labels)):
        img = downloaded_images[i] if i < len(downloaded_images) else None
        title = product.get("title", "Unknown Product")
        source = product.get("source", "Unknown Source")
        price = product.get("price", "")
        process_args.append((img, cell_w, cell_h, image_area_h, label, title, source, price))
    
    # Process images in parallel
    with ThreadPoolExecutor(max_workers=min(8, len(process_args))) as executor:
        processed_cells = list(executor.map(_process_single_image, process_args))
    
    # Compose grid
    successful_images = 0
    for i, cell_img in enumerate(processed_cells):
        if cell_img is not None:
            successful_images += 1
            r = i // cols
            c = i % cols
            x = padding + c * (cell_w + padding)
            y = header_height + padding + r * (cell_h + padding)  # Offset by header height
            grid.paste(cell_img, (x, y))
    
    # Encode to JPEG bytes with lower quality for smaller size
    out = io.BytesIO()
    grid.save(out, format="JPEG", quality=70, optimize=True)  # Reduced quality from 85
    img_bytes = out.getvalue()

    # Upload to Supabase
    public_url: Optional[str] = None
    filename = f"{filename_prefix}_{int(time.time())}_{uuid.uuid4().hex}.jpg"
    
    try:
        supabase = get_supabase_client()
        supabase.storage.from_(bucket).upload(
            path=filename,
            file=img_bytes,
            file_options={"content-type": "image/jpeg"},
        )
        
        public_url = supabase.storage.from_(bucket).get_public_url(filename)

    except Exception as e:
        logger.error(f"Failed to upload grid to bucket '{bucket}': {e}")
        public_url = None  # Ensure public_url is explicitly set to None on failure

    return img_bytes, public_url, filename 