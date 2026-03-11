import os
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from .service import FixedImageCropperTheBudgetService

# Create router for Fixed Image Cropper The Budget service
router = APIRouter()


@router.get("/")
def read_root():
    """Welcome endpoint for Fixed Image Cropper The Budget service"""
    return {
        "message": "Welcome to Fixed Image Cropper The Budget Service. Use /crop-fixed-the-budget/ endpoint to upload and crop images.",
        "description": "This service trims page borders and crops images into header and body parts for scanned letters.",
    }


@router.post("/crop-fixed-the-budget/", summary="Crop image with predefined dimensions (The Budget)")
async def crop_image_fixed_the_budget(
    image_file: Annotated[UploadFile, File(description="Image file to crop")]
):
    """Crop an image into two parts (header and body) using predefined dimensions.

    Returns a ZIP file containing both cropped parts.
    """
    try:
        if not image_file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        valid_extensions = [".png", ".jpg", ".jpeg"]
        file_ext = os.path.splitext(image_file.filename.lower())[1]
        if file_ext not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format. Supported formats: {', '.join(valid_extensions)}",
            )

        content = await image_file.read()

        try:
            result = FixedImageCropperTheBudgetService.crop_image_fixed_the_budget(
                content, image_file.filename
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")

        return StreamingResponse(
            result["zip_buffer"],
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={result['filename']}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/health")
async def health_check():
    """Endpoint para verificar el estado del servicio"""
    return {"status": "OK", "service": "Fixed Image Cropper The Budget"}
