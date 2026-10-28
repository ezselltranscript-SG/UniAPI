import io
import os
import re
import unicodedata
import zipfile
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from .service import PDFNormalizerService
from .vision import BatchHeader, VisionReviewError
from app.concurrency import run_blocking, PYMUPDF_LOCK


router = APIRouter()


def _upload_base_name(filename: str) -> str:
    leaf_name = os.path.basename(filename.replace("\\", "/"))
    return os.path.splitext(leaf_name)[0]


def _build_content_disposition(filename: str) -> str:
    """Return a header-safe attachment name while preserving Unicode clients."""
    return _attachment_header(f"{_upload_base_name(filename)}_normalized.pdf")


def _batch_prefix(batch: BatchHeader) -> str:
    """Return ``MM-DD-Batch#`` from the batch header, with X for anything unread."""
    month = f"{batch.received_month:02d}" if batch.received_month else "XX"
    day = f"{batch.received_day:02d}" if batch.received_day else "XX"
    return f"{month}-{day}-Batch{batch.number or 'X'}"


def _letter_file_names(batch: BatchHeader, letter_count: int) -> list[str]:
    """Name each letter ``MM-DD-Batch#-position-total.pdf``.

    The total is the batch header's letter count when it was read, so a
    missing letter shows up as a gap downstream; otherwise the letters found.
    """
    total = batch.letter_count or letter_count
    prefix = _batch_prefix(batch)
    return [f"{prefix}-{position}-{total}.pdf" for position in range(1, letter_count + 1)]


def _normalized_file_name(filename: str, batch: BatchHeader, letter_count: int) -> str:
    if not batch.number:
        return f"{_upload_base_name(filename)}_normalized.pdf"
    sheets = f"-{batch.sheets_per_letter}sheets" if batch.sheets_per_letter else ""
    return f"{_batch_prefix(batch)}{sheets}-{batch.letter_count or letter_count}letters.pdf"


def _attachment_header(output_name: str) -> str:
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
    vision_provider: str | None = Query(None, pattern="^(openai|anthropic)$", description="Vision provider override; defaults to PDF_NORMALIZER_VISION_PROVIDER or OpenAI"),
    vision_model: str | None = Query(None, description="Optional vision-model override for the selected provider"),
    judge: bool = Query(True, description="Have the vision model check the finished document page by page and retry the pages it flags"),
    output: str = Query("pdf", pattern="^(pdf|zip)$", description="pdf returns one normalized PDF; zip returns one PDF per letter"),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    if output == "zip" and review_mode != "vision":
        raise HTTPException(status_code=400, detail="output=zip needs review_mode=vision to find the letters")

    try:
        result = await run_blocking(
            PDFNormalizerService.normalize_pdf,
            await file.read(),
            auto_rotate=auto_rotate,
            ensure_page_pairs=ensure_page_pairs,
            review_mode=review_mode,
            vision_provider=vision_provider,
            vision_model=vision_model,
            judge=judge,
            split_letters=output == "zip",
            serialize_with=PYMUPDF_LOCK,
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
    batch: BatchHeader = result["batch"]
    letter_count = len(result["letter_page_ranges"])
    if output == "zip":
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, letter_pdf in zip(_letter_file_names(batch, letter_count), result["letter_pdfs"]):
                bundle.writestr(name, letter_pdf)
        body = archive.getvalue()
        media_type = "application/zip"
        download_name = (
            f"{_batch_prefix(batch)}.zip" if batch.number else f"{_upload_base_name(file.filename)}_letters.zip"
        )
    else:
        body = result["pdf_bytes"]
        media_type = "application/pdf"
        download_name = _normalized_file_name(file.filename, batch, letter_count)

    return StreamingResponse(
        io.BytesIO(body),
        media_type=media_type,
        headers={
            "Content-Disposition": _attachment_header(download_name),
            "X-Input-Pages": str(result["input_page_count"]),
            "X-Output-Pages": str(result["output_page_count"]),
            "X-Rotated-Pages": str(rotated_pages),
            "X-Blank-Pages-Added": str(result["blank_pages_added"]),
            "X-Blank-After-Source-Pages": blank_after_pages,
            "X-Letter-Start-Pages": letter_start_pages,
            "X-Applied-Rotations": applied_rotations,
            "X-Rotation-Overrides": rotation_overrides,
            "X-Review-Mode": result["review_mode"],
            "X-Review-Provider": result["review_provider"],
            "X-Review-Model": result["review_model"],
            "X-Judge-Status": result["judge_status"],
            "X-Judge-Retries": str(result["judge_retries"]),
            "X-Judge-Issues": ",".join(result["judge_issues"]),
            "X-Batch-Number": str(batch.number or ""),
            "X-Batch-Received": (
                f"{batch.received_month:02d}-{batch.received_day:02d}" if batch.received_month else ""
            ),
            "X-Batch-Sheets": str(batch.sheets_per_letter or ""),
            "X-Batch-Letters": str(batch.letter_count or ""),
            "X-Letters-Found": str(letter_count),
        },
    )


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "pdf-normalizer"}
