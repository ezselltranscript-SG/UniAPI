import os
import shutil
import tempfile
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import FileResponse

from app.config import DOWNLOADS_DIR
from .service import PDFPairSplitterService

# Create router for PDF Pair Splitter service
router = APIRouter()

@router.get("/")
def read_root():
    """Welcome endpoint for PDF Pair Splitter service"""
    return {"message": "Welcome to PDF Pair Splitter Service. Use /split-pairs/ endpoint to upload and split PDFs into pairs of pages."}


@router.post("/split-pairs/", summary="Split PDF into pairs of pages (2 pages per file)")
async def split_pdf_pairs(pdf_file: Annotated[UploadFile, File(description="PDF file to split")]):
    """Split a PDF file into pairs of pages (2 pages per output file) and return a ZIP archive.
    
    - **pdf_file**: The PDF file to split
    
    Returns a ZIP file containing all page pairs as separate PDF files.
    
    Example file naming:
    - Input: document.pdf
    - Output folder: document
    - Output files: 
        - document_Part1.pdf (pages 1-2)
        - document_Part2.pdf (pages 3-4)
        - etc.
    """
    try:
        # Debug info
        print(f"Processing file: {pdf_file.filename}")
        
        # Validate file type
        if not pdf_file.filename or not pdf_file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be a PDF")
        
        # Create a persistent temporary directory
        temp_dir = tempfile.mkdtemp()
        try:
            # Save the uploaded PDF to the temporary directory
            pdf_path = os.path.join(temp_dir, pdf_file.filename)
            content = await pdf_file.read()
            with open(pdf_path, "wb") as f:
                f.write(content)
            
            # Get the folder name (same as the original PDF name without extension)
            folder_name = os.path.splitext(pdf_file.filename)[0]
            output_folder = os.path.join(temp_dir, folder_name)
            os.makedirs(output_folder, exist_ok=True)
            
            # Split the PDF into pairs of pages using the service
            result = PDFPairSplitterService.split_page_pairs(pdf_path, output_folder)
            
            # Create a copy of the ZIP file in a more persistent location
            persistent_zip = os.path.join(DOWNLOADS_DIR, result["zip_filename"])
            shutil.copy2(result["zip_path"], persistent_zip)
            print(f"Copied ZIP to persistent location: {persistent_zip}")
            
            # Return the ZIP file from the persistent location
            return FileResponse(
                path=persistent_zip,
                media_type="application/zip",
                filename=result["zip_filename"],
                background=None  # Prevent background task from running
            )
        except Exception as e:
            # Clean up the temp directory in case of error
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise e
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


@router.get("/health")
async def health_check():
    """Endpoint para verificar el estado del servicio"""
    return {"status": "OK", "service": "PDF Pair Splitter"}
