from PIL import Image
import io
import zipfile
import os
from typing import Dict, Any

class ShowerCropperService:
    """
    Service for cropping forms: extracts only the fixed-position handwritten/text area
    based on visual layout measurements for different form types.
    """

    @staticmethod
    def crop_fixed_area(image_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Crops the image to a fixed area where the handwritten content typically appears
        in the Ivverich und Ender shower form.

        Args:
            image_data: Raw bytes of the image file
            filename: Original filename

        Returns:
            Dictionary with a ZIP buffer containing the cropped image and metadata
        """
        # Load the image
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        print(f"Original image size: {width}x{height} pixels")
        
        # Fixed crop boundaries based on visual inspection of Ivverich und Ender form layout
        # Crop from just below the header to just above the sender information
        top = int(height * 0.35)     # ~35% from top (below header)
        bottom = int(height * 0.82)  # ~82% from top (above sender info)
        text_box = (0, top, width, bottom)
        
        print(f"Cropping shower form text area: {text_box}")
        
        # Crop the image
        text_image = image.crop(text_box)
        
        # Prepare output filename
        base_name, ext = os.path.splitext(filename)
        
        # Create a ZIP file with the processed image
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            # Save the cropped image
            cropped_filename = f"{base_name}_text_area{ext}"
            text_bytes = io.BytesIO()
            text_image.save(text_bytes, format=image.format)
            zip_file.writestr(cropped_filename, text_bytes.getvalue())

        zip_buffer.seek(0)
        return {
            "zip_buffer": zip_buffer,
            "filename": f"{base_name}_processed.zip",
            "body_dimensions": text_image.size
        }
        
    @staticmethod
    def crop_fixed_area_obituaries(image_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Crops the image to a fixed area optimized for obituaries layout.
        Specifically targets the handwritten content area in the Obituary & In Memoriam form.

        Args:
            image_data: Raw bytes of the image file
            filename: Original filename

        Returns:
            Dictionary with a ZIP buffer containing the cropped image and metadata
        """
        # Load the image
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        print(f"Original image size: {width}x{height} pixels")
        
        # Fixed crop boundaries based on visual inspection of obituary form layout
        # Crop from just below the header to just above the sender information
        top = int(height * 0.25)     # ~25% from top (below header)
        bottom = int(height * 0.81)  # ~81% from top (above sender info)
        text_box = (0, top, width, bottom)
        
        print(f"Cropping obituary form text area: {text_box}")
        
        # Crop the image
        text_image = image.crop(text_box)
        
        # Prepare output filename
        base_name, ext = os.path.splitext(filename)
        
        # Create a ZIP file with the processed image
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            # Save the cropped image
            cropped_filename = f"{base_name}_text_area{ext}"
            text_bytes = io.BytesIO()
            text_image.save(text_bytes, format=image.format)
            zip_file.writestr(cropped_filename, text_bytes.getvalue())

        zip_buffer.seek(0)
        return {
            "zip_buffer": zip_buffer,
            "filename": f"{base_name}_processed.zip",
            "body_dimensions": text_image.size
        }
        

