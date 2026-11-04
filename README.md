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
│    ├── agente_1_clasificador_segmentador.py ← Agente 1 (Segmentación visual OpenCV/Pillow)
│    ├── ocr_tiro_con_arco.py ← Motor de extracción OCR (NVIDIA NIM) 
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

### 🛠️ Instalación y Gestión de Dependencias con `uv`

El proyecto utiliza **`uv`** para la gestión rápida y reproducible del entorno virtual y las dependencias:

```shell
# Sincronizar el entorno e instalar dependencias del proyecto
uv sync
```

> [!CAUTION]
> Se requiere tener configurada la variable `NVIDIA_API_KEY` en el archivo `.env` local (se puede obtener gratuitamente en el portal de NVIDIA NIM).

---

### 🚀 Ejecución del Sistema Multi-Agente

Para iniciar el servidor principal y la interfaz web interactiva en `http://localhost:7860`, ejecuta:

```shell
uv run tiro-con-arco
```

*(Si utilizas un entorno virtual propio previamente activado como `venv_ia_proyecto`, puedes usar `uv run --active tiro-con-arco` o lanzar directamente `uv run tiro-con-arco`).*


# Agentes

## 🤖 Agente 1: Clasificador y Segmentador Semántico por Páginas 
**Objetivo:** Recibir el archivo de entrada (**PDF multipágina** o **Imagen PNG/JPG**), procesar página por página mediante análisis híbrido (**extracción de texto semántico y visión por computadora con OpenCV/Pillow**), clasificar la estructura del documento y segmentar ordenadamente las zonas de cada arquero, emitiendo un **manifiesto JSON con la cola de trabajo estandarizada** para el Agente 2.

### 🧠 Lógica de Clasificación Semántica (Text-Anchored Classification)
A diferencia de los cortes geométricos estáticos, el Agente 1 analiza anclas de texto e identificadores clave en la página completa:
- **Eliminatoria (`2_arqueros` / Duelos Directos):** Detecta la presencia de marcas exclusivas de enfrentamientos directos como `"Ganador"`, `"Total Set Points"`, `"S.O."` (Shoot-Off), `"Contención XA/XB"` o `"Posición X"` (puesto en la llave/bracket).
- **Clasificación (`4_arqueros` o `1_arquero`):** Detecta sufijos de diana/contención física (`XA`, `XB`, `XC`, `XD`).
- Si encuentra 3 o 4 combinaciones: clasifica como `4_arqueros` (matriz 2x2).
- Si encuentra 1 sola combinación: clasifica como `1_arquero` (planilla individual).
- **Portada / Separador (`portada`):** Si la página no contiene grillas de puntuación ni anclas de tiro (páginas de título o reglamentos), la clasifica como `sin_modo`.

### ✂️ Estrategia de Segmentación y Recorte Posicional
El Agente 1 no asume números fijados de diana (evita hardcodear `"1A"`, `"1B"`), sino **etiquetas posicionales dinámicas**:
- **Clasificación (4 Arqueros):** Asigna slots posicionales `Pos_A`, `Pos_B`, `Pos_C` y `Pos_D`. Aplica un **solape vertical del 12%** (`y = 38%` de la altura) para los cuadrantes inferiores (`Pos_C` y `Pos_D`), garantizando que la caja superior con el nombre del atleta nunca quede recortada.
- **Eliminatoria (2 Arqueros / Duelos):** Asigna slots `Puesto_1` (Izquierda) y `Puesto_2` (Derecha). Realiza el corte desde el borde superior absoluto (`y = 0`), manteniendo visibles el nombre del arquero, club, categoría y la tabla de *Set Points*.
- **Individual (1 Arquero):** Conserva el **100% de la imagen original** sin recortar (`posicion_slot: "Individual"`).
- **Portada:** Conserva la vista entera etiquetada como `posicion_slot: "Portada"`.

