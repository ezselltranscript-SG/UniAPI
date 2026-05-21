import base64

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .service import normalize_text, build_report_docx

router = APIRouter()

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class NormalizationRequest(BaseModel):
    date: str = Field(..., description="Date of the letter (will also be normalized)")
    body: str = Field(..., description="Body text of the letter to normalize")
    client: str = Field(..., description="Client name used to select normalization rules")


@router.get("/")
async def read_root():
    return {
        "message": "Word Normalizer Service",
        "description": "Expands short forms in letter text based on client-specific rules from Normalization_Words_List",
        "endpoints": {
            "POST /normalize/": "Normalize date and body text, returns JSON with normalized fields and a Word report file",
        },
        "payload": {
            "date": "2024-01-15",
            "body": "The pt was adm to the hosp.",
            "client": "ClientName",
        },
    }


@router.post("/normalize/", summary="Normalize short forms in letter date and body")
async def normalize(payload: NormalizationRequest):
    """
    Expand short forms in both the date and body using client-specific rules from Normalization_Words_List.

    Returns JSON with:
    - **date**: normalized date string
    - **body**: normalized body string
    - **file**: base64-encoded Word document listing every substitution made and the total count
    """
    try:
        result = normalize_text(payload.date, payload.body, payload.client)

        docx_bytes = build_report_docx(result["changes"], result["total_changes"])
        encoded = base64.b64encode(docx_bytes).decode("utf-8")

        return JSONResponse(
            content={
                "date": result["normalized_date"],
                "body": result["normalized_body"],
                "file": {
                    "data": encoded,
                    "mimeType": DOCX_MIME,
                    "fileName": "normalization_report.docx",
                },
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during normalization: {str(e)}")
