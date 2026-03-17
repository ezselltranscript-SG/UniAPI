from PIL import Image
import io
import zipfile
import os
from typing import Dict, Any


class FixedImageCropperTheBudgetService:
    """Service class for fixed dimension image cropping operations (The Budget template)"""

    @staticmethod
    def crop_image_fixed_the_budget(image_data: bytes, filename: str) -> Dict[str, Any]:
        """Divide una imagen en dos partes: header y body con dimensiones fijas predefinidas.

        This variant is tuned for scanned letter pages like the sample provided:
        - First trims outer page borders (top/bottom/left/right) using percentages.
        - Then splits into header/body regions.

        Args:
            image_data: Bytes de la imagen
            filename: Nombre del archivo original

        Returns:
            Dictionary with ZIP buffer and filename
        """
        image = Image.open(io.BytesIO(image_data))

        width, height = image.size
        print(f"Imagen original: {width}x{height} píxeles")

        # Step 1: trim page borders to remove scanner margins / frame.
        # These percentages are intentionally conservative; adjust if needed.
        left = int(width * 0.04)
        right = int(width * 0.96)
        top = int(height * 0.00)
        bottom = int(height * 0.97)
        page_box = (left, top, right, bottom)

        print(f"Recortando página (bordes): {page_box}")
        page_image = image.crop(page_box)

        p_width, p_height = page_image.size
        print(f"Imagen sin bordes: {p_width}x{p_height} píxeles")

        # Step 2: split header/body in the trimmed page.
        # Header contains the letterhead area; body is the handwritten content.
        header_box = (0, int(p_height * 0.00), p_width, int(p_height * 0.27))
        body_box = (0, int(p_height * 0.27), p_width, p_height)

        print(f"Recortando header: {header_box}")
        print(f"Recortando body: {body_box}")

        header_image = page_image.crop(header_box)
        body_image = page_image.crop(body_box)

        base_name = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1]

        header_filename = f"{base_name}_header{ext}"
        body_filename = f"{base_name}_body{ext}"

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            header_bytes = io.BytesIO()
            header_image.save(header_bytes, format=image.format)
            header_bytes.seek(0)
            zip_file.writestr(header_filename, header_bytes.getvalue())

            body_bytes = io.BytesIO()
            body_image.save(body_bytes, format=image.format)
            body_bytes.seek(0)
            zip_file.writestr(body_filename, body_bytes.getvalue())

        zip_buffer.seek(0)

        return {
            "zip_buffer": zip_buffer,
            "filename": f"{base_name}_cropped.zip",
            "header_dimensions": header_image.size,
            "body_dimensions": body_image.size,
        }
