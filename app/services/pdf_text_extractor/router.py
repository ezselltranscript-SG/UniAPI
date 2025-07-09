from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional

from .service import PDFTextExtractorService

router = APIRouter(
    prefix="/pdf-text-extractor",
    tags=["PDF Text Extractor Service"],
    responses={404: {"description": "Not found"}},
)


@router.post("/extract/")
async def extract_text_from_pdf(
    file: UploadFile = File(...),
    by_page: bool = Query(False, description="Devolver texto separado por páginas")
):
    """
    Extrae texto de un archivo PDF.
    
    - **file**: Archivo PDF
    - **by_page**: Si es True, devuelve el texto separado por páginas
    """
    # Verificar tipo de archivo
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")
    
    # Leer contenido del archivo
    file_content = await file.read()
    
    try:
        # Extraer texto
        result = PDFTextExtractorService.extract_text_from_pdf(file_content, return_by_page=by_page)
        
        # Devolver resultado
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-with-metadata/")
async def extract_text_with_metadata(
    file: UploadFile = File(...)
):
    """
    Extrae texto y metadatos básicos de un archivo PDF.
    
    - **file**: Archivo PDF
    """
    # Verificar tipo de archivo
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")
    
    # Leer contenido del archivo
    file_content = await file.read()
    
    try:
        # Extraer texto y metadatos
        result = PDFTextExtractorService.extract_text_with_metadata(file_content)
        
        # Devolver resultado
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-to-file/")
async def extract_text_to_file(
    file: UploadFile = File(...),
    format: str = Query("txt", description="Formato de salida (txt)")
):
    """
    Extrae texto de un archivo PDF y lo devuelve como un archivo de texto.
    
    - **file**: Archivo PDF
    - **format**: Formato de salida (actualmente solo se admite 'txt')
    """
    # Verificar tipo de archivo
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")
    
    # Verificar formato solicitado
    if format.lower() != "txt":
        raise HTTPException(status_code=400, detail="Formato no soportado. Actualmente solo se admite 'txt'")
    
    # Leer contenido del archivo
    file_content = await file.read()
    
    try:
        # Extraer texto
        result = PDFTextExtractorService.extract_text_from_pdf(file_content, return_by_page=False)
        text = result.get("text", "")
        
        # Devolver como archivo de texto
        return JSONResponse(
            content={"text": text},
            headers={"Content-Disposition": f"attachment; filename={file.filename.split('.')[0]}.txt"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
