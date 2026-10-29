FROM python:3.12-slim-bookworm

# Evitar interacciones durante la instalación de paquetes
ENV DEBIAN_FRONTEND=noninteractive

# glibc crea una arena de memoria por hilo y no devuelve al SO lo liberado en
# ellas: tras un lote de conversiones el proceso quedaba en ~1.1 GB en reposo.
# Con 2 arenas la memoria liberada vuelve a estar disponible (ver app/memory.py).
ENV MALLOC_ARENA_MAX=2

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
