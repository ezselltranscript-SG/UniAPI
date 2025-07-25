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
        
        # Aplicar umbralización para mejorar el contraste
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        
        # Método 1: Buscar líneas horizontales características del formulario
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
        horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
        
        # Contar líneas horizontales
        contours_h, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Si hay suficientes líneas horizontales, probablemente es un formulario
        if len(contours_h) >= 3:
            print(f"Detected {len(contours_h)} horizontal lines - likely a standard form")
            return True
        
        # Método 2: Buscar texto "Ivverich" que aparece en el encabezado del formulario
        # Este método es más específico para el formato exacto mostrado
        top_region = gray[0:int(gray.shape[0]*0.2), :]
        _, top_thresh = cv2.threshold(top_region, 180, 255, cv2.THRESH_BINARY_INV)
        
        # Buscar contornos en la región superior que podrían ser el encabezado
        contours_top, _ = cv2.findContours(top_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Si hay varios contornos en la parte superior, podría ser el encabezado del formulario
        if len(contours_top) > 5:
            total_area = 0
            for c in contours_top:
                total_area += cv2.contourArea(c)
            
            # Si hay suficiente área de contornos en la parte superior
            if total_area > (top_region.shape[0] * top_region.shape[1] * 0.05):
                print(f"Detected header region with {len(contours_top)} contours - likely a standard form")
                return True
        
        # Método 3: Verificar patrón de líneas horizontales equidistantes en la parte central
        # Este método busca las líneas de escritura del formulario
        middle_region = gray[int(gray.shape[0]*0.4):int(gray.shape[0]*0.9), :]
        _, middle_thresh = cv2.threshold(middle_region, 200, 255, cv2.THRESH_BINARY_INV)
        
        # Detectar líneas horizontales en la región central
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        h_lines = cv2.morphologyEx(middle_thresh, cv2.MORPH_OPEN, h_kernel, iterations=1)
        contours_middle, _ = cv2.findContours(h_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Si hay varias líneas horizontales en la parte central, probablemente es un formulario
        if len(contours_middle) >= 5:
            print(f"Detected {len(contours_middle)} lines in writing area - likely a standard form")
            return True
        
        # Si llegamos aquí, no se detectó el formato estándar con ningún método
        print("No standard form pattern detected")
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
