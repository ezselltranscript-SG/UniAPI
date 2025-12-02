import os
import io
import shutil
import tempfile
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse

from .service import AnchoredPdfCropperService

router = APIRouter()

@router.get("/")
async def read_root():
    return {
        "message": "Anchored PDF Cropper Service",
        "endpoints": {
            "POST /crop/": "Detecta un ancla (texto/verde) y recorta la región objetivo en múltiples PDFs"
        },
        "parameters": {"files": "Lista de archivos PDF"},
        "notes": "El recorte es automático; no requiere parámetros. Usa OCR con palabras clave predefinidas y detección visual."
    }

@router.post("/crop/", summary="Auto crop anchored panel", operation_id="anchored_crop_auto")
async def crop_pdfs(files: List[UploadFile] = File(...)):
    # Validate inputs
    if not files:
        raise HTTPException(status_code=400, detail="Debes enviar al menos un PDF")
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"El archivo {f.filename} no es un PDF")

    # Read all files into memory (could be changed to streamed processing if needed)
    pdf_list = []
    for f in files:
        content = await f.read()
        pdf_list.append((content, f.filename))

    try:
        # Fully automatic: rely on service defaults
        result = AnchoredPdfCropperService.crop_pdfs(pdf_files=pdf_list)
        return StreamingResponse(
            content=result["buffer"],
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={result['filename']}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al recortar PDFs: {str(e)}")

