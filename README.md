# sistema-tiro-con-arco-ia2026

## Ayudamemoria de organizacion

```
sistema-tiro-con-arco-ia2026/
├── README.md ← README principal (siguiendo la plantilla obligatoria)
├── AGENTS.md ← (Opcional) Instrucciones para agentes de IA
├── pyproject.toml ← O requirements.txt con las dependencias
├── .gitignore ← Exclusión de venv, .env, temporales y datos pesados
├── LICENSE ← Licencia del proyecto (ej. MIT)
├── src/ ← Código fuente modular del proyecto
│    ├── __init__.py 
│    ├── agente_1_clasificador_segmentador.py ← Agente 1 (Segmentación visual OpenCV/Pillow + Pre-OCR + Render 300 DPI)
│    ├── agente_2_ocr_extractor.py ← Agente 2 (Digitaliza los valores con NVIDIA NIM, LLM Refactorizer u Ollama local)
│    ├── agente_3_validador_conciliador.py ← Agente 3 (Valida la matemática, deduce números ilegibles y reconcilia totales)
│    └── app_tiro_con_arco.py ← Interfaz principal / Orquestador Gradio
├── notebooks/ ← Pruebas de exploración / evaluación 
│    └── exploracion_y_evaluacion_ocr.ipynb 
├── data/
│    ├── raw/ ← Planillas de muestra sin procesar (PDFs, imágenes PNG/JPG)
│    │    ├── 1-AFPSF_Plani_TS-4-Arqueros.png
│    │    ├── 1A-AFPSF_Plani_TS.png
│    │    ├── Eliminacion-AFAPIECOSF-Sala-2-Arqueros.png
│    │    └── 2026-05-03-S-AFPSF-Planillas-20260505_recortado.pdf
│    └── processed/ ← Resultados exportados y datasets
│        └── torneo_indoor_san_francisco_detallado.csv
├── models/ ← (Reservado para pesos/modelos locales si aplicara)
├── tests/ ← Pruebas unitarias/integración
│    └── test_agente_1.py
└── docs/ ← Exclusivo para la Demo estática de GitHub Pages
     ├── index.html ← Landing page con el pitch, arquitectura y resultados
     ├── img/ ← Capturas de pantalla de la interfaz Gradio y diagramas 
     └── assets/ ← CSS/JS auxiliares para la web estática
```

---

## 🚀 Método de Ejecución Recomendado con Docker (Orquestado)

El proyecto está contenerizado para garantizar la portabilidad y evitar la instalación manual de dependencias del sistema operativo (como OpenCV o Tesseract OCR).

### 1. Requisitos Previos
* Docker Desktop o Docker Engine con Docker Compose V2.

### 2. Construir e Iniciar los Contenedores
En la raíz de tu repositorio, ejecutá:

```bash
docker compose up -d --build
```

Esto iniciará dos servicios interconectados en una red interna privada:
* **`archery_multiagent_app`**: Servidor Gradio y pipeline multi-agente en el puerto `7860`.
* **`archery_ollama_ocr`**: Motor local de modelos de visión en el puerto `11434`.

### 3. Descargar el Modelo de Visión en Ollama Local
Para habilitar la inferencia visual 100% privada y local sin depender de la nube, ejecutá en tu terminal:

```bash
docker exec -it archery_ollama_ocr ollama pull qwen2-vl
```

*(Opcional: también podés descargar `qwen2-vl:7b` o `llama3.2-vision`)*.

### 4. Abrir la Aplicación Web
Una vez iniciado el contenedor, abrí tu navegador e ingresá a:

👉 **http://localhost:7860**

### 5. Visualizacion de logs
Para poder ver los logs del docker, ejecutá en tu terminal:

```bash
docker compose logs -f archery-app
```

### 6. Frenado del contenedor
Para poder frenar el contenedor de su ejecucion, ejecutá en tu terminal:
```bash
docker compose down
```

---

## 💻 Método de Ejecución Local (Alternativo sin Docker)

Si preferís ejecutar la aplicación directamente en tu entorno Python local:

