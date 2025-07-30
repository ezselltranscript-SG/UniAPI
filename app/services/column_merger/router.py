import os
import shutil
import tempfile
from typing import Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import FileResponse

from app.config import DOWNLOADS_DIR
from .service import ColumnMergerService

# Create router for Column Merger service
router = APIRouter()

@router.get("/")
async def read_root():
    """Welcome endpoint for Column Merger service"""
    return {
        "message": "Column Merger Service",
        "endpoints": {
            "POST /merge/obituaries/": "Fusiona archivos de texto en formato de columnas para obituarios",
            "POST /merge/showers/": "Fusiona archivos de texto en formato de columnas para anuncios de shower",
        },
        "parameters": {
            "file": "Archivo comprimido (ZIP, RAR, etc.) que contiene archivos de texto",
            "output_filename": "Nombre para el archivo de salida (opcional)",
            "date": "Fecha para mostrar en el encabezado (opcional, formato: 'Month DD')"
        },
        "notes": "Los archivos se ordenarán por número de parte si tienen 'partX' en el nombre"
    }

@router.post("/merge/obituaries/", summary="Fusionar archivos de texto en formato de columnas para obituarios")
async def merge_obituaries(
    file: Optional[UploadFile] = File(None),
    data: Optional[UploadFile] = File(None),
    archive: Optional[UploadFile] = File(None),
    output_filename: Optional[str] = Form("merged_obituaries"),
    date: Optional[str] = Form(None),
    request: Request = None
):
    """
    Fusiona múltiples archivos de texto en formato de columnas para obituarios
    
    - **file/data/archive**: Archivo comprimido (ZIP, RAR, etc.) con archivos de texto
    - **output_filename**: Nombre para el archivo de salida (opcional)
    - **date**: Fecha para mostrar en el encabezado (opcional, formato: 'Month DD')
    
    Los archivos se ordenarán por número de parte si tienen 'partX' en el nombre.
    """
    return await merge_files_in_columns(
        file=file, 
        data=data, 
        archive=archive, 
        output_filename=output_filename, 
        date=date, 
        document_type="OBITUARIES", 
        request=request
    )

@router.post("/merge/showers/", summary="Fusionar archivos de texto en formato de columnas para showers")
async def merge_showers(
    file: Optional[UploadFile] = File(None),
    data: Optional[UploadFile] = File(None),
    archive: Optional[UploadFile] = File(None),
    output_filename: Optional[str] = Form("merged_showers"),
    date: Optional[str] = Form(None),
    request: Request = None
):
    """
    Fusiona múltiples archivos de texto en formato de columnas para anuncios de shower
    
    - **file/data/archive**: Archivo comprimido (ZIP, RAR, etc.) con archivos de texto
    - **output_filename**: Nombre para el archivo de salida (opcional)
    - **date**: Fecha para mostrar en el encabezado (opcional, formato: 'Month DD')
    
    Los archivos se ordenarán por número de parte si tienen 'partX' en el nombre.
    """
    return await merge_files_in_columns(
        file=file, 
        data=data, 
        archive=archive, 
        output_filename=output_filename, 
        date=date, 
        document_type="SHOWERS", 
        request=request
    )

async def merge_files_in_columns(
    file: Optional[UploadFile] = None,
    data: Optional[UploadFile] = None,
    archive: Optional[UploadFile] = None,
    output_filename: str = "merged_document",
    date: Optional[str] = None,
    document_type: str = "OBITUARIES",
    request: Request = None
):
    """
    Función auxiliar para fusionar archivos en formato de columnas
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
            column_merger = ColumnMergerService()
            result = column_merger.merge_files_in_columns(
                archive_data=archive_data,
                output_filename=output_filename,
                temp_dir=temp_dir,
                document_type=document_type,
                date=date
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
