import os
import tempfile
import shutil
from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse
from typing import List, Optional

from app.config import DOWNLOADS_DIR
from .service import WordToPdfService
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router for Word to PDF service
router = APIRouter()

@router.get("/")
async def read_root():
    """Welcome endpoint for Word to PDF service"""
    return {
        "message": "Word to PDF Conversion Service",
        "endpoints": {
            "POST /convert/": "Convierte un documento Word a PDF con encabezados personalizados",
        },
        "parameters": {
            "file": "Documento Word (.docx o .doc)"
        },
        "features": [
            "Eliminación de encabezados existentes",
            "Estandarización de fuentes a Times New Roman 10pt",
            "Adición de encabezados personalizados con formato base_code_PartX"
        ]
    }

@router.post("/convert/", summary="Convertir documento Word a PDF")
async def convert_to_pdf(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """
    Convierte un documento Word a PDF con modificación de encabezados
    
    - **file**: Documento Word (.docx o .doc)
    
    Returns el documento convertido a PDF con encabezados personalizados
    """
    # Validar tipo de archivo
    if not file.filename:
        raise HTTPException(status_code=400, detail="No se proporcionó ningún archivo")
    
    if not file.filename.lower().endswith(('.docx', '.doc')):
        raise HTTPException(status_code=400, detail="El archivo debe ser un documento Word (.docx o .doc)")
    
    try:
        logger.info(f"Iniciando conversión de {file.filename}")
        # Leer el documento Word
        word_data = await file.read()
        
        # Usar el servicio para convertir el documento con las nuevas funcionalidades
        word_to_pdf_service = WordToPdfService()
        result = word_to_pdf_service.convert_to_pdf(
            word_data=word_data,
            filename=file.filename
        )
        
        # Crear una copia del PDF en una ubicación más persistente
        persistent_pdf = os.path.join(DOWNLOADS_DIR, result["filename"])
        shutil.copy2(result["pdf_path"], persistent_pdf)
        logger.info(f"PDF guardado en ubicación persistente: {persistent_pdf}")
        
        # Limpiar archivos temporales en segundo plano
        if background_tasks:
            def cleanup():
                temp_dir = os.path.dirname(result["pdf_path"])
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.info(f"Directorio temporal eliminado: {temp_dir}")
                except Exception as e:
                    logger.error(f"Error al eliminar directorio temporal {temp_dir}: {str(e)}")
            
            background_tasks.add_task(cleanup)
        else:
            # Limpiar archivos temporales inmediatamente si no hay tareas en segundo plano
            temp_dir = os.path.dirname(result["pdf_path"])
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Devolver el archivo PDF
        return FileResponse(
            path=persistent_pdf,
            media_type="application/pdf",
            filename=result["filename"]
        )
        
    except Exception as e:
        logger.error(f"Error al convertir el documento: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al convertir el documento: {str(e)}")

@router.get("/health")
async def health_check():
    """Endpoint para verificar el estado del servicio"""
    return {"status": "OK"}
