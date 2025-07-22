FROM python:3.9-slim

# Evitar interacciones durante la instalación de paquetes
ENV DEBIAN_FRONTEND=noninteractive

# Configurar repositorios y aceptar EULA de Microsoft Fonts
RUN echo "deb http://deb.debian.org/debian/ bookworm main contrib" > /etc/apt/sources.list.d/contrib.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends debconf-utils && \
    echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections

# Instalar dependencias del sistema, incluyendo fuentes de Microsoft
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    poppler-utils \
    unrar-free \
    libmagic1 \
    p7zip-full \
    # Tesseract OCR para el servicio OCR
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    # Dependencias para patool
    cabextract \
    lzip \
    lzop \
    arj \
    # Dependencias para OpenCV (shower_cropper)
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    # Fuentes de Microsoft y configuración
    ttf-mscorefonts-installer \
    fontconfig \
    && fc-cache -f -v \
    # Limpiar caché de apt para reducir el tamaño de la imagen
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Configurar directorio de trabajo
WORKDIR /app

# Copiar archivos de requisitos e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Crear directorios necesarios
RUN mkdir -p downloads

# Copiar el resto del código
COPY . .

# Exponer el puerto que usará la aplicación
EXPOSE 8000

# Comando para ejecutar la aplicación
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
