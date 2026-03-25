import os
import shutil
import tempfile
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.config import DOWNLOADS_DIR
from .service import PDFChunkSplitterService


router = APIRouter()


@router.get("/")
def read_root():
    return {
        "message": "Welcome to PDF Chunk Splitter Service. Use /split-chunks/ endpoint to upload and split PDFs into N-page chunks.",
        "default_chunk_size": 2,
    }


@router.post("/split-chunks/", summary="Split PDF into N-page chunks (default 2 pages per file)")
async def split_pdf_chunks(
    pdf_file: Annotated[UploadFile, File(description="PDF file to split")],
    chunk_size: Annotated[int, Query(ge=1, description="Pages per output file (chunk size)")] = 2,
):
    try:
        print(f"Processing file: {pdf_file.filename}")
        print(f"Chunk size: {chunk_size}")

        if not pdf_file.filename or not pdf_file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        temp_dir = tempfile.mkdtemp()
        try:
            pdf_path = os.path.join(temp_dir, pdf_file.filename)
            content = await pdf_file.read()
            with open(pdf_path, "wb") as f:
                f.write(content)

            folder_name = os.path.splitext(pdf_file.filename)[0]
            output_folder = os.path.join(temp_dir, folder_name)
            os.makedirs(output_folder, exist_ok=True)

            result = PDFChunkSplitterService.split_by_chunk_size(pdf_path, output_folder, chunk_size)

            persistent_zip = os.path.join(DOWNLOADS_DIR, result["zip_filename"])
            shutil.copy2(result["zip_path"], persistent_zip)
            print(f"Copied ZIP to persistent location: {persistent_zip}")

            return FileResponse(
                path=persistent_zip,
                media_type="application/zip",
                filename=result["zip_filename"],
                background=None,
            )
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise e
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


@router.get("/health")
async def health_check():
    return {"status": "OK", "service": "PDF Chunk Splitter"}
