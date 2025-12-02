from typing import Annotated
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, Response

from .service import TemplateCheckerService

router = APIRouter()

@router.get("/")
def read_root():
    return {"message": "Template Checker: POST /detect with an image to get template_id 1 or 2"}

@router.post("/detect", summary="Detect template type from image header (returns 1 or 2 as JSON)")
async def detect_template(
    image_file: Annotated[UploadFile, File(description="Image file to analyze")]
):
    try:
        if not image_file or not image_file.filename:
            raise HTTPException(status_code=400, detail="No image provided")
        if not image_file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        content = await image_file.read()
        result = TemplateCheckerService.detect_template(content)
        template_id = result.get("template_id", 1)
        # Return JSON so clients can branch on template_id
        # Keep reason and other debug info in case the caller needs it
        return JSONResponse({
            "template_id": template_id,
            "reason": result.get("reason"),
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting template: {str(e)}")
