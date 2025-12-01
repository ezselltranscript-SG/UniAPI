import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import API_HOST, API_PORT, API_RELOAD, CORS_ORIGINS

# Import routers from each service
from app.services.pdf_splitter.router import router as pdf_splitter_router
from app.services.pdf_pair_splitter.router import router as pdf_pair_splitter_router
from app.services.pdf_custom_splitter.router import router as pdf_custom_splitter_router
from app.services.image_cropper.router import router as image_cropper_router
from app.services.fixed_image_cropper.router import router as fixed_image_cropper_router
from app.services.word_to_pdf.router import router as word_to_pdf_router
from app.services.file_merger.router import router as file_merger_router
from app.services.pdf_to_image.router import router as pdf_to_image_router
from app.services.ocr.router import router as ocr_router
from app.services.image_to_pdf.router import router as image_to_pdf_router
from app.services.pdf_text_extractor.router import router as pdf_text_extractor_router
from app.services.text_correction.router import router as text_correction_router
from app.services.shower_cropper.router import router as shower_cropper_router
from app.services.column_merger.router import router as column_merger_router
from app.services.docx_generator.router import router as docx_generator_router
# Import additional service routers here as they are added
from app.services.anchored_pdf_cropper.router import router as anchored_pdf_cropper_router
from app.services.fixed_image_cropper_NT.router import router as fixed_image_cropper_nt_router
from app.services.template_checker.router import router as template_checker_router

# Create main FastAPI application
app = FastAPI(
    title="Unified Document Services API",
    description="Centralized API for document processing, transcription, and letter generation services",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
def read_root():
    """Endpoint de bienvenida"""
    return {
        "message": "Welcome to the Unified Document Services API",
        "services": [
            {"name": "PDF Splitter", "endpoint": "/pdf-splitter"},
            {"name": "PDF Pair Splitter", "endpoint": "/pdf-pair-splitter"},
            {"name": "PDF Custom Splitter", "endpoint": "/pdf-custom-splitter"},
            {"name": "Image Cropper", "endpoint": "/image-cropper"},
            {"name": "Fixed Image Cropper", "endpoint": "/fixed-image-cropper"},
            {"name": "Word to PDF", "endpoint": "/word-to-pdf"},
            {"name": "File Merger", "endpoint": "/file-merger"},
            {"name": "PDF to Image", "endpoint": "/pdf-to-image"},
            {"name": "OCR", "endpoint": "/ocr"},
            {"name": "Image to PDF", "endpoint": "/image-to-pdf"},
            {"name": "PDF Text Extractor", "endpoint": "/pdf-text-extractor"},
            {"name": "Text Correction", "endpoint": "/text-correction"},
            {"name": "Shower Cropper", "endpoint": "/shower-cropper"},
            {"name": "Column Merger", "endpoint": "/column-merger"},
            {"name": "DOCX Generator", "endpoint": "/docx-generator"},
            {"name": "Anchored PDF Cropper", "endpoint": "/anchored-pdf-cropper"},
            {"name": "Fixed Image Cropper NT", "endpoint": "/fixed-image-cropper-nt"},
            {"name": "Template Checker", "endpoint": "/template-checker"},
            # Add other services here as they are implemented
        ],
        "documentation": "/docs"
    }

# Include routers from each service
app.include_router(pdf_splitter_router, prefix="/pdf-splitter", tags=["PDF Splitter"])
app.include_router(pdf_pair_splitter_router, prefix="/pdf-pair-splitter", tags=["PDF Pair Splitter"])
app.include_router(pdf_custom_splitter_router, prefix="/pdf-custom-splitter", tags=["PDF Custom Splitter"])
app.include_router(image_cropper_router, prefix="/image-cropper", tags=["Image Cropper"])
app.include_router(fixed_image_cropper_router, prefix="/fixed-image-cropper", tags=["Fixed Image Cropper"])
app.include_router(word_to_pdf_router, prefix="/word-to-pdf", tags=["Word to PDF"])
app.include_router(file_merger_router, prefix="/file-merger", tags=["File Merger"])
app.include_router(pdf_to_image_router, prefix="/pdf-to-image", tags=["PDF to Image"])
app.include_router(ocr_router, prefix="/ocr", tags=["OCR"])
app.include_router(image_to_pdf_router, prefix="/image-to-pdf", tags=["Image to PDF"])
app.include_router(pdf_text_extractor_router, prefix="/pdf-text-extractor", tags=["PDF Text Extractor"])
app.include_router(text_correction_router, prefix="/text-correction", tags=["Text Correction"])
app.include_router(shower_cropper_router, prefix="/shower-cropper", tags=["Shower Cropper"])
app.include_router(column_merger_router, prefix="/column-merger", tags=["Column Merger"])
app.include_router(docx_generator_router, prefix="/docx-generator", tags=["DOCX Generator"])
app.include_router(anchored_pdf_cropper_router, prefix="/anchored-pdf-cropper", tags=["Anchored PDF Cropper"])
# Include the NT variant of the fixed image cropper
app.include_router(fixed_image_cropper_nt_router, prefix="/fixed-image-cropper-nt", tags=["Fixed Image Cropper NT"])
# Template checker
app.include_router(template_checker_router, prefix="/template-checker", tags=["Template Checker"])
# Include additional service routers here as they are added

if __name__ == "__main__":
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=API_RELOAD)