### 1. Dependencias del Sistema Operativo
Debés contar con Tesseract OCR y librerías gráficas instaladas:
* **Linux (Debian/Ubuntu):**
  ```bash
  sudo apt update && sudo apt install -y tesseract-ocr tesseract-ocr-spa libgl1 libglib2.0-0
  ```
* **macOS:**
  ```bash
  brew install tesseract tesseract-lang
  ```

### 2. Instalación con `uv` y Ejecución
```bash
# Sincronizar entorno de Python
uv sync

# Ejecutar la aplicación Gradio
uv run tiro-con-arco
```

*(Si utilizas un entorno virtual propio previamente activado como `venv_ia_proyecto`, puedes usar `uv run --active tiro-con-arco` o lanzar directamente `uv run tiro-con-arco`).*

---

# 🖥️ Interfaz Web Gradio
* **Flujo Interactivo en 4 Pasos con Control Humano (Human-in-the-loop):**
  * **Paso 0 (Carga y Renderizado):** Convierte los PDFs a 300 DPI para máxima nitidez. Permite aplicar mejoras de contraste (CLAHE) por página y **Deshacer** (Undo) si es necesario. Muestra una galería de las páginas físicas.
  * **Paso 1 (Segmentación):** Procesa el documento, clasifica las páginas (info/eliminatoria/clasificación) y divide los cuadrantes. Aplica solape de 20px para no cortar nombres. Permite mejorar recortes individuales.
  * **Paso 2 (OCR e Inspección):** Ofrece selección masiva con checkboxes. Ejecuta el OCR y presenta una tabla con vista previa, además de un visor de texto en crudo (LaTeX de Nemotron vs JSON parseado).
  * **Paso 3 (Auditoría):** El Agente 3 evalúa la matemática, deduce números ilegibles y arroja un **Score de Certeza** por cada arquero.

***

# Agentes

## 🤖 Agente 1: Clasificador y Segmentador Semántico (v28)
**Objetivo:** Recibir el archivo de entrada (**PDF multipágina** o **Imagen PNG/JPG**), procesar página por página y segmentar las planillas de arqueros. Utiliza una regla estricta de **homogeneidad documental** y descarte de hojas sin datos.

### 🧠 Opciones de Diferenciación y Pre-OCR
El Agente 1 no adivina; utiliza visión por computadora (OpenCV), renderizado de alta calidad y reglas de negocio para diferenciar el tipo de documento:
- **Renderizado Ultra-HD:** Convierte los PDFs a imágenes a **300 DPI** (`scale=4.1667`) para evitar la borrosidad en tablas manuscritas.
- **Micro-OCR de Diferenciación:** Ejecuta Tesseract a nivel de página completa buscando palabras clave antes de hacer los cortes:
  - Si detecta `Ganador`, `Set Point`, `Oro/Bronce`, `S.O.`, clasifica la hoja como **Eliminatoria**.
  - Si detecta `Turno:`, `18m-1`, `Ronda`, o distancias específicas, clasifica la hoja como **Clasificación**.
- **Descarte de Hoja Completa (`informacion` / `portada`):** Si la página no contiene una tabla de tiros (detección de grillas con morfología de líneas) o si, aun teniéndola, la evaluación de densidad de tinta confirma que **todos los cuadrantes están vacíos** (sin anotaciones manuscritas), se descarta la hoja completa. Se genera un solo recorte de la página entera, sin dividir en cuadrantes.
- **Homogeneidad Documental (`clasificacion` vs `eliminatoria`):** Si la página sí tiene anotaciones, se clasifica de forma **homogénea** para toda la hoja. Si el layout se detecta como 4 arqueros, los 4 recortes serán de `clasificacion`. Si es de 2 arqueros, será de `eliminatoria`. **Nunca se mezclan tipos de juego en una misma página.**
- **Cuadrantes Vacíos Parciales:** Si una planilla es de 4 arqueros pero uno solo está en blanco, ese recorte se marca con `es_cuadrante_vacio: True`, pero conserva el `tipo_juego: clasificacion` para mantener la coherencia.

