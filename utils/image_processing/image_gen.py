import os
import logging
from io import BytesIO
from typing import Union, Tuple, Optional
import requests

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def to_pil_image(img_input: Union[bytes, str, Image.Image]) -> Image.Image:
    """Convert various image inputs to PIL Image."""
    if isinstance(img_input, Image.Image):
        return img_input
    elif isinstance(img_input, bytes):
        return Image.open(BytesIO(img_input))
    elif isinstance(img_input, str):
        if img_input.startswith(("http://", "https://")):
            raise ValueError("Remote image URLs not supported, download first")
        return Image.open(img_input)
    else:
        raise ValueError(f"Unsupported image input type: {type(img_input)}")


def load_user_avatar_from_url(avatar_url: str) -> Optional[Image.Image]:
    """Fetch a user's avatar image; returns None if unavailable.

    Guest users (and anyone who hasn't uploaded a selfie) will not have an
    avatar, so this is an expected soft-failure path. Callers should handle
    None by falling back to text-only generation.
    """
    try:
        response = requests.get(avatar_url, timeout=10)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
    except Exception as e:
        logger.debug(f"🎭 No avatar available at {avatar_url}: {e}")
        return None


def prepare_pil_for_upload(img: Image.Image) -> Image.Image:
    """Convert to RGB and compress quality without changing dimensions."""
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=75, optimize=True)
    buffer.seek(0)
    img = Image.open(buffer)
    
    return img


def detect_image_mime_and_ext(image_input: Union[bytes, Image.Image]) -> Tuple[str, str]:
    """Best-effort sniffing of image mime and extension from header bytes."""
    # Convert PIL Image to bytes if needed
    if isinstance(image_input, Image.Image):
        buffer = BytesIO()
        # Convert to RGB if not already
        img = image_input.convert("RGB") if image_input.mode != "RGB" else image_input
        img.save(buffer, format="JPEG", quality=85)
        image_bytes = buffer.getvalue()
    else:
        image_bytes = image_input
    
    if not image_bytes:
        return ("image/jpeg", ".jpg")
    header = image_bytes[:12]
    if header.startswith(b"\xFF\xD8"):
        return ("image/jpeg", ".jpg")
    if header.startswith(b"\x89PNG"):
        return ("image/png", ".png")
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ("image/webp", ".webp")
    return ("image/jpeg", ".jpg")


def compose_user_images_row(
    base_image_input: Union[Image.Image, bytes, str],
    num_images: int,
) -> Image.Image:
    """Tile the same base image X times in a 1xX row with 3px red separators on a white background.

    Args:
        base_image_input: PIL Image, bytes, or local file path of the base image.
        num_images: Number of times to tile the image horizontally.

    Returns:
        A PIL Image with the base image repeated horizontally `num_images` times,
        separated by vertical red lines of width 3 on a white background.
    """
    if num_images <= 0:
        raise ValueError("num_images must be >= 1")

    img = to_pil_image(base_image_input)
    if img.mode != "RGB":
        img = img.convert("RGB")

    width, height = img.size

    separator_width = 3
    separator_color = (255, 0, 0)
    background_color = (255, 255, 255)

    total_width = num_images * width + max(0, num_images - 1) * separator_width
    canvas = Image.new("RGB", (total_width, height), color=background_color)
    draw = ImageDraw.Draw(canvas)

    x_offset = 0
    for i in range(num_images):
        canvas.paste(img, (x_offset, 0))
        x_offset += width
        if i < num_images - 1:
            draw.rectangle([(x_offset, 0), (x_offset + separator_width - 1, height - 1)], fill=separator_color)
            x_offset += separator_width

    return canvas


def split_row_image_into_cells(
    img_input: Union[Image.Image, bytes, str],
    expected_cells: int | None = None,
    separator_color: Tuple[int, int, int] = (255, 0, 0),
    color_tolerance: int = 20,
    min_separator_fraction: float = 0.9,
) -> list[Image.Image]:
    """Split a 1xX composed row image back into its individual cells.

    Attempts to detect vertical red separator columns (default approx (255,0,0))
    and splits on those boundaries. If none are detected, optionally falls back
    to equal-width splits if `expected_cells` is provided; otherwise returns the
    original image as a single cell.

    Args:
        img_input: PIL Image, bytes, or local file path to the composed image.
        expected_cells: If provided and no separators are detected, split into
            this many equal-width parts.
        separator_color: Target RGB for the separator.
        color_tolerance: Max per-channel absolute difference to consider "near" the separator color.
        min_separator_fraction: Fraction of pixels in a column that must be near
            the separator color for it to be considered a separator column.

    Returns:
        A list of PIL Images corresponding to each cell.
    """
    def is_near_color(rgb: Tuple[int, int, int], target: Tuple[int, int, int], tol: int) -> bool:
        r, g, b = rgb
        tr, tg, tb = target
        return abs(r - tr) <= tol and abs(g - tg) <= tol and abs(b - tb) <= tol

    img = to_pil_image(img_input)
    if img.mode != "RGB":
        img = img.convert("RGB")

    width, height = img.size
    pixels = img.load()

    separator_columns: list[bool] = []
    for x in range(width):
        redish_count = 0
        for y in range(height):
            if is_near_color(pixels[x, y], separator_color, color_tolerance):
                redish_count += 1
        fraction = redish_count / float(height)
        separator_columns.append(fraction >= min_separator_fraction)

    # Group consecutive separator columns into ranges
    separator_ranges: list[Tuple[int, int]] = []
    in_run = False
    run_start = 0
    for x, is_sep in enumerate(separator_columns):
        if is_sep and not in_run:
            in_run = True
            run_start = x
        elif not is_sep and in_run:
            in_run = False
            separator_ranges.append((run_start, x - 1))
    if in_run:
        separator_ranges.append((run_start, width - 1))

    # Build cell boundaries between separator ranges
    cells: list[Image.Image] = []
    current_left = 0
    for (sep_start, sep_end) in separator_ranges:
        if sep_start > current_left:
            # crop left cell up to start of separator
            cells.append(img.crop((current_left, 0, sep_start, height)))
        current_left = sep_end + 1

    if current_left < width:
        cells.append(img.crop((current_left, 0, width, height)))

    logger.info(f"Found {len(separator_ranges)} separator ranges, extracted {len(cells)} cells")

    # If separators are missing or the count doesn't match expected, fall back to equal widths
    if expected_cells and expected_cells > 1 and (len(separator_ranges) == 0 or len(cells) != expected_cells):
        logger.info(f"Falling back to {expected_cells} equal-width splits (sep_ranges={len(separator_ranges)}, detected_cells={len(cells)})")
        base = width // expected_cells
        remainder = width % expected_cells
        x = 0
        cells = []
        for i in range(expected_cells):
            w = base + (1 if i < remainder else 0)
            cells.append(img.crop((x, 0, x + w, height)))
            x += w
    elif not cells:
        # No cells and no expected_cells: return whole image to avoid empty result
        cells = [img]

    # Filter out any accidental zero-width crops
    cells = [c for c in cells if c.width > 0 and c.height > 0]

    if not cells:
        logger.warning("split_row_image_into_cells produced no cells; returning original image")
        return [img]

    return cells 

