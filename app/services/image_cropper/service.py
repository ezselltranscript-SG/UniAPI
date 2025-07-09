from PIL import Image
import io
import zipfile
import os
from typing import Optional, Tuple, Dict, Any

class ImageCropperService:
    """Service class for image cropping operations"""
    
    @staticmethod
    def crop_image(
        image_data: bytes,
        filename: str,
        split_point: Optional[int] = None,
        split_percentage: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Divide una imagen en dos partes: header (arriba) y body (abajo)
        
        Args:
            image_data: Bytes de la imagen
            filename: Nombre del archivo original
            split_point: Punto de división en píxeles desde arriba (opcional)
            split_percentage: Punto de división como porcentaje de la altura (0.0-1.0, opcional)
            
        Returns:
            Dictionary with ZIP buffer and filename
        """
        # Abrir la imagen desde los bytes
        image = Image.open(io.BytesIO(image_data))
        
        # Obtener dimensiones
        width, height = image.size
        
        # Determinar punto de división
        if split_point is not None:
            division_y = split_point
        elif split_percentage is not None:
            division_y = int(height * split_percentage)
        else:
            # Por defecto, dividir por la mitad
            division_y = height // 2
        
        # Crear las dos partes
        # Header: desde arriba hasta el punto de división
        image_header = image.crop((0, 0, width, division_y))
        
        # Body: desde el punto de división hasta abajo
        image_body = image.crop((0, division_y, width, height))
        
        # Determinar formato
        format_name = 'PNG' if filename.lower().endswith('.png') else 'JPEG'
        extension = 'png' if format_name == 'PNG' else 'jpg'
        
        # Crear ZIP en memoria
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Guardar image_header
            header_buffer = io.BytesIO()
            image_header.save(header_buffer, format=format_name)
            zip_file.writestr(f"image_header.{extension}", header_buffer.getvalue())
            
            # Guardar image_body
            body_buffer = io.BytesIO()
            image_body.save(body_buffer, format=format_name)
            zip_file.writestr(f"image_body.{extension}", body_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Crear nombre del archivo ZIP
        original_name = os.path.splitext(filename)[0] if filename else "image"
        zip_filename = f"{original_name}_cropped.zip"
        
        return {
            "buffer": zip_buffer,
            "filename": zip_filename
        }
