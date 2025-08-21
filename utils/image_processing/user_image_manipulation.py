from PIL import Image
from io import BytesIO
from typing import Union
import typing
import logging

logger = logging.getLogger(__name__)


class UserImageManipulator:
    """Utility class for manipulating user images for virtual try-on"""
    
    # Target aspect ratio: 3:2 height to width (or 2:3 width to height)
    TARGET_WIDTH_TO_HEIGHT_RATIO = 2/3
    WHITE_COLOR = (255, 255, 255, 255)  # RGBA white with full opacity
    
    @classmethod
    def extend_to_target_ratio(
        cls, 
        image_input: Union[str, BytesIO, Image.Image, 'typing.BinaryIO']
    ) -> BytesIO:
        """
        Extend an image to the target 3:2 height/width ratio by adding white space.
        
        Never crops, condenses, or distorts the original image - only adds white space
        to achieve the target aspect ratio.
        
        Args:
            image_input: Path to image file, BytesIO object, PIL Image object, or file handle
            
        Returns:
            BytesIO object containing the extended image as PNG
        """
        # Load the image
        if isinstance(image_input, str):
            image = Image.open(image_input)
        elif isinstance(image_input, Image.Image):
            image = image_input
        elif hasattr(image_input, 'read'):
            # Handle file-like objects (BytesIO, file handles, etc.)
            image = Image.open(image_input)
        else:
            raise ValueError("image_input must be a file path, BytesIO object, PIL Image, or file handle")
        
        # Convert to RGBA to ensure we can add white background
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        original_width, original_height = image.size
        current_ratio = original_width / original_height
        
        # Check if we already have the target ratio (within a small tolerance)
        if abs(current_ratio - cls.TARGET_WIDTH_TO_HEIGHT_RATIO) < 0.001:
            return cls._image_to_bytesio(image)
        
        # Calculate new dimensions
        if current_ratio < cls.TARGET_WIDTH_TO_HEIGHT_RATIO:
            # Image is too tall/narrow, need to add width
            new_height = original_height
            new_width = int(original_height * cls.TARGET_WIDTH_TO_HEIGHT_RATIO)
        else:
            # Image is too wide/short, need to add height
            new_width = original_width
            new_height = int(original_width / cls.TARGET_WIDTH_TO_HEIGHT_RATIO)
        
        # Create new image with white background
        extended_image = Image.new('RGBA', (new_width, new_height), cls.WHITE_COLOR)
        
        # Calculate position to center the original image
        x_offset = (new_width - original_width) // 2
        y_offset = (new_height - original_height) // 2
        
        # Paste original image onto the white background
        extended_image.paste(image, (x_offset, y_offset), image)
            
        return cls._image_to_bytesio(extended_image)
    
    @classmethod
    def _image_to_bytesio(cls, image: Image.Image) -> BytesIO:
        """Convert PIL Image to BytesIO object as PNG"""
        img_bytes = BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        img_bytes.name = "extended_image.png"
        return img_bytes
    
    @classmethod
    def get_image_info(cls, image_input: Union[str, BytesIO, Image.Image, 'typing.BinaryIO']) -> dict:
        """
        Get information about an image including dimensions and aspect ratio.
        
        Args:
            image_input: Path to image file, BytesIO object, PIL Image object, or file handle
            
        Returns:
            Dictionary containing image information
        """
        # Load the image
        if isinstance(image_input, str):
            image = Image.open(image_input)
        elif isinstance(image_input, Image.Image):
            image = image_input
        elif hasattr(image_input, 'read'):
            # Handle file-like objects (BytesIO, file handles, etc.)
            image = Image.open(image_input)
        else:
            raise ValueError("image_input must be a file path, BytesIO object, PIL Image, or file handle")
        
        width, height = image.size
        current_ratio = width / height
        needs_extension = abs(current_ratio - cls.TARGET_WIDTH_TO_HEIGHT_RATIO) >= 0.001
        
        return {
            "width": width,
            "height": height,
            "current_ratio": current_ratio,
            "target_ratio": cls.TARGET_WIDTH_TO_HEIGHT_RATIO,
            "needs_extension": needs_extension,
            "mode": image.mode
        } 