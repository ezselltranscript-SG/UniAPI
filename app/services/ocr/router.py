from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional

from .service import OCRService

router = APIRouter(
    prefix="/ocr",
    tags=["OCR Service"],
    responses={404: {"description": "Not found"}},
)


@router.post("/image/")
async def ocr_image(
    file: UploadFile = File(...),
    lang: str = Query("spa", description="Idioma para OCR (spa, eng, etc)")
):
    """
    Realiza OCR en una imagen y devuelve el texto extraído.
    
    - **file**: Archivo de imagen (PNG, JPEG, etc.)
    - **lang**: Idioma para OCR (por defecto español 'spa')
    """
    # Verificar tipo de archivo
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
    
    # Leer contenido del archivo
    file_content = await file.read()
    
    try:
        # Realizar OCR
        text = OCRService.perform_ocr_on_image(file_content, lang=lang)
        
        # Devolver resultado
        return JSONResponse(content={"text": text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pdf/")
async def ocr_pdf(
    file: UploadFile = File(...),
    lang: str = Query("spa", description="Idioma para OCR (spa, eng, etc)"),
    pages_only: bool = Query(False, description="Devolver solo el texto por páginas sin texto completo")
):
    """
    Realiza OCR en un archivo PDF y devuelve el texto extraído.
    
    - **file**: Archivo PDF
    - **lang**: Idioma para OCR (por defecto español 'spa')
    - **pages_only**: Si es True, devuelve solo el texto por páginas sin el texto completo
    """
    # Verificar tipo de archivo
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")
    
    # Leer contenido del archivo
    file_content = await file.read()
    
    try:
        # Realizar OCR
        result = OCRService.perform_ocr_on_pdf(file_content, lang=lang)
        
        # Filtrar resultado si es necesario
        if pages_only:
            # Eliminar el texto completo
            if "full_text" in result:
                del result["full_text"]
        
        # Devolver resultado
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
