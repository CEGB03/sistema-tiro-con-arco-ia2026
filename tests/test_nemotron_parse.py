import os
import json
import pytest
import requests
from pathlib import Path

# 1. Definir la ruta raíz del proyecto de forma robusta
# Path(__file__) -> .../tests/test_nemotron_parse.py
# .parents[1] -> sube dos niveles y llega a .../sistema-tiro-con-arco-ia2026
BASE_DIR = Path(__file__).resolve().parents[1]

# 2. Ruta exacta de la imagen (basado en el error que te arrojó)
IMAGE_PATH = BASE_DIR / "data" / "raw" / "2026-06-28-S-AFAPIECO-Planillas-20260702_191449" / "2026-06-28-S-AFAPIECO-Planillas-20260702_191449-pages-recortado-images-2.jpg"

INVOKE_URL = "https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-parse/parse"

def test_nemotron_parse_endpoint():
    # 1. Verificar API Key
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        pytest.fail("La variable de entorno 'NVIDIA_API_KEY' no está definida.")

    # 2. Verificar que la imagen existe
    if not IMAGE_PATH.is_file():
        pytest.fail(f"No se encontró la imagen en: {IMAGE_PATH}")

    # 3. Leer la imagen
    with open(IMAGE_PATH, "rb") as f:
        image_bytes = f.read()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }

    files = {
        "document": (IMAGE_PATH.name, image_bytes, "image/jpeg"),
        "options": (None, json.dumps({"decoding": {"max_output_tokens": 4096}}), "application/json")
    }

    # 4. Hacer la petición
    try:
        response = requests.post(INVOKE_URL, headers=headers, files=files, timeout=60)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        pytest.fail(f"La petición a NVIDIA falló: {e}")

    result = response.json()

    # 5. Validaciones
    assert "content" in result, "La respuesta no contiene el campo 'content'."
    assert len(result["content"].strip()) > 0, "El contenido extraído está vacío."

    # 6. Imprimir una muestra para ver qué está leyendo el modelo
    print("\n" + "="*60)
    print("✅ ¡TEST EXITOSO! Muestra del contenido extraído por la IA:")
    print("="*60)
    print(result["content"][:1000] + "\n...[cortado para visualizar]")
    print("="*60 + "\n")