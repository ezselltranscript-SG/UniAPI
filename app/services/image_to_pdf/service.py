import io
from typing import Dict, Any, List, Union
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4


class ImageToPDFService:
    """Servicio para convertir imágenes a formato PDF."""
    
    @staticmethod
    def convert_image_to_pdf(image_bytes: bytes, page_size: str = "A4") -> bytes:
        """
        Convierte una imagen a formato PDF.
        
        Args:
            image_bytes: Bytes de la imagen
            page_size: Tamaño de página ("A4" o "letter")
            
        Returns:
            Bytes del archivo PDF generado
        """
        try:
            # Determinar tamaño de página
            page_size_map = {
                "A4": A4,
                "letter": letter
            }
            pdf_page_size = page_size_map.get(page_size.upper(), A4)
            
            # Cargar imagen desde bytes
            image = Image.open(io.BytesIO(image_bytes))
            
            # Crear buffer para el PDF
            pdf_buffer = io.BytesIO()
            
            # Crear PDF
            pdf = canvas.Canvas(pdf_buffer, pagesize=pdf_page_size)
            
            # Obtener dimensiones de la página
            width, height = pdf_page_size
            
            # Calcular dimensiones para ajustar la imagen a la página
            img_width, img_height = image.size
            aspect = img_width / float(img_height)
            
            # Ajustar imagen para que quepa en la página con márgenes
            margin = 50  # margen en puntos
            max_width = width - 2 * margin
            max_height = height - 2 * margin
            
            if img_width / max_width > img_height / max_height:
                # Limitado por ancho
                new_width = max_width
                new_height = new_width / aspect
            else:
                # Limitado por alto
                new_height = max_height
                new_width = new_height * aspect
            
            # Calcular posición para centrar la imagen
            x = (width - new_width) / 2
            y = (height - new_height) / 2
            
            # Dibujar imagen en el PDF
            pdf.drawImage(io.BytesIO(image_bytes), x, y, width=new_width, height=new_height)
            
            # Finalizar PDF
            pdf.save()
            
            # Obtener bytes del PDF
            pdf_bytes = pdf_buffer.getvalue()
            pdf_buffer.close()
            
            return pdf_bytes
        except Exception as e:
            raise Exception(f"Error al convertir imagen a PDF: {str(e)}")
    
    @staticmethod
    def convert_multiple_images_to_pdf(image_bytes_list: List[bytes], page_size: str = "A4") -> bytes:
        """
        Convierte múltiples imágenes a un único archivo PDF con múltiples páginas.
        
        Args:
            image_bytes_list: Lista de bytes de imágenes
            page_size: Tamaño de página ("A4" o "letter")
            
        Returns:
            Bytes del archivo PDF generado
        """
        try:
            # Determinar tamaño de página
            page_size_map = {
                "A4": A4,
                "letter": letter
            }
            pdf_page_size = page_size_map.get(page_size.upper(), A4)
            
            # Crear buffer para el PDF
            pdf_buffer = io.BytesIO()
            
            # Crear PDF
            pdf = canvas.Canvas(pdf_buffer, pagesize=pdf_page_size)
            
            # Obtener dimensiones de la página
            width, height = pdf_page_size
            
            # Procesar cada imagen
            for img_bytes in image_bytes_list:
                # Cargar imagen desde bytes
                image = Image.open(io.BytesIO(img_bytes))
                
                # Calcular dimensiones para ajustar la imagen a la página
                img_width, img_height = image.size
                aspect = img_width / float(img_height)
                
                # Ajustar imagen para que quepa en la página con márgenes
                margin = 50  # margen en puntos
                max_width = width - 2 * margin
                max_height = height - 2 * margin
                
                if img_width / max_width > img_height / max_height:
                    # Limitado por ancho
                    new_width = max_width
                    new_height = new_width / aspect
                else:
                    # Limitado por alto
                    new_height = max_height
                    new_width = new_height * aspect
                
                # Calcular posición para centrar la imagen
                x = (width - new_width) / 2
                y = (height - new_height) / 2
                
                # Dibujar imagen en el PDF
                pdf.drawImage(io.BytesIO(img_bytes), x, y, width=new_width, height=new_height)
                
                # Añadir nueva página para la siguiente imagen
                pdf.showPage()
            
            # Finalizar PDF
            pdf.save()
            
            # Obtener bytes del PDF
            pdf_bytes = pdf_buffer.getvalue()
            pdf_buffer.close()
            
            return pdf_bytes
        except Exception as e:
            raise Exception(f"Error al convertir imágenes a PDF: {str(e)}")
