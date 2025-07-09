import os
import shutil
import tempfile
from typing import Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import FileResponse

from app.config import DOWNLOADS_DIR
from .service import FileMergerService

# Create router for File Merger service
router = APIRouter()

@router.get("/")
async def read_root():
    """Welcome endpoint for File Merger service"""
    return {
        "message": "File Merger Service",
        "endpoints": {
            "POST /merge/": "Fusiona archivos PDF o DOCX de un archivo comprimido",
        },
        "parameters": {
            "file": "Archivo comprimido (ZIP, RAR, etc.) que contiene archivos PDF o DOCX",
            "output_filename": "Nombre para el archivo de salida (opcional)"
        },
        "notes": "Los archivos se ordenarán por número de parte si tienen 'partX' en el nombre"
    }

@router.post("/merge/", summary="Fusionar archivos PDF o DOCX")
async def merge_files(
    file: Optional[UploadFile] = File(None),
    data: Optional[UploadFile] = File(None),
    archive: Optional[UploadFile] = File(None),
    output_filename: Optional[str] = Form("merged_document"),
    request: Request = None
):
    """
    Fusiona múltiples archivos PDF o DOCX contenidos en un archivo comprimido
    
    - **file/data/archive**: Archivo comprimido (ZIP, RAR, etc.) con archivos PDF o DOCX
    - **output_filename**: Nombre para el archivo de salida (opcional)
    
    Los archivos se ordenarán por número de parte si tienen 'partX' en el nombre.
    Todos los archivos deben ser del mismo tipo (PDF o DOCX).
    """
    # Determinar cuál campo contiene el archivo
    actual_file = file or data or archive
    if not actual_file:
        form = await request.form()
        for value in form.values():
            if isinstance(value, UploadFile):
                actual_file = value
                break
    
    if not actual_file:
        raise HTTPException(status_code=400, detail="No se proporcionó ningún archivo.")
    
    try:
        # Crear un directorio temporal para procesar los archivos
        with tempfile.TemporaryDirectory() as temp_dir:
            # Leer el archivo comprimido
            archive_data = await actual_file.read()
            
            # Usar el servicio para procesar y fusionar los archivos
            file_merger = FileMergerService()
            result = file_merger.merge_files(
                archive_data=archive_data,
                output_filename=output_filename,
                temp_dir=temp_dir
            )
            
            # Crear una copia del archivo en una ubicación más persistente
            persistent_file = os.path.join(DOWNLOADS_DIR, result["filename"])
            shutil.copy2(result["output_path"], persistent_file)
            
            # Devolver el archivo fusionado
            return FileResponse(
                path=persistent_file,
                media_type=result["media_type"],
                filename=result["filename"]
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al fusionar archivos: {str(e)}")

@router.get("/health")
async def health_check():
    """Endpoint para verificar el estado del servicio"""
    return {"status": "OK"}
