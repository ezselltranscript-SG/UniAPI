import os
import shutil
import tempfile
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import FileResponse

from app.config import DOWNLOADS_DIR
from .service import PDFSplitterService

# Create router for PDF Splitter service
router = APIRouter()

@router.get("/")
def read_root():
    """Welcome endpoint for PDF Splitter service"""
    return {"message": "Welcome to PDF Splitter Service. Use /split/ endpoint to upload and split PDFs."}


@router.post("/split/", summary="Split PDF into individual pages")
async def split_pdf(pdf_file: Annotated[UploadFile, File(description="PDF file to split")]):
    """Split a PDF file into individual pages and return a ZIP archive.
    
    - **pdf_file**: The PDF file to split
    
    Returns a ZIP file containing all individual pages as separate PDF files.
    
    Example file naming:
    - Input: 070425-1-OBITUARIES-B01-9.pdf
    - Output folder: 070425-1-OBITUARIES-B01-9
    - Output files: 
        - 070425-1-OBITUARIES-B01-9-Part1.pdf
        - 070425-1-OBITUARIES-B01-9-Part2.pdf
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
            
            # Split the PDF into individual pages using the service
            pdf_service = PDFSplitterService()
            pdf_service.split_pages(pdf_path, output_folder)
            
            # Create a ZIP file containing all the split pages
            zip_basename = os.path.join(temp_dir, folder_name)
            zip_path = shutil.make_archive(zip_basename, 'zip', output_folder)
            
            # Verify the file exists before returning
            if not os.path.exists(zip_path):
                print(f"Error: ZIP file was not created at {zip_path}")
                raise HTTPException(status_code=500, detail="Failed to create ZIP file")
                
            print(f"ZIP file created successfully at: {zip_path}")
            
            # Create a copy of the ZIP file in a more persistent location
            persistent_zip = os.path.join(DOWNLOADS_DIR, f"{folder_name}.zip")
            shutil.copy2(zip_path, persistent_zip)
            print(f"Copied ZIP to persistent location: {persistent_zip}")
            
            # Return the ZIP file from the persistent location
            return FileResponse(
                path=persistent_zip,
                media_type="application/zip",
                filename=f"{folder_name}.zip",
                background=None  # Prevent background task from running
            )
        except Exception as e:
            # Clean up the temp directory in case of error
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise e
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
