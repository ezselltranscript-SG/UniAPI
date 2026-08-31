import io
import os
import re
import unicodedata
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from .service import PDFNormalizerService
from .vision import VisionReviewError


router = APIRouter()


def _build_content_disposition(filename: str) -> str:
    """Return a header-safe attachment name while preserving Unicode clients."""
    leaf_name = os.path.basename(filename.replace("\\", "/"))
    base_name = os.path.splitext(leaf_name)[0]
    output_name = f"{base_name}_normalized.pdf"
    output_name = output_name.replace("\r", "").replace("\n", "")

    ascii_name = (
        unicodedata.normalize("NFKD", output_name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_name = re.sub(r"[^A-Za-z0-9._ -]", "_", ascii_name).strip(" .")
    if not ascii_name:
        ascii_name = "normalized.pdf"

    encoded_name = quote(output_name, safe="")
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{encoded_name}"
    )


@router.get("/")
def read_root():
    return {
        "message": "PDF Normalizer Service",
        "endpoint": "POST /normalize/",
        "behavior": "Uses vision review to correct page rotations and insert black missing reverse sides at letter boundaries.",
    }


@router.post("/normalize/", summary="Normalize scanned PDF page orientation and page pairs")
async def normalize_pdf(
    file: Annotated[UploadFile, File(description="PDF file to normalize")],
    auto_rotate: bool = Query(True, description="Apply the reviewed page rotations"),
    ensure_page_pairs: bool = Query(True, description="Apply the reviewed black missing-side pages"),
    review_mode: str = Query("vision", pattern="^(vision|heuristic)$", description="vision uses the LLM; heuristic is the non-LLM fallback"),
    vision_model: str | None = Query(None, description="Optional OpenAI vision model override"),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    try:
        result = PDFNormalizerService.normalize_pdf(
            await file.read(),
            auto_rotate=auto_rotate,
            ensure_page_pairs=ensure_page_pairs,
            review_mode=review_mode,
            vision_model=vision_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VisionReviewError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error normalizing PDF: {exc}") from exc

    rotated_pages = sum(rotation != 0 for rotation in result["applied_rotations"])
    blank_after_pages = ",".join(map(str, result["blank_after_source_pages"]))
    letter_start_pages = ",".join(map(str, result["letter_start_pages"]))
    applied_rotations = ",".join(
        f"{page}:{rotation}"
        for page, rotation in enumerate(result["applied_rotations"], start=1)
        if rotation
    )
    rotation_overrides = ",".join(
        str(page)
        for page, source in enumerate(result["rotation_sources"], start=1)
        if source.endswith("_override")
    )
    return StreamingResponse(
        io.BytesIO(result["pdf_bytes"]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": _build_content_disposition(file.filename),
            "X-Input-Pages": str(result["input_page_count"]),
            "X-Output-Pages": str(result["output_page_count"]),
            "X-Rotated-Pages": str(rotated_pages),
            "X-Blank-Pages-Added": str(result["blank_pages_added"]),
            "X-Blank-After-Source-Pages": blank_after_pages,
            "X-Letter-Start-Pages": letter_start_pages,
            "X-Applied-Rotations": applied_rotations,
            "X-Rotation-Overrides": rotation_overrides,
            "X-Review-Mode": result["review_mode"],
            "X-Review-Model": result["review_model"],
        },
    )


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "pdf-normalizer"}