### ✂️ Estrategia de Segmentación y Recorte Posicional
- **Clasificación (4 Arqueros):** Slots `A`, `B`, `C`, `D`. Aplica un margen de solape de 20px para no cortar los nombres en el centro de la hoja.
- **Eliminatoria (2 Arqueros):** Slots `A` (Izquierda) y `B` (Derecha).
- **Individual (1 Arquero):** Conserva el 100% de la imagen.

### 📄 Salida (Manifiesto JSON)
```json
{
  "archivo_origen": "planillas_torneo.pdf",
  "total_paginas": 2,
  "tareas_agente2": [
    {
      "pagina": 1,
      "target_id": "Portada",
      "tipo_juego": "informacion",
      "layout": "portada",
      "ruta_recorte": "/tmp/archery_agent1/pag_1_pos_Portada.png",
      "label": "Pág 1 - Hoja de Información / Portada",
      "es_pagina_informacion": true,
      "es_cuadrante_vacio": false,
      "razon_preclasificacion": "Sin tabla de tiros en la hoja / Hoja Informativa",
      "es_mejorado": false
    },
    {
      "pagina": 2,
      "target_id": "A",
      "tipo_juego": "clasificacion",
      "layout": "4_arqueros",
      "ruta_recorte": "/tmp/archery_agent1/pag_2_pos_A.png",
      "label": "Pág 2 - Pos A",
      "es_pagina_informacion": false,
      "es_cuadrante_vacio": false,
      "razon_preclasificacion": "Contiene datos anotados",
      "es_mejorado": true
    }
  ]
}
```

---

## 🤖 Agente 2: Preprocesador y Extractor OCR Multimodal (v56)
**Objetivo:** Tomar los recortes del Agente 1, preprocesar la imagen y transcribir los datos utilizando una **cadena de fallback** entre APIs en la nube y modelos locales, con refactorización secundaria.

### 🎨 1. Pipeline de Preprocesamiento (OpenCV)
- **Realce (CLAHE):** Resalta la tinta manuscrita frente a las sombras del escaneo.
- **Filtro Bilateral:** Elimina el ruido del papel sin difuminar los números.
- **Detección de Tabla Vacía:** Si el recorte no tiene suficiente tinta (ratio < 0.0003), se salta el OCR automáticamente y se marca como `sin_puntos_registrados`.

### 🧠 2. Diferenciación y Cadena de Resiliencia (Fallback)
El Agente 2 diferencia entre recortes de planillas reales y hojas de información.
- **Si `es_pagina_informacion` es True:** Omite el OCR inmediatamente (ahorra cuota y tiempo) y devuelve un JSON marcado como `Descartado (Sin OCR)`.
- **Si es una planilla real:** Intenta secuencialmente:
  1. **NVIDIA Nemotron Parse (API):** Usa el endpoint `/retrieval/nvidia/nemotron-3.5-parse/parse`. Extrae la tabla en formato LaTeX.
  2. **Refactorización Secundaria (LLM):** Si el LaTeX de Nemotron es complejo, invoca a `meta/llama-3.1-70b-instruct` para forzar la conversión a un JSON perfecto.
  3. **Ollama Local (Fallback):** Modelos como `qwen2.5-vl` o `deepseek-ocr`.
  4. **Tesseract OCR:** Como último recurso de texto tradicional.

*Nota:* El agente genera automáticamente un archivo de auditoría (`auditoria_nemotron_raw_vs_refactorizado.json`) comparando el texto en crudo contra el JSON final.

