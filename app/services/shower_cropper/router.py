import os
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from app.config import DOWNLOADS_DIR
from .service import ShowerCropperService

# Create router for Shower Cropper service
router = APIRouter()

@router.get("/")
def read_root():
    """Welcome endpoint for Shower Cropper service"""
    return {
        "message": "Welcome to Shower Cropper Service. Use /crop-shower/ endpoint to upload and crop images with automatic text area detection.",
        "description": "This service automatically detects and crops the handwritten or filled-in area of a form."
    }


@router.post("/crop-shower/", summary="Crop image to handwritten/filled-in area")
async def crop_to_written_area(
    image_file: Annotated[UploadFile, File(description="Image file to crop")]
):
    """Crop an image to the dynamically-detected handwritten or filled-in area.
    
    - **image_file**: The image file to crop (PNG, JPG, JPEG)
    
    The image will be analyzed to detect the area with handwritten or filled-in content,
    and only that area will be extracted.
    
    Returns a ZIP file containing the cropped part.
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
            result = ShowerCropperService.crop_to_written_area(content, image_file.filename)
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
    return {"status": "OK", "service": "Shower Cropper"}
