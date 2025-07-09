import os
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from app.config import DOWNLOADS_DIR
from .service import FixedImageCropperService

# Create router for Fixed Image Cropper service
router = APIRouter()

@router.get("/")
def read_root():
    """Welcome endpoint for Fixed Image Cropper service"""
    return {
        "message": "Welcome to Fixed Image Cropper Service. Use /crop-fixed/ endpoint to upload and crop images with predefined dimensions.",
        "description": "This service crops images into header (12%-30% of height) and body (31%-100% of height) parts."
    }


@router.post("/crop-fixed/", summary="Crop image with predefined dimensions")
async def crop_image_fixed(
    image_file: Annotated[UploadFile, File(description="Image file to crop")]
):
    """Crop an image into two parts (header and body) using predefined dimensions.
    
    - **image_file**: The image file to crop (PNG, JPG, JPEG)
    
    The image will be cropped into:
    - Header: from 12% to 30% of the image height
    - Body: from 31% to 100% of the image height
    
    Returns a ZIP file containing both cropped parts.
    """
    try:
        # Validate file type
        if not image_file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        valid_extensions = ['.png', '.jpg', '.jpeg']
        file_ext = os.path.splitext(image_file.filename.lower())[1]
        if file_ext not in valid_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file format. Supported formats: {', '.join(valid_extensions)}"
            )
        
        # Read the image file
        content = await image_file.read()
        
        # Process the image using the service
        try:
            result = FixedImageCropperService.crop_image_fixed(content, image_file.filename)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")
        
        # Return the ZIP file as a streaming response
        return StreamingResponse(
            result["zip_buffer"],
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={result['filename']}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/health")
async def health_check():
    """Endpoint para verificar el estado del servicio"""
    return {"status": "OK", "service": "Fixed Image Cropper"}
