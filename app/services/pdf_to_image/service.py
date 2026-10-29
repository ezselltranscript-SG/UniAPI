import io
import os
import tempfile
import zipfile
from typing import List, Dict, Any, Optional
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image

from app.memory import release_memory

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
            
        # Las páginas de periódico a 200 DPI ocupan ~48 MB cada una sin comprimir.
        # Para no quedarnos sin memoria se renderiza una página a la vez a disco
        # (pdftoppm escribe el PPM, no se bufferiza su stdout) y el ZIP se arma en
        # un archivo temporal. En memoria solo queda una página a la vez.
        zip_file_obj = tempfile.TemporaryFile()
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                pdf_path = os.path.join(tmp_dir, "input.pdf")
                with open(pdf_path, "wb") as pdf_file:
                    pdf_file.write(pdf_bytes)

                try:
                    page_count = pdfinfo_from_path(pdf_path)["Pages"]
                except Exception as e:
                    raise Exception(f"Error al convertir PDF a imágenes: {str(e)}")

                with zipfile.ZipFile(zip_file_obj, "w") as zip_file:
                    for page in range(1, page_count + 1):
                        try:
                            page_paths = convert_from_path(
                                pdf_path,
                                output_folder=tmp_dir,
                                first_page=page,
                                last_page=page,
                                paths_only=True,
                            )
                        except Exception as e:
                            raise Exception(f"Error al convertir PDF a imágenes: {str(e)}")

                        for page_path in page_paths:
                            img_io = io.BytesIO()
                            with Image.open(page_path) as image:
                                image.save(img_io, format=format.upper())
                            os.remove(page_path)
                            zip_file.writestr(f"page_{page}.{format}", img_io.getvalue())

            zip_file_obj.seek(0)
        except Exception:
            zip_file_obj.close()
            raise
        finally:
            release_memory()

        return {
            "is_single_image": False,
            "content": zip_file_obj,
            "media_type": "application/zip",
            "filename": f"converted_images.zip",
            "page_count": page_count
        }
