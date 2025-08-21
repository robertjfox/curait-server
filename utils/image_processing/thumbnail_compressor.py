import io
import time
import uuid
import os
import asyncio
import logging
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image, ImageOps, ImageDraw, ImageFont
import httpx
import requests
from clients.supabase_client import get_supabase_client
from utils.image_processing.user_selfie_handler import get_user_selfie_url

logger = logging.getLogger(__name__)


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    """Wrap text to fit within max_width, returning list of lines (max 2 lines)."""
    words = text.split()
    lines = []
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
                # Word is too long, truncate it
                current_line = word[:20] + "..." if len(word) > 20 else word
        
        # Limit to 2 lines
        if len(lines) >= 2:
            break
    
    if current_line and len(lines) < 2:
        lines.append(current_line)
    
    return lines[:2]  # Ensure max 2 lines


def _create_circular_mask(size: int) -> Image.Image:
    """Create a circular mask for the user face"""
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse([0, 0, size, size], fill=255)
    return mask


def _add_user_face_overlay(grid: Image.Image, grid_width: int, grid_height: int, user_data: Optional[Dict[str, Any]] = None) -> Image.Image:
    """Add circular user face overlay in the center of the grid"""
    # Determine user face filename from user data
    user_face_url = None
    user_id = user_data.get("id") if user_data else None
    
    # Try user-specific selfie first
    if user_id:
        filename = f"user_face_{user_id}.png"
        try:
            user_face_url = get_user_selfie_url(filename)
            logger.debug(f"🎭 Found user-specific face image: {filename}")
        except Exception:
            user_face_url = None
    
    if not user_face_url:
        # Fallback to gender-based naming if user-specific image not found
        gender = (user_data.get("gender", "female") if user_data else "female").lower()
        filename = f"user_face_{gender}.png"
        try:
            user_face_url = get_user_selfie_url(filename)
            logger.debug(f"🎭 Using gender-based face image: {filename}")
        except Exception:
            user_face_url = None
    
    if not user_face_url:
        logger.debug("🎭 No user face image found, skipping overlay")
        return grid  # Return original grid if no user face found
    
    try:
        # Download and load user face image from Supabase (sync request for simplicity)
        import requests
        
        resp = requests.get(user_face_url, timeout=10)
        resp.raise_for_status()
        user_face = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        
        # Calculate overlay size (about 2/5 of the grid width, with larger max size)
        overlay_size = min(int(grid_width * 0.4), int(grid_height * 0.4), 150)
        
        # Resize user face to overlay size while maintaining aspect ratio
        user_face = ImageOps.contain(user_face, (overlay_size, overlay_size), Image.LANCZOS)
        
        # Create circular mask
        mask = _create_circular_mask(overlay_size)
        
        # Create a new image for the circular face
        circular_face = Image.new('RGBA', (overlay_size, overlay_size), (0, 0, 0, 0))
        
        # Paste the user face centered in the circular area
        face_w, face_h = user_face.size
        paste_x = (overlay_size - face_w) // 2
        paste_y = (overlay_size - face_h) // 2
        circular_face.paste(user_face, (paste_x, paste_y))
        
        # Apply circular mask
        circular_face.putalpha(mask)
        
        # Add a subtle border around the circle
        border_size = 2
        border_overlay = Image.new('RGBA', (overlay_size + border_size * 2, overlay_size + border_size * 2), (0, 0, 0, 0))
        border_draw = ImageDraw.Draw(border_overlay)
        border_draw.ellipse([0, 0, overlay_size + border_size * 2, overlay_size + border_size * 2], 
                          fill=None, outline=(255, 255, 255, 200), width=border_size)
        
        # Convert grid to RGBA for overlay
        grid_rgba = grid.convert("RGBA")
        
        # Calculate center position
        center_x = (grid_width - (overlay_size + border_size * 2)) // 2
        center_y = (grid_height - (overlay_size + border_size * 2)) // 2
        
        # Paste border first
        grid_rgba.paste(border_overlay, (center_x, center_y), border_overlay)
        
        # Paste circular face
        face_x = center_x + border_size
        face_y = center_y + border_size
        grid_rgba.paste(circular_face, (face_x, face_y), circular_face)
        
        # Convert back to RGB
        return grid_rgba.convert("RGB")
        
    except Exception as e:
        # If anything goes wrong, return the original grid
        return grid


