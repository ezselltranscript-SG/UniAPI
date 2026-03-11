import os
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from .service import FixedImageCropperTheBudgetT2Service

# Create router for Fixed Image Cropper The Budget T2 service
router = APIRouter()


@router.get("/")
def read_root():
    """Welcome endpoint for Fixed Image Cropper The Budget T2 service"""
    return {
        "message": "Welcome to Fixed Image Cropper The Budget T2 Service. Use /crop-fixed-the-budget-t2/ endpoint to upload and crop images.",
        "description": "This service trims page borders and crops images into header and body parts for scanned letters.",
    }


@router.post("/crop-fixed-the-budget-t2/", summary="Crop image with predefined dimensions (The Budget T2)")
async def crop_image_fixed_the_budget_t2(
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
            result = FixedImageCropperTheBudgetT2Service.crop_image_fixed_the_budget_t2(
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
    return {"status": "OK", "service": "Fixed Image Cropper The Budget T2"}
