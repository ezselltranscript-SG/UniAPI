from PIL import Image
import io
import zipfile
import os
from typing import Dict, Any, Tuple

class FixedImageCropperService:
    """Service class for fixed dimension image cropping operations"""
    
    @staticmethod
    def crop_image_fixed_NT(image_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Divide una imagen en dos partes: header y body con dimensiones fijas predefinidas
        
        Args:
            image_data: Bytes de la imagen
            filename: Nombre del archivo original
            
        Returns:
            Dictionary with ZIP buffer and filename
        """
        # Abrir la imagen desde los bytes
        image = Image.open(io.BytesIO(image_data))
        
        # Obtener dimensiones
        width, height = image.size
        print(f"Imagen original: {width}x{height} píxeles")
        
        # Definir las coordenadas de recorte fijas (basadas en porcentajes)
        header_box = (0, int(height * 0.02), width, int(height * 0.20))
        body_box = (0, int(height * 0.20), width, height)
        
        print(f"Recortando header: {header_box}")
        print(f"Recortando body: {body_box}")
        
        # Recortar las imágenes
        header_image = image.crop(header_box)
        body_image = image.crop(body_box)
        
        # Obtener el nombre base y la extensión
        base_name = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1]
        
        # Nombres para las partes recortadas
        header_filename = f"{base_name}_header{ext}"
        body_filename = f"{base_name}_body{ext}"
        
        # Crear un buffer ZIP en memoria
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            # Guardar header en el ZIP
            header_bytes = io.BytesIO()
            header_image.save(header_bytes, format=image.format)
            header_bytes.seek(0)
            zip_file.writestr(header_filename, header_bytes.getvalue())
            
            # Guardar body en el ZIP
            body_bytes = io.BytesIO()
            body_image.save(body_bytes, format=image.format)
            body_bytes.seek(0)
            zip_file.writestr(body_filename, body_bytes.getvalue())
        
        # Preparar el buffer para lectura
        zip_buffer.seek(0)
        
        # Devolver el buffer ZIP y el nombre del archivo
        return {
            "zip_buffer": zip_buffer,
            "filename": f"{base_name}_cropped.zip",
            "header_dimensions": header_image.size,
            "body_dimensions": body_image.size
        }
