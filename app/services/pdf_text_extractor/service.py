import io
from typing import Dict, Any, Optional, List
from pdfminer.high_level import extract_text, extract_pages
from pdfminer.layout import LTTextContainer


class PDFTextExtractorService:
    """Servicio para extraer texto de archivos PDF."""
    
    @staticmethod
    def extract_text_from_pdf(pdf_bytes: bytes, return_by_page: bool = False) -> Dict[str, Any]:
        """
        Extrae texto de un archivo PDF.
        
        Args:
            pdf_bytes: Bytes del archivo PDF
            return_by_page: Si es True, devuelve el texto separado por páginas
            
        Returns:
            Diccionario con el texto extraído
        """
        try:
            # Crear buffer de entrada
            pdf_file = io.BytesIO(pdf_bytes)
            
            if return_by_page:
                # Extraer texto por páginas
                result = {}
                page_texts = []
                
                # Procesar cada página
                for page_num, page_layout in enumerate(extract_pages(pdf_file)):
                    texts = []
                    for element in page_layout:
                        if isinstance(element, LTTextContainer):
                            texts.append(element.get_text())
                    
                    page_text = "".join(texts)
                    page_texts.append(page_text)
                    result[f"page_{page_num + 1}"] = page_text
                
                # Añadir texto completo
                result["full_text"] = "\n\n".join(page_texts)
                
                return result
            else:
                # Extraer todo el texto de una vez
                text = extract_text(pdf_file)
                return {"text": text}
        except Exception as e:
            raise Exception(f"Error al extraer texto del PDF: {str(e)}")
    
    @staticmethod
    def extract_text_with_metadata(pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Extrae texto y metadatos básicos de un archivo PDF.
        
        Args:
            pdf_bytes: Bytes del archivo PDF
            
        Returns:
            Diccionario con el texto extraído y metadatos
        """
        try:
            # Extraer texto básico
            result = PDFTextExtractorService.extract_text_from_pdf(pdf_bytes, return_by_page=True)
            
            # Contar páginas
            num_pages = len([k for k in result.keys() if k.startswith("page_")])
            
            # Calcular estadísticas básicas
            full_text = result.get("full_text", "")
            word_count = len(full_text.split())
            char_count = len(full_text)
            
            # Añadir metadatos
            result["metadata"] = {
                "num_pages": num_pages,
                "word_count": word_count,
                "character_count": char_count
            }
            
            return result
        except Exception as e:
            raise Exception(f"Error al extraer texto y metadatos del PDF: {str(e)}")
