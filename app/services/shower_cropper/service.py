from PIL import Image
import io
import zipfile
import os
from typing import Dict, Any, Tuple
import numpy as np
import cv2

class ShowerCropperService:
    """Service for cropping shower-type forms: extracts only the handwritten or filled-in body area."""

    @staticmethod
    def detect_written_area(image: Image.Image) -> Tuple[int, int]:
        """
        Detects the vertical range (top, bottom) of the handwritten or filled-in area in the form.
        
        Args:
            image: PIL Image object
        
        Returns:
            Tuple with (top, bottom) pixel coordinates for cropping
        """
        # Convert PIL image to grayscale using OpenCV
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)

        # Binarize image to highlight dark text
        _, thresh = cv2.threshold(cv_image, 200, 255, cv2.THRESH_BINARY_INV)

        # Sum black pixels across each row
        hist = np.sum(thresh, axis=1)

        # Set threshold for meaningful content
        min_val = 50
        rows_with_text = np.where(hist > min_val)[0]

        if len(rows_with_text) == 0:
            return (0, image.height)  # fallback: full image if no content found

        top = rows_with_text[0]
        bottom = rows_with_text[-1]

        return (top, bottom)

    @staticmethod
    def crop_to_written_area(image_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Crops the image to the dynamically-detected body (text) area only.
        
        Args:
            image_data: Raw bytes of the image file
            filename: Original filename
            
        Returns:
            Dictionary with a ZIP buffer containing the cropped text area and metadata
        """
        # Load image
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        print(f"Original image size: {width}x{height} pixels")

        # Detect text region
        top, bottom = ShowerCropperService.detect_written_area(image)
        body_box = (0, top, width, bottom)
        print(f"Cropping text area: {body_box}")

        # Crop
        body_image = image.crop(body_box)

        # Prepare file naming
        base_name, ext = os.path.splitext(filename)
        body_filename = f"{base_name}_text_area{ext}"

        # Create in-memory ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            body_bytes = io.BytesIO()
            body_image.save(body_bytes, format=image.format)
            zip_file.writestr(body_filename, body_bytes.getvalue())

        zip_buffer.seek(0)

        return {
            "zip_buffer": zip_buffer,
            "filename": f"{base_name}_cropped.zip",
            "body_dimensions": body_image.size
        }