### 📄 Salida (Manifiesto JSON)
Genera una cola de trabajo estructurada en disco con el siguiente formato:
```json 
{ 
     "archivo_origen": "torneo_copa_san_francisco.pdf", 
     "total_paginas": 3, 
     "tareas_agente2": [
          {
               "pagina": 1,
               "posicion_slot": "Portada",
               "tipo_juego": "sin_modo",
               "layout": "portada",
               "ruta_recorte": "/tmp/archery_agent1/pag_1_crop_Portada.png"
          },
          { 
               "pagina": 2, 
               "posicion_slot": "Pos_A",
               "tipo_juego": "clasificacion",
               "layout": "4_arqueros",
               "ruta_recorte": "/tmp/archery_agent1/pag_2_crop_Pos_A.png"
          },
          { 
               "pagina": 3,
               "posicion_slot": "Puesto_1",
               "tipo_juego": "eliminatoria",
               "layout": "2_arqueros",
               "ruta_recorte": "/tmp/archery_agent1/pag_3_crop_Puesto_1.png"
          }
     ] 
}
```

## 🤖 Agente 2: Preprocesador de Imagen y Extractor OCR Multimodal (NVIDIA NIM)

**Objetivo:** Tomar las imágenes recortadas por el Agente 1, aplicar un pipeline de procesamiento digital de imágenes (PDI) para maximizar la legibilidad del trazo manuscrito y transcribir con precisión todos los datos (números, letras, encabezados y puntuaciones) utilizando modelos multimodales de visión por computadora alojados en **NVIDIA NIM**.

---

### 🎨 1. Pipeline de Preprocesamiento de Imagen (OpenCV & Pillow)
Antes de enviar el recorte al modelo de visión, la imagen atraviesa una fase de limpieza visual para eliminar ruido, sombras del escaneo y arrugas del papel:
- **CLAHE (Contrast Limited Adaptive Histogram Equalization):** Realce de contraste local adaptativo para rescatar escrituras suaves en lápiz o tinta azul/negra tenue.
- **Filtro Bilateral / Denoising:** Supresión de tramas de fondo e imperfecciones del papel sin suavizar ni deformar los bordes de los números.
- **Deskew (Alineación Estructural):** Corrección fina de inclinación horizontal para garantizar que las líneas de las series queden perfectamente alineadas.
- **Binarización y Escalado Normalizado:** Conversión a alto contraste manteniendo una resolución óptima para inferencia multimodal.

---

### 🧠 2. Inferencia Multimodal & Cadena de Fallback (NVIDIA NIM)
El agente consulta la API de NVIDIA NIM mediante un **prompt estructurado en JSON Schema** diferenciado por tipo de juego:
- **Planillas de Clasificación:** Extrae el encabezado (Arquero, Club, Categoría, Diana/Target `1A..D`), las 10 series de 3 flechas, sumas parciales, total general y conteo de `10s` y `9s`.
- **Planillas de Eliminatorias:** Extrae el puesto de la grilla (`Posición X`), puntos por set en enfrentamientos directos, `Total Set Points`, el indicador de `Ganador` y puntuación de empate `S.O.` (Shoot-Off).

#### 🔄 Resiliencia por Cadena de Fallback Automática
Para evitar interrupciones por saturación o límites de tasa (HTTP 429 / 504 Timeout), el motor conmuta automáticamente en tiempo real entre la suite multimodal de NVIDIA NIM:
1. `meta/llama-3.2-11b-vision-instruct`
2. `moonshotai/kimi-k3`
3. `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`
4. `google/paligemma`

---

### 📄 3. Salida (Manifiesto de Transcripción JSON)
El Agente 2 genera un archivo JSON con todos los datos extraídos de cada arquero, sirviendo como entrada directa para la validación y corrección aritmética del **Agente 3**:

```json
{
  "archivo_origen": "2026-05-03-S-AFPSF-Planillas-20260505_recortado.pdf",
  "total_transcripciones": 2,
  "transcripciones": [
    {
      "pagina": 3,
      "posicion_slot": "Pos_A",
      "tipo_juego": "clasificacion",
      "arquero": "Leguiza Marcelo Gabriel",
      "target": "1A",
      "club": "TCAP",
      "series": [
        {"serie": 1, "flechas":, "suma_parcial": 27, "total_acumulado": 27},
        {"serie": 2, "flechas":, "suma_parcial": 28, "total_acumulado": 55}
      ],
      "totales_planilla": {"total_puntos": 247, "cant_10s": 4, "cant_9s": 4}
    }
  ]
}