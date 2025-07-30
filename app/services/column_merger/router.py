import os
import shutil
import tempfile
from typing import Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse

from .service import ColumnMergerService

# Create router for Column Merger service
router = APIRouter()

@router.get("/health")
async def health_check():
    """Health check endpoint for the column merger service"""
    return {"status": "ok", "service": "column_merger"}

@router.get("/")
async def read_root():
    """Welcome endpoint for Column Merger service"""
    return {
        "message": "Column Merger Service",
        "endpoints": {
            "POST /merge-columns/": "Fusiona documentos Word manteniendo su formato original"
        },
        "parameters": {
            "file": "Archivo comprimido (ZIP, RAR, etc.) que contiene documentos Word",
            "output_filename": "Nombre para el archivo de salida (opcional)"
        },
        "notes": "Los archivos se ordenarán por número de parte si tienen 'partX' en el nombre"
    }

@router.post("/merge-columns/", summary="Fusionar documentos Word manteniendo formato")
async def merge_columns(
    file: UploadFile = File(...),
    output_filename: str = Form("merged_document")
):
    """
    Fusiona documentos Word de un archivo comprimido manteniendo el formato original
    
    - **file**: Archivo comprimido (ZIP, RAR, etc.) con documentos Word
    - **output_filename**: Nombre para el archivo de salida (opcional)
    
    Los archivos se ordenarán por número de parte si tienen 'partX' en el nombre.
    El resultado será un único documento Word con todas las páginas combinadas.
    """
    try:
        # Crear un directorio temporal para el procesamiento
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Leer el archivo subido
            archive_data = await file.read()
            
            # Procesar el archivo con el servicio
            result = ColumnMergerService.merge_documents(
                archive_data=archive_data,
                output_filename=output_filename,
                temp_dir=temp_dir
            )
            
            # Devolver el archivo resultante
            return FileResponse(
                path=result["output_file"],
                filename=f"{output_filename}.docx",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
        finally:
            # Limpiar el directorio temporal
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
