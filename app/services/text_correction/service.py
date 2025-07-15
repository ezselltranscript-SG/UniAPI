import re
from typing import List
from fuzzywuzzy import fuzz
from app.config import supabase
import logging

# Configurar logger
logger = logging.getLogger(__name__)

class TextCorrectionService:
    """
    Servicio para corregir texto utilizando coincidencia difusa con nombres de ciudades
    """
    
    @staticmethod
    def fetch_town_names() -> List[str]:
        """
        Obtiene nombres de ciudades desde Supabase (tabla: 'towns')
        
        Returns:
            List[str]: Lista de nombres de ciudades
        """
        try:
            if not supabase:
                logger.error("Conexión a Supabase no configurada")
                return []
                
            response = supabase.table("towns").select("name").execute()
            if response.data:
                return [entry["name"] for entry in response.data]
            return []
        except Exception as e:
            logger.error(f"Error al obtener nombres de ciudades: {str(e)}")
            return []

    @staticmethod
    def correct_text(text: str, threshold: int = 85) -> str:
        """
        Corrige el texto comparando con nombres de ciudades
        
        Args:
            text (str): Texto a corregir
            threshold (int, optional): Umbral de similitud. Defaults to 85.
            
        Returns:
            str: Texto corregido
        """
        try:
            towns = TextCorrectionService.fetch_town_names()
            if not towns:
                logger.warning("No se encontraron nombres de ciudades para corregir el texto")
                return text
                
            words = re.findall(r"\b\w+\b", text)
            corrected_words = []

            for word in words:
                best_match = max(
                    towns,
                    key=lambda town: fuzz.ratio(word.lower(), town.lower())
                )
                similarity = fuzz.ratio(word.lower(), best_match.lower())
                corrected_words.append(best_match if similarity >= threshold else word)

            return " ".join(corrected_words)
        except Exception as e:
            logger.error(f"Error al corregir texto: {str(e)}")
            return text
