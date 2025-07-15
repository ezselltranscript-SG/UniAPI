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
            
            # Extraer palabras, puntuación y espacios
            # Patrón que captura palabras, signos de puntuación y espacios por separado
            pattern = r'([\w]+|[^\w\s]|\s+)'
            tokens = re.findall(pattern, text)
            result = []
            
            i = 0
            while i < len(tokens):
                token = tokens[i]
                
                # Si no es una palabra (es puntuación o espacio), mantenerla sin cambios
                if not re.match(r'^[\w]+$', token):
                    result.append(token)
                    i += 1
                    continue
                
                # Intentar nombres compuestos (hasta 3 palabras)
                best_match = None
                best_similarity = 0
                best_length = 0
                
                # Probar con diferentes longitudes de palabras compuestas
                for length in range(1, 4):
                    if i + length > len(tokens):
                        break
                        
                    # Verificar que todos los tokens sean palabras
                    if not all(re.match(r'^[\w]+$', tokens[i+j]) for j in range(length)):
                        continue
                        
                    compound = ' '.join(tokens[i:i+length])
                    
                    # Encontrar la mejor coincidencia para este compuesto
                    for town in towns:
                        similarity = fuzz.ratio(compound.lower(), town.lower())
                        if similarity >= threshold and (similarity > best_similarity or 
                                                      (similarity == best_similarity and length > best_length)):
                            best_match = town
                            best_similarity = similarity
                            best_length = length
                
                # Si encontramos una coincidencia para un compuesto
                if best_match and best_length > 0:
                    result.append(best_match)
                    i += best_length
                else:
                    # Si no hay coincidencia compuesta, intentar con una sola palabra
                    word = token
                    # Usar partial_ratio para mejorar coincidencias parciales
                    best_match = max(
                        towns,
                        key=lambda town: max(fuzz.ratio(word.lower(), town.lower()), 
                                            fuzz.partial_ratio(word.lower(), town.lower()))
                    )
                    # Usar el mejor entre ratio y partial_ratio
                    ratio_score = fuzz.ratio(word.lower(), best_match.lower())
                    partial_score = fuzz.partial_ratio(word.lower(), best_match.lower())
                    similarity = max(ratio_score, partial_score)
                    result.append(best_match if similarity >= threshold else word)
                    i += 1
            
            # No necesitamos reconstruir con espacios adicionales ya que ahora
            # preservamos los espacios originales del texto
            corrected_text = ''.join(result)
                
            return corrected_text
        except Exception as e:
            logger.error(f"Error al corregir texto: {str(e)}")
            return text
