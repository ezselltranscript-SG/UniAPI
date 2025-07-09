import os
import shutil
import tempfile
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse

from app.config import DOWNLOADS_DIR
from .service import PDFCustomSplitterService

# Create router for PDF Custom Splitter service
router = APIRouter()

@router.get("/")
def read_root():
    """Welcome endpoint for PDF Custom Splitter service"""
    return {
        "message": "Welcome to PDF Custom Splitter Service. Use /split-custom/ endpoint to upload and split PDFs with custom page count per file.",
        "usage": "POST to /split-custom/ with a PDF file and pages_per_file parameter (default: 3)"
    }


@router.post("/split-custom/", summary="Split PDF into custom page groups")
async def split_pdf_custom(
    pdf_file: Annotated[UploadFile, File(description="PDF file to split")],
    pages_per_file: Annotated[int, Form(description="Number of pages per output file")] = 3
):
    """Split a PDF file into groups with a specified number of pages per output file and return a ZIP archive.
    
    - **pdf_file**: The PDF file to split
    - **pages_per_file**: Number of pages per output file (default: 3)
    
    Returns a ZIP file containing all page groups as separate PDF files.
    
    Example file naming:
    - Input: document.pdf with pages_per_file=4
    - Output files: 
        - document_Group1_Pages1-4.pdf
        - document_Group2_Pages5-8.pdf
        - etc.
    """
    try:
        # Debug info
        print(f"Processing file: {pdf_file.filename}")
        print(f"Pages per file: {pages_per_file}")
        
        # Validate file type
        if not pdf_file.filename or not pdf_file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be a PDF")
        
        # Validate pages_per_file
        if pages_per_file < 1:
            raise HTTPException(status_code=400, detail="pages_per_file must be at least 1")
        
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
            
            # Split the PDF into custom page groups using the service
            result = PDFCustomSplitterService.split_by_page_count(pdf_path, output_folder, pages_per_file)
            
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
    return {"status": "OK", "service": "PDF Custom Splitter"}
