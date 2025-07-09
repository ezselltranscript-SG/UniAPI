import os
import tempfile
import shutil
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Query
from fastapi.responses import StreamingResponse
from typing import Optional

from app.config import DOWNLOADS_DIR
from .service import PDFToImageService

# Configurar router para el servicio PDF to Image
router = APIRouter()

@router.get("/")
async def read_root():
    """Endpoint de bienvenida para el servicio PDF to Image"""
    return {
        "message": "PDF to Image Conversion Service",
        "endpoints": {
            "POST /convert/": "Convierte un archivo PDF a imágenes (PNG o JPEG)"
        },
        "parameters": {
            "file": "Archivo PDF",
            "format": "Formato de salida (png, jpeg, jpg). Por defecto: png"
        }
    }

@router.post("/convert/", summary="Convertir PDF a imágenes")
async def convert_pdf(
    file: UploadFile = File(...),
    format: str = Query("png", description="Formato de salida (png, jpeg, jpg)")
):
    """
    Convierte un archivo PDF a imágenes
    
    - **file**: Archivo PDF
    - **format**: Formato de salida (png, jpeg, jpg). Por defecto: png
    
    Returns:
    - Si el PDF tiene una sola página: la imagen convertida
    - Si el PDF tiene múltiples páginas: un archivo ZIP con todas las imágenes
    """
    # Validar tipo de archivo
    if not file.filename:
        raise HTTPException(status_code=400, detail="No se proporcionó ningún archivo")
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")
    
    # Validar formato
    if format.lower() not in ["png", "jpeg", "jpg"]:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa png o jpeg.")
    
    try:
        # Leer el archivo PDF
        pdf_bytes = await file.read()
        
        # Usar el servicio para convertir el PDF a imágenes
        pdf_to_image_service = PDFToImageService()
        result = pdf_to_image_service.convert_pdf_to_images(
            pdf_bytes=pdf_bytes,
            format=format
        )
        
        # Devolver el resultado
        return StreamingResponse(
            content=result["content"],
            media_type=result["media_type"],
            headers={
                "Content-Disposition": f"attachment; filename={result['filename']}"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al convertir el PDF: {str(e)}")

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "pdf-to-image"}
