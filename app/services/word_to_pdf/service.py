import os
import tempfile
import shutil
import logging
from typing import Dict, Any
import comtypes.client

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WordToPdfService:
    """Service class for converting Word documents to PDF using COM interface"""
    
    @staticmethod
    def convert_docx_to_pdf(input_path, output_path=None):
        """
        Converts a Word DOCX file to PDF without altering layout, fonts, or headers.
        
        Parameters:
            input_path (str): Full path to the input DOCX file.
            output_path (str, optional): Full path for the output PDF. 
                                         If not provided, uses the same base name.
        
        Returns:
            str: Path to the generated PDF file.
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"The file '{input_path}' does not exist.")
        
        if not input_path.lower().endswith('.docx') and not input_path.lower().endswith('.doc'):
            raise ValueError("Input file must be a .docx or .doc Word document.")

        # Default output path if not specified
        if output_path is None:
            output_path = os.path.splitext(input_path)[0] + ".pdf"

        # Initialize Word application
        logger.info(f"Inicializando aplicación Word para convertir {input_path}")
        word = comtypes.client.CreateObject('Word.Application')
        word.Visible = False

        try:
            # Abrir el documento
            logger.info(f"Abriendo documento {input_path}")
            doc = word.Documents.Open(input_path)
            
            # Guardar como PDF (FileFormat=17 es PDF)
            logger.info(f"Guardando como PDF en {output_path}")
            doc.SaveAs(output_path, FileFormat=17)
            
            # Cerrar el documento
            doc.Close()
            
            logger.info(f"Conversión exitosa: {output_path}")
        except Exception as e:
            logger.error(f"Error durante la conversión: {str(e)}")
            raise e
        finally:
            # Cerrar Word
            word.Quit()

        if not os.path.exists(output_path):
            logger.error("La conversión a PDF falló, no se encontró el archivo de salida")
            raise RuntimeError("PDF conversion failed.")

        return output_path
    
    @staticmethod
    def convert_to_pdf(word_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Convierte un documento de Word a PDF usando la interfaz COM de Word
        
        Args:
            word_data: Bytes del documento Word
            filename: Nombre del archivo original
            
        Returns:
            Dictionary with PDF path and filename
        """
        # Crear un directorio temporal para trabajar
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Obtener el nombre base del archivo sin extensión
            base_name = os.path.splitext(filename)[0]
            
            # Definir rutas para los archivos
            word_path = os.path.join(temp_dir, filename)
            pdf_filename = f"{base_name}.pdf"
            pdf_path = os.path.join(temp_dir, pdf_filename)
            
            # Guardar el documento Word en el directorio temporal
            logger.info(f"Guardando documento Word en {word_path}")
            with open(word_path, "wb") as f:
                f.write(word_data)
            
            # Convertir a PDF usando comtypes
            logger.info("Iniciando conversión a PDF usando comtypes")
            output_pdf = WordToPdfService.convert_docx_to_pdf(word_path, pdf_path)
            
            logger.info(f"Conversión exitosa: {output_pdf}")
            
            return {
                "pdf_path": output_pdf,
                "filename": pdf_filename
            }
            
        except Exception as e:
            logger.error(f"Error en la conversión: {str(e)}")
            # Limpiar el directorio temporal en caso de error
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise e
