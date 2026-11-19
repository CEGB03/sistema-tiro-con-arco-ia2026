# AGENTS.md

Instrucciones técnicas para asistentes de IA (Claude Code, Cursor, GitHub Copilot) que trabajen sobre este repositorio.

## 1. Instalación y Entorno

### Ejecución local con `uv` (Python 3.11 / 3.12)
```bash
# Dependencias del sistema requeridas por OpenCV y Tesseract
sudo apt update && sudo apt install -y tesseract-ocr tesseract-ocr-spa libgl1 libglib2.0-0
```
# Sincronizar entorno e iniciar la interfaz web (http://localhost:7860)
```python
uv sync
uv run tiro-con-arco
```
## Ejecución con Docker
```Bash
docker compose up -d --build
```
# Opcional: descargar modelo VLM local en el contenedor Ollama
```bash
docker exec -it archery_ollama_ocr ollama pull qwen2-vl
```
Variables de entorno
- Configurar NVIDIA_API_KEY en .env (en la raíz del proyecto) para habilitar NVIDIA NIM (nemotron-3.5-parse y llama-3.1-70b-instruct).

- Opcional: OLLAMA_HOST / OLLAMA_URL para inferencia local.

## 2. Comandos de Verificación y Tests
Ejecutar siempre la suite de pruebas antes de cerrar cambios en src/tiro_arco/:

```Bash
uv run pytest -v
```
Para probar un módulo o URL de scraping de forma aislada:

```Bash
uv run python -m tiro_arco.agente_4_scraper_resultados <torneo_id_o_url>
```
## 3. Convenciones del Código y del Dominio
- Terminología FATARCO / World Archery (no confundir):

  - Serie (1..10): tanda de 3 flechas dentro de una planilla.

  - Turno (Turno 1 / Turno 2, almacenado en el campo ronda): planilla completa de 30 flechas.

- Valores de flechas: Mantener siempre strings en mayúsculas preservando "X" (centro de 10) y "M" (Miss = 0 pts). Nunca convertir "X" en "10" ni "M" en "0" en la salida del OCR.

- Alcance del scraping web (agente_4_scraper_resultados.py): arquerosonline.com.ar solo publica puntajes acumulados por Turno (Turno 1, Turno 2, Total), nunca flechas individuales. No agregar métricas de error por flecha al Agente 4.

- Imports resilientes: En src/tiro_arco/, conservar los bloques try/except ImportError (from tiro_arco... -> from ... -> import directo) para que los módulos funcionen tanto instalados como ejecutados directamente.

- Límite de tasa NVIDIA NIM: Mantener RateLimiter(requests_per_minute=35) en agente_2_ocr_extractor.py para evitar errores HTTP 429.

- Callbacks de Gradio (app_tiro_con_arco.py): Cualquier modificación en la tupla de retorno de funciones conectadas a .click() o .change() debe actualizar exactamente en el mismo orden su lista outputs=[...].

- Notebooks: Mantener numeración secuencial (01_... a 06_...) en notebooks/, con un objetivo único por archivo.

## 4. Qué NO Tocar
- No modificar ni sobrescribir los datasets de Verdad Terreno en data/processed/*.csv ni las planillas originales en data/raw/.

- No commitear el archivo .env, credenciales ni archivos temporales generados en /tmp o data/audit/.

- No romper las claves raíz de los manifiestos JSON (tareas_agente2, transcripciones, resultados_auditados, verificaciones_web), ya que son el contrato entre módulos, tests y la UI.