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
# Import additional service routers here as they are added

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
# Include additional service routers here as they are added

if __name__ == "__main__":
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=API_RELOAD)