### 📄 Salida (Manifiesto JSON)
```json
{
  "archivo_origen": "planillas_torneo.pdf",
  "transcripciones": [
    {
      "pagina": 1,
      "target_id": "Portada",
      "tipo_juego": "informacion",
      "transcripcion": {
        "arquero": "N/A (Hoja Informativa)",
        "sin_puntos_registrados": true,
        "observacion": "Hoja de Información / Portada (Descartada)",
        "series": [],
        "modelo_usado": "Descartado (Sin OCR)"
      }
    },
    {
      "pagina": 2,
      "target_id": "A",
      "tipo_juego": "clasificacion",
      "transcripcion": {
        "valido": true,
        "arquero": "Leguiza Marcelo Gabriel",
        "target": "1A",
        "club": "TCAP",
        "categoria": "R M",
        "sin_puntos_registrados": false,
        "series": [
          {"serie": 1, "flechas": ["10", "9", "8"], "suma_parcial_escrita": 27}
        ],
        "totales_planilla": {"total_puntos": 247, "cant_10s": 4, "cant_9s": 6},
        "modelo_usado": "nvidia:nemotron-3.5-parse + llm-refactorer:llama-3.1-70b"
      }
    }
  ]
}
```

---

## 🤖 Agente 3: Validador Lógico y Reconciliador Matemático (v5)
**Objetivo:** Recibir el JSON crudo del Agente 2, limpiar el ruido del OCR, verificar que las matemáticas cierren y deducir números ilegibles basándose en el contexto y las reglas de tiro con arco.

### 🧹 1. Sanitización y Deducción
- **Ruido OCR:** Corrige lecturas típicas como `"6X"` -> `6`, o `"104"` -> `10`.
- **Deducción de Flechas Ilegibles:** Si la IA lee `[2, 3, 'U']` y la suma escrita en el papel es `9`, el Agente 3 deduce automáticamente que `'U'` es un `4`.
- **Confusión 15 vs 16:** Si detecta una flecha leída como 6 pero el total escrito de la serie es 15, asume que el OCR leyó mal y corrige la flecha a 5.

### 📐 2. Reconciliación Matemática y Modalidad
- **Validación Serie por Serie y Totales:** Compara la suma de las flechas contra la suma parcial escrita y contra el total del pie de página.
- **Lógica de Sala vs Aire Libre:** En Sala (Indoor), agrupa el conteo de `10s` como `(X + 10)`. En Aire Libre (Outdoor), diferencia los `10s` puros de las `Xs`.
- **Deducción de Totales Faltantes:** Si el recuadro del total general no fue leído por el OCR, el Agente 3 lo deduce a partir del total acumulado escrito en la última serie.

### 📊 3. Índice de Certeza y Auditoría
Diferencia el estado de cada planilla en base a un **Score de Certeza (0% a 100%)**:
- `APROBADO_AUTOMATICO` (≥ 90% de certeza, todo cierra matemáticamente).
- `REVISION_RECOMENDADA` / `REQUIERE_REVISION_HUMANA` (hay discrepancias en las sumas).
- `SIN_PUNTOS_CONFIRMADO` (la planilla estaba vacía).

### 📄 Salida (Informe de Auditoría JSON)
```json
{
  "archivo_origen": "planillas_torneo.pdf",
  "resumen_auditoria": {
    "total_cuadrantes_procesados": 2,
    "aprobados_automaticos": 1,
    "requiere_revision_humana": 0,
    "sin_puntos_confirmados": 1
  },
  "resultados_auditados": [
    {
      "pagina": 2,
      "target_id": "A",
      "arquero": "Leguiza Marcelo Gabriel",
      "target": "1A",
      "matematica_valida": true,
      "score_certeza": 100.0,
      "estado_auditoria": "APROBADO_AUTOMATICO",
      "total_oficial_estado": "DEDUCIDO_ULTIMA_SERIE",
      "totales_oficiales_planilla": {"total_puntos": 247, "cant_10s": 4, "cant_9s": 6, "cant_xs": 0},
      "totales_calculados_series": {"total_puntos": 247, "cant_10s_totales": 4, "cant_10s_puras": 4, "cant_9s": 6},
      "deducciones_realizadas": [
        {
          "serie": 4,
          "original": "U",
          "deducido": "4",
          "diferencia_calculada": 4
        }
      ],
      "errores": [],
      "advertencias": [
        "💡 Total en papel (247 pts) deducido del acumulado escrito en la última serie",
        "💡 Serie 4: Flecha ilegible 'U' deducida automáticamente como '4' (Suma escrita 26 - parcial = 4)"
      ]
    }
  ]
}
```