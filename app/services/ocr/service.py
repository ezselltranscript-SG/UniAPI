import io
import os
import tempfile
from typing import Dict, Any, Optional

import pytesseract
from PIL import Image
from pdf2image import convert_from_bytes


class OCRService:
    """Servicio para realizar reconocimiento óptico de caracteres (OCR) en imágenes y PDFs."""
    
    @staticmethod
    def perform_ocr_on_image(image_bytes: bytes, lang: str = "spa") -> str:
        """
        Realiza OCR en una imagen.
        
        Args:
            image_bytes: Bytes de la imagen
            lang: Idioma para OCR (por defecto español)
            
        Returns:
            Texto extraído de la imagen
        """
        try:
            # Cargar imagen desde bytes
            image = Image.open(io.BytesIO(image_bytes))
            
            # Realizar OCR
            text = pytesseract.image_to_string(image, lang=lang)
            
            return text
        except Exception as e:
            raise Exception(f"Error al realizar OCR en la imagen: {str(e)}")
    
    @staticmethod
    def perform_ocr_on_pdf(pdf_bytes: bytes, lang: str = "spa") -> Dict[str, Any]:
        """
        Realiza OCR en un archivo PDF.
        
        Args:
            pdf_bytes: Bytes del archivo PDF
            lang: Idioma para OCR (por defecto español)
            
        Returns:
            Diccionario con el texto extraído por página
        """
        try:
            # Convertir PDF a imágenes
            with tempfile.TemporaryDirectory() as temp_dir:
                images = convert_from_bytes(pdf_bytes, output_folder=temp_dir)
                
                # Realizar OCR en cada página
                result = {}
                for i, image in enumerate(images):
                    # Guardar imagen temporalmente
                    temp_img_path = os.path.join(temp_dir, f"page_{i+1}.png")
                    image.save(temp_img_path, "PNG")
                    
                    # Realizar OCR
                    with open(temp_img_path, "rb") as img_file:
                        page_text = pytesseract.image_to_string(Image.open(img_file), lang=lang)
                        result[f"page_{i+1}"] = page_text
                
                # Texto completo combinado
                full_text = "\n\n".join([text for text in result.values()])
                result["full_text"] = full_text
                
                return result
        except Exception as e:
            raise Exception(f"Error al realizar OCR en el PDF: {str(e)}")
