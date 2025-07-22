from PIL import Image
import io
import zipfile
import os
from typing import Dict, Any

class ShowerCropperService:
    """
    Service for cropping shower-type forms: extracts only the fixed-position handwritten/text area
    based on visual layout measurements.
    """

    @staticmethod
    def crop_fixed_area(image_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Crops the image to a fixed area where the handwritten content typically appears.

        Args:
            image_data: Raw bytes of the image file
            filename: Original filename

        Returns:
            Dictionary with a ZIP buffer containing the cropped text area and metadata
        """
        # Load the image
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        print(f"Original image size: {width}x{height} pixels")

        # Fixed crop boundaries based on visual inspection of form layout
        top = int(height * 0.325)     # ~32.5% from top
        bottom = int(height * 0.875)  # ~87.5% from top
        text_box = (0, top, width, bottom)

        print(f"Cropping fixed text area: {text_box}")

        # Crop the image
        text_image = image.crop(text_box)

        # Prepare output filename
        base_name, ext = os.path.splitext(filename)
        cropped_filename = f"{base_name}_text_area{ext}"

        # Create an in-memory ZIP with the cropped image
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            text_bytes = io.BytesIO()
            text_image.save(text_bytes, format=image.format)
            zip_file.writestr(cropped_filename, text_bytes.getvalue())

        zip_buffer.seek(0)

        return {
            "zip_buffer": zip_buffer,
            "filename": f"{base_name}_cropped.zip",
            "body_dimensions": text_image.size
        }
        
    @staticmethod
    def crop_fixed_area_obituaries(image_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Crops the image to a fixed area optimized for obituaries layout.
        
        Args:
            image_data: Raw bytes of the image file
            filename: Original filename
            
        Returns:
            Dictionary with a ZIP buffer containing the cropped text area and metadata
        """
        # Load the image
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        print(f"Original image size: {width}x{height} pixels")
        
        # Fixed crop boundaries optimized for obituaries
        top = int(height * 0.25)      # ~25% from top
        bottom = int(height * 0.81)   # ~81% from top
        text_box = (0, top, width, bottom)
        
        print(f"Cropping obituary area: {text_box}")
        
        # Crop the image
        text_image = image.crop(text_box)
        
        # Prepare output filename
        base_name, ext = os.path.splitext(filename)
        cropped_filename = f"{base_name}_obituary_area{ext}"
        
        # Create an in-memory ZIP with the cropped image
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            text_bytes = io.BytesIO()
            text_image.save(text_bytes, format=image.format)
            zip_file.writestr(cropped_filename, text_bytes.getvalue())
        
        zip_buffer.seek(0)
        
        return {
            "zip_buffer": zip_buffer,
            "filename": f"{base_name}_obituary_cropped.zip",
            "body_dimensions": text_image.size
        }
