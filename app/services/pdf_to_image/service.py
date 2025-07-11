import io
import zipfile
from typing import List, Dict, Any, Optional
from pdf2image import convert_from_bytes
from PIL import Image

class PDFToImageService:
    """
    Servicio para convertir archivos PDF a imágenes (PNG, JPEG)
    """
    
    @staticmethod
    def convert_pdf_to_images(pdf_bytes: bytes, format: str = "png") -> Dict[str, Any]:
        """
        Convierte un archivo PDF a imágenes
        
        Args:
            pdf_bytes: Bytes del archivo PDF
            format: Formato de salida de las imágenes (png, jpeg, jpg)
            
        Returns:
            Dict con información sobre la conversión y los bytes de la imagen o archivo ZIP
        """
        # Validar formato
        if format.lower() not in ["png", "jpeg", "jpg"]:
            raise ValueError("Formato no soportado. Usa png o jpeg.")
            
        # Normalizar formato
        if format.lower() == "jpg":
            format = "jpeg"
            
        # Convertir PDF a imágenes
        try:
            images = convert_from_bytes(pdf_bytes)
        except Exception as e:
            raise Exception(f"Error al convertir PDF a imágenes: {str(e)}")
            
        # Crear un archivo ZIP con todas las imágenes
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for i, image in enumerate(images):
                img_io = io.BytesIO()
                image.save(img_io, format=format.upper())
                img_io.seek(0)
                zip_file.writestr(f"page_{i+1}.{format}", img_io.getvalue())
                
        zip_buffer.seek(0)
        
        return {
            "is_single_image": False,
            "content": zip_buffer,
            "media_type": "application/zip",
            "filename": f"converted_images.zip",
            "page_count": len(images)
        }
