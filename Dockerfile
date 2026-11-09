FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

# Instalar dependencias del sistema (OpenCV, GLib, Tesseract OCR en español)
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 tesseract-ocr tesseract-ocr-spa && rm -rf /var/lib/apt/lists/*

# Copiar configuración de proyecto e instalar dependencias Python
COPY pyproject.toml ./

# Copiar el código fuente y variables de entorno
COPY src/ ./src/
COPY .env* ./
RUN pip install --no-cache-dir .

EXPOSE 7860

CMD ["python", "src/tiro_arco/app_tiro_con_arco.py"]
