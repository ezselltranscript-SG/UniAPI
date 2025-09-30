import os
import shutil
import base64
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.config import DOWNLOADS_DIR
from .service import DocxGeneratorService

router = APIRouter()


class DocxPayload(BaseModel):
    city: Optional[str] = Field(default="City", description="City name")
    authorName: Optional[str] = Field(default="Name", description="Author name")
    date: Optional[str] = Field(default="No Date", description="Date string")
    body: Optional[str] = Field(default="", description="Body text content")
    documentName: Optional[str] = Field(default="document.docx", description="Output file name (.docx)")


@router.get("/")
async def read_root():
    return {
        "message": "DOCX Generator Service",
        "endpoints": {
            "POST /generate/": "Genera un documento .docx con plantilla básica (title + body)",
        },
        "payload": {
            "city": "City",
            "authorName": "Name",
            "date": "YYYY-MM-DD",
            "body": "Main content",
            "documentName": "my-file.docx",
        },
    }


@router.post("/generate/", summary="Generar documento Word (.docx)")
async def generate_docx(payload: DocxPayload, as_base64: bool = Query(False, description="Si es true, retorna JSON con base64 en lugar de archivo")):
    try:
        service = DocxGeneratorService()
        result = service.generate_docx(payload.model_dump())

        # Move to persistent downloads directory
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        persistent_path = os.path.join(DOWNLOADS_DIR, result["filename"])
        shutil.copy2(result["docx_path"], persistent_path)

        if as_base64:
            with open(persistent_path, "rb") as f:
                data_b64 = base64.b64encode(f.read()).decode("utf-8")
            return JSONResponse(
                content={
                    "success": True,
                    "binary": {
                        "data": {
                            "data": data_b64,
                            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "fileName": result["filename"],
                        }
                    },
                }
            )

        return FileResponse(
            path=persistent_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=result["filename"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar el documento: {str(e)}")