async def compress_thumbnails_to_grid(
        products: List[Dict[str, Any]], 
        keywords: List[str] = None, 
        cell_size: int = 240, 
        final_max_side: int = 512, 
        jpeg_quality: int = 70,
        user_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Tuple[bytes, Optional[str]]]:
    """
    Download up to 4 product images, and compress them into a single 2x2 grid JPEG with product titles as labels.
    Products should have 'imageUrl' and 'title' keys.
    Optionally adds a circular user face overlay in the center if available.
    Uploads to Supabase for verification and returns (jpeg_bytes, public_url_or_none).
    
    Args:
        products: List of product dicts with 'imageUrl' and 'title' keys
        keywords: Deprecated - product titles are used as labels instead
        cell_size: Size of each cell in the grid
        final_max_side: Maximum dimension of final grid image
        jpeg_quality: JPEG compression quality (1-100)
        user_data: User data dict with id for face image lookup
    """
    if not products:
        return None
    
    # Download images with product titles as labels
    product_data = []
    async with httpx.AsyncClient() as client:
        for i, product in enumerate(products[:4]):  # Max 4 for 2x2 grid
            try:
                url = product.get("imageUrl", "")
                # Use product title as label
                label = product.get("title", f"Item {i+1}")
                if not url:
                    logger.warning(f"⚠️  Product {i+1} missing imageUrl, skipping")
                    continue
                    
                logger.debug(f"📥 Downloading product image {i+1}: {label}")
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
                img = Image.open(io.BytesIO(response.content)).convert("RGB")
                
                product_data.append({"image": img, "label": label})
                logger.debug(f"✅ Successfully loaded product {i+1}")
            except Exception as e:
                logger.warning(f"❌ Failed to load product {i+1}: {str(e)}")
                continue  # Skip failed downloads
    
    if not product_data:
        return None
    
    # Calculate dimensions with space for 2-line labels
    header_height = 50  # Increased space for 2 lines of label text with padding
    total_cell_height = cell_size + header_height
    
    # Create 2x2 grid with label space
    grid_width = cell_size * 2
    grid_height = total_cell_height * 2
    grid = Image.new("RGB", (grid_width, grid_height), (255, 255, 255))
    
    # Get font for labels
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 12)  # Slightly smaller font
    except:
        font = ImageFont.load_default()
    
    draw = ImageDraw.Draw(grid)
    
    for i, item in enumerate(product_data):
        img = item["image"]
        label = item["label"]
        
        # Fit image into cell while maintaining aspect ratio
        img = ImageOps.contain(img, (cell_size, cell_size), Image.LANCZOS)
        
        # Calculate position
        col = i % 2
        row = i // 2
        x = col * cell_size
        y = row * total_cell_height + header_height  # Leave space for title
        
        # Paste image
        grid.paste(img, (x, y))
        
        # Add label above image with alignment to avoid center circle
        label_y = row * total_cell_height + 5  # 5px padding from top
        
        # Wrap text to fit in cell width with some padding
        max_text_width = cell_size - 10  # 5px padding on each side
        wrapped_lines = wrap_text(label, font, max_text_width)
        
        # Draw each line of text with side-based alignment
        line_height = 16  # Approximate line height
        for line_idx, line in enumerate(wrapped_lines):
            bbox = font.getbbox(line)
            text_width = bbox[2] - bbox[0]
            
            # Align text based on column to avoid center circle
            if col == 0:  # Left column - align left
                line_x = x + 5  # 5px padding from left edge
            else:  # Right column - align right
                line_x = x + cell_size - text_width - 5  # 5px padding from right edge
            
            line_y = label_y + (line_idx * line_height)
            
            draw.text((line_x, line_y), line, fill=(0, 0, 0), font=font)
    
    # Add user face overlay in the center if available
    grid = _add_user_face_overlay(grid, grid_width, grid_height, user_data)
    
    # Downscale final composite if too large
    w, h = grid.size
    scale = min(final_max_side / max(w, h), 1.0)
    if scale < 1.0:
        grid = grid.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    
    # Encode to JPEG
    buf = io.BytesIO()
    grid.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    img_bytes = buf.getvalue()
    
    # Upload to Supabase for verification
    public_url = None
    filename = f"vton_grid_{int(time.time())}_{uuid.uuid4().hex[:8]}.jpg"
    
    try:
        supabase = get_supabase_client()
        supabase.storage.from_("vton-image-input-grid").upload(
            path=filename,
            file=img_bytes,
            file_options={"content-type": "image/jpeg"},
        )
        public_url = supabase.storage.from_("vton-image-input-grid").get_public_url(filename)
    except Exception as e:
        logger.error(f"❌ Failed to upload VTON grid to Supabase: {str(e)}")
        pass  # Continue without upload if it fails
    
    return img_bytes, public_url 