from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Dict, Any
from .service import TextCorrectionService
import logging

# Configurar logger
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(
    prefix="/text-correction",
    tags=["text-correction"],
    responses={404: {"description": "Not found"}},
)

class TextCorrectionRequest(BaseModel):
    text: str
    threshold: int = 85

class TextCorrectionResponse(BaseModel):
    corrected_text: str

@router.post("/correct", response_model=TextCorrectionResponse)
async def correct_text(request: TextCorrectionRequest = Body(...)):
    """
    Corrige el texto utilizando coincidencia difusa con nombres de ciudades.
    
    - **text**: Texto a corregir
    - **threshold**: Umbral de similitud (0-100). Por defecto: 85
    """
    try:
        corrected_text = TextCorrectionService.correct_text(
            text=request.text,
            threshold=request.threshold
        )
        return {"corrected_text": corrected_text}
    except Exception as e:
        logger.error(f"Error en endpoint de corrección de texto: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al procesar la solicitud: {str(e)}")
