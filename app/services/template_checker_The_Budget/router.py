from typing import Annotated

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from .service import TemplateCheckerTheBudgetService

router = APIRouter()


@router.get("/")
def read_root():
    return {
        "message": "Template Checker The Budget: POST /detect with an image to get template_id 1 or 2"
    }


@router.post("/detect", summary="Detect The Budget template type from image header (returns 1 or 2 as JSON)")
async def detect_template(
    image_file: Annotated[UploadFile, File(description="Image file to analyze")]
):
    try:
        if not image_file or not image_file.filename:
            raise HTTPException(status_code=400, detail="No image provided")
        if not image_file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        content = await image_file.read()
        result = TemplateCheckerTheBudgetService.detect_template(content)
        template_id = str(result.get("template_id", 1))

        return JSONResponse({
            "template_id": template_id,
            "reason": result.get("reason"),
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting template: {str(e)}")
