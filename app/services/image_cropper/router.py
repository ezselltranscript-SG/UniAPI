from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import StreamingResponse
from typing import Optional
import io

from .service import ImageCropperService

# Create router for Image Cropper service
router = APIRouter()

@router.get("/")
async def read_root():
    """Welcome endpoint for Image Cropper service"""
    return {
        "message": "Image Cropping Service",
        "endpoints": {
            "POST /crop/": "Divide una imagen en header y body",
        },
        "parameters": {
            "file": "Imagen PNG o JPG (requerido)",
            "split_point": "Punto de división en píxeles desde arriba (opcional)",
            "split_percentage": "Punto de división como porcentaje 0.0-1.0 (opcional)"
        },
        "examples": {
            "split_by_pixels": "split_point=300 (divide a 300px desde arriba)",
            "split_by_percentage": "split_percentage=0.3 (divide al 30% de la altura)",
            "default": "Sin parámetros = divide por la mitad"
        }
    }

@router.post("/crop/", summary="Divide una imagen en dos partes")
async def crop_image(
    file: UploadFile = File(...),
    split_point: Optional[int] = Form(None),
    split_percentage: Optional[float] = Form(None)
):
    """
    Divide una imagen en dos partes: header (arriba) y body (abajo)
    
    Parámetros:
    - file: Imagen PNG o JPG
    - split_point: Punto de división en píxeles desde arriba (opcional)
    - split_percentage: Punto de división como porcentaje de la altura (0.0-1.0, opcional)
    
    Si no se especifica ningún punto, se divide por la mitad (50%)
    """
    
    # Validar tipo de archivo
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
    
    if file.content_type not in ['image/png', 'image/jpeg', 'image/jpg']:
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PNG y JPG")
    
    try:
        # Validar parámetros
        if split_point is not None and split_point < 0:
            raise HTTPException(
                status_code=400, 
                detail="El punto de división debe ser un valor positivo"
            )
        
        if split_percentage is not None and (split_percentage < 0.0 or split_percentage > 1.0):
            raise HTTPException(
                status_code=400, 
                detail="El porcentaje debe estar entre 0.0 y 1.0"
            )
        
        # Leer la imagen
        image_data = await file.read()
        
        # Usar el servicio para procesar la imagen
        image_cropper = ImageCropperService()
        result = image_cropper.crop_image(
            image_data=image_data,
            filename=file.filename,
            split_point=split_point,
            split_percentage=split_percentage
        )
        
        return StreamingResponse(
            io.BytesIO(result["buffer"].read()),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={result['filename']}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando la imagen: {str(e)}")

@router.get("/health")
async def health_check():
    """Endpoint para verificar el estado del servicio"""
    return {"status": "OK"}
