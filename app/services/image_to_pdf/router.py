from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
import io

from .service import ImageToPDFService

router = APIRouter(
    prefix="/image-to-pdf",
    tags=["Image to PDF Service"],
    responses={404: {"description": "Not found"}},
)


@router.post("/convert/")
async def convert_image_to_pdf(
    file: UploadFile = File(...),
    page_size: str = Query("A4", description="Tamaño de página (A4 o letter)")
):
    """
    Convierte una imagen a formato PDF.
    
    - **file**: Archivo de imagen (PNG, JPEG, etc.)
    - **page_size**: Tamaño de página (A4 o letter)
    """
    # Verificar tipo de archivo
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
    
    # Leer contenido del archivo
    file_content = await file.read()
    
    try:
        # Convertir imagen a PDF
        pdf_bytes = ImageToPDFService.convert_image_to_pdf(file_content, page_size=page_size)
        
        # Devolver el PDF como respuesta de streaming
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={file.filename.split('.')[0]}.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/convert-multiple/")
async def convert_multiple_images_to_pdf(
    files: List[UploadFile] = File(...),
    page_size: str = Query("A4", description="Tamaño de página (A4 o letter)")
):
    """
    Convierte múltiples imágenes a un único archivo PDF con múltiples páginas.
    
    - **files**: Lista de archivos de imagen (PNG, JPEG, etc.)
    - **page_size**: Tamaño de página (A4 o letter)
    """
    # Verificar que todos los archivos sean imágenes
    for file in files:
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"El archivo {file.filename} debe ser una imagen")
    
    try:
        # Leer contenido de todos los archivos
        image_bytes_list = []
        for file in files:
            file_content = await file.read()
            image_bytes_list.append(file_content)
        
        # Convertir imágenes a PDF
        pdf_bytes = ImageToPDFService.convert_multiple_images_to_pdf(image_bytes_list, page_size=page_size)
        
        # Devolver el PDF como respuesta de streaming
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=combined_images.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
