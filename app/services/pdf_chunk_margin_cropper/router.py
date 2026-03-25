import io
import os
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from fastapi.responses import StreamingResponse

from . import service as crop_text_box


router = APIRouter()


@router.get("/")
def read_root():
    return {
        "message": "PDF Chunk Margin Cropper Service",
        "endpoints": {
            "POST /process/": "Upload a PDF, provide chunk_size; keeps first page of each chunk, crops the rest, returns a single PDF",
        },
        "parameters": {
            "file": "PDF file",
            "chunk_size": "Number of pages per chunk (3,4,5,6,...)",
            "dpi": "Render DPI (default 250)",
        },
    }


@router.post("/process/", summary="Chunk-aware margin crop for PDF")
async def process_pdf(
    file: Annotated[UploadFile, File(description="PDF file to process")],
    chunk_size: int = Query(2, ge=1, description="Number of pages per chunk"),
    dpi: int = Query(250, ge=72, le=400, description="Render DPI"),
    mode: str = Query("crop", description="Processing mode: crop or mark"),
    debug: bool = Query(False, description="If true, stamps pages with debug info")
):
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        pdf_bytes = await file.read()

        mode = (mode or "crop").lower().strip()
        if mode not in {"crop", "mark"}:
            raise HTTPException(status_code=400, detail="mode must be 'crop' or 'mark'")

        if debug:
            print(
                "[pdf_chunk_margin_cropper] params "
                f"chunk_size={chunk_size} dpi={dpi} mode={mode} filename={file.filename} bytes={len(pdf_bytes)}"
            )

        try:
            result = crop_text_box.PDFChunkMarginCropperService.process_pdf(
                pdf_bytes=pdf_bytes,
                chunk_size=chunk_size,
                dpi=dpi,
                mode=mode,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

        base = os.path.splitext(file.filename)[0]
        out_name = f"{base}_cropped.pdf"

        return StreamingResponse(
            io.BytesIO(result["pdf_bytes"]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={out_name}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
