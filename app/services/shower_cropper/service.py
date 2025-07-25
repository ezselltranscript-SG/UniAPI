from PIL import Image
import io
import zipfile
import os
import cv2
import numpy as np
from typing import Dict, Any, List, Tuple, Union

class ShowerCropperService:
    """
    Service for cropping shower-type forms: extracts only the fixed-position handwritten/text area
    based on visual layout measurements.
    """

    @staticmethod
    def crop_fixed_area(image_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Crops the image to a fixed area where the handwritten content typically appears.
        Detecta automáticamente si la imagen tiene el formato estándar y solo aplica
        el recorte si es así. Si no tiene el formato estándar, la deja sin cambios.

        Args:
            image_data: Raw bytes of the image file
            filename: Original filename

        Returns:
            Dictionary with a ZIP buffer containing the processed image(s) and metadata
        """
        # Load the image
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        print(f"Original image size: {width}x{height} pixels")
        
        # Convertir a formato OpenCV para detección
        img_array = np.array(image.convert('RGB'))
        cv_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # Detectar si la imagen tiene el formato estándar
        has_standard_format = ShowerCropperService.detect_standard_format(cv_img)
        
        # Fixed crop boundaries based on visual inspection of form layout
        top = int(height * 0.48)     # ~48% from top
        bottom = int(height * 0.84)  # ~84% from top
        text_box = (0, top, width, bottom)
        
        if has_standard_format:
            print(f"Detected standard format. Cropping fixed text area: {text_box}")
        else:
            print("No standard format detected. Keeping original image.")

        # Prepare output filename
        base_name, ext = os.path.splitext(filename)
        # Create a ZIP file with the processed image
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            base_name, ext = os.path.splitext(filename)
            
            if has_standard_format:
                # Crop the image if it has standard format
                text_image = image.crop(text_box)
                
                # Save the cropped image
                cropped_filename = f"{base_name}_text_area{ext}"
                text_bytes = io.BytesIO()
                text_image.save(text_bytes, format=image.format)
                zip_file.writestr(cropped_filename, text_bytes.getvalue())
                
                result_dimensions = text_image.size
            else:
                # Keep the original image if it doesn't have standard format
                img_bytes = io.BytesIO()
                image.save(img_bytes, format=image.format)
                zip_file.writestr(filename, img_bytes.getvalue())
                
                result_dimensions = image.size

        zip_buffer.seek(0)
        return {
            "zip_buffer": zip_buffer,
            "filename": f"{base_name}_processed.zip",
            "body_dimensions": result_dimensions,
            "format_detected": has_standard_format
        }
        
    @staticmethod
    def crop_fixed_area_obituaries(image_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Crops the image to a fixed area optimized for obituaries layout.
        Detecta automáticamente si la imagen tiene el formato estándar y solo aplica
        el recorte si es así. Si no tiene el formato estándar, la deja sin cambios.

        Args:
            image_data: Raw bytes of the image file
            filename: Original filename

        Returns:
            Dictionary with a ZIP buffer containing the processed image(s) and metadata
        """
        # Load the image
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        print(f"Original image size: {width}x{height} pixels")
        
        # Convertir a formato OpenCV para detección
        img_array = np.array(image.convert('RGB'))
        cv_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # Detectar si la imagen tiene el formato estándar
        has_standard_format = ShowerCropperService.detect_standard_format(cv_img)

        # Fixed crop boundaries for obituaries (25% to 81% of height)
        top = int(height * 0.25)     # 25% from top
        bottom = int(height * 0.81)  # 81% from top
        text_box = (0, top, width, bottom)
        
        if has_standard_format:
            print(f"Detected standard format. Cropping fixed obituary area: {text_box}")
        else:
            print("No standard format detected. Keeping original image.")
        
        # Prepare output filename
        base_name, ext = os.path.splitext(filename)
        # Create a ZIP file with the processed image
        cropped_filename = f"{base_name}_obituary_area{ext}"
        
        # Create an in-memory ZIP with the processed image
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            if has_standard_format:
                # Crop the image if it has standard format
                text_image = image.crop(text_box)
                
                # Save the cropped image
                text_bytes = io.BytesIO()
                text_image.save(text_bytes, format=image.format)
                zip_file.writestr(cropped_filename, text_bytes.getvalue())
                
                result_dimensions = text_image.size
            else:
                # Keep the original image if it doesn't have standard format
                img_bytes = io.BytesIO()
                image.save(img_bytes, format=image.format)
                zip_file.writestr(filename, img_bytes.getvalue())
                
                result_dimensions = image.size

        zip_buffer.seek(0)

        return {
            "zip_buffer": zip_buffer,
            "filename": f"{base_name}_obituary_processed.zip",
            "body_dimensions": result_dimensions,
            "format_detected": has_standard_format
        }
        
    @staticmethod
    def detect_standard_format(image_array: np.ndarray) -> bool:
        """
        Detecta si la imagen tiene el formato estándar del formulario.
        
        Args:
            image_array: Imagen en formato numpy array (OpenCV)
            
        Returns:
            True si la imagen tiene el formato estándar, False en caso contrario
        """
        # Convertir a escala de grises si es necesario
        if len(image_array.shape) == 3:
            gray = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)
        else:
            gray = image_array
            
        # Método 1: Buscar el borde negro característico
        # Aplicar umbralización para destacar los bordes negros
        _, thresh = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)
        
        # Buscar contornos rectangulares grandes
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Buscar un rectángulo grande que podría ser el borde del formulario
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            # Si encontramos un rectángulo grande que ocupa gran parte de la imagen
            if w > image_array.shape[1] * 0.8 and h > image_array.shape[0] * 0.7:
                # Verificar si tiene líneas horizontales características
                roi = gray[y:y+h, x:x+w]
                horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
                detect_horizontal = cv2.morphologyEx(roi, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
                horizontal_lines = cv2.findContours(detect_horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                horizontal_lines = horizontal_lines[0] if len(horizontal_lines) == 2 else horizontal_lines[1]
                
                if len(horizontal_lines) > 5:  # Si hay suficientes líneas horizontales
                    return True
        
        # Si no se detectó el formato estándar
        return False
    
    @staticmethod
    def process_mixed_format(image_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Procesa una imagen que puede contener páginas con formato estándar y sin formato.
        Recorta solo las páginas con formato estándar y deja sin cambios las demás.
        
        Args:
            image_data: Raw bytes de la imagen o PDF
            filename: Nombre original del archivo
            
        Returns:
            Dictionary con un ZIP buffer conteniendo todas las páginas procesadas
        """
        # Cargar la imagen
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        print(f"Original image size: {width}x{height} pixels")
        
        # Convertir a formato OpenCV para detección
        img_array = np.array(image.convert('RGB'))
        cv_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # Detectar si la imagen tiene el formato estándar
        has_standard_format = ShowerCropperService.detect_standard_format(cv_img)
        
        # Preparar el ZIP para la salida
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            base_name, ext = os.path.splitext(filename)
            
            if has_standard_format:
                # Aplicar recorte fijo si es formato estándar
                top = int(height * 0.48)     # Ajustado según la última configuración
                bottom = int(height * 0.84)  # Ajustado según la última configuración
                text_box = (0, top, width, bottom)
                
                print(f"Detected standard format. Cropping fixed text area: {text_box}")
                
                # Recortar la imagen
                text_image = image.crop(text_box)
                
                # Guardar en el ZIP
                cropped_filename = f"{base_name}_text_area{ext}"
                text_bytes = io.BytesIO()
                text_image.save(text_bytes, format=image.format)
                zip_file.writestr(cropped_filename, text_bytes.getvalue())
            else:
                # Mantener la imagen sin cambios si no es formato estándar
                print("No standard format detected. Keeping original image.")
                
                # Guardar la imagen original en el ZIP
                img_bytes = io.BytesIO()
                image.save(img_bytes, format=image.format)
                zip_file.writestr(filename, img_bytes.getvalue())
        
        zip_buffer.seek(0)
        return {
            "zip_buffer": zip_buffer,
            "filename": f"{base_name}_processed.zip",
            "format_detected": has_standard_format
        }
