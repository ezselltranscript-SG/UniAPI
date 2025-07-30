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
        
        # Leer el archivo subido
        archive_data = await file.read()
        
        # Procesar el archivo con el servicio
        result = ColumnMergerService.merge_documents(
            archive_data=archive_data,
            output_filename=output_filename,
            temp_dir=temp_dir
        )
        
        # Copiar el archivo a un directorio temporal que no se eliminará inmediatamente
        output_file = result["output_file"]
        safe_temp_dir = tempfile.mkdtemp()
        safe_output_path = os.path.join(safe_temp_dir, f"{output_filename}.docx")
        shutil.copy2(output_file, safe_output_path)
        
        # Limpiar el directorio temporal original
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Definir una función para limpiar el directorio temporal después de enviar la respuesta
        def cleanup_temp_dir():
            shutil.rmtree(safe_temp_dir, ignore_errors=True)
        
        # Devolver el archivo resultante desde la ubicación segura
        return FileResponse(
            path=safe_output_path,
            filename=f"{output_filename}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            background=cleanup_temp_dir
        )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
