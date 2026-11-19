# 🎯 Sistema Multi-Agente de IA para Digitalización y Validación de Planillas de Tiro con Arco (FATARCO / World Archery)

Sistema inteligente automatizado basado en una arquitectura **Multi-Agente Modular** y **Modelos Multimodales de Visión-Lenguaje (VLM)** para la clasificación, segmentación en alta definición, transcripción OCR adaptativa, auditoría aritmética estricta y cotejo web con resultados oficiales de competencia.

---

## 📐 Especificación del Agente de IA (PEAS)

| Componente | Descripción |
| :--- | :--- |
| **Performance (Métricas)** | Precisión por flecha (🎯 96.5%), Tasa de error (3.5%), Planillas 100% exactas (91.7%), Coincidencia de total (95.8%), Tasa de recuperación de ausencias (DNS). |
| **Environment (Entorno)** | Planillas manuscritas en PDF/JPG (rondas de clasificación y eliminatorias), portal web de resultados (`arquerosonline.com.ar`), dataset de Verdad Terreno (CSV). |
| **Actuators (Actuadores)** | Generador de cuadrantes optimizados, motor de inferencia VLM, validador aritmético, scraper web, visor HTML interactivo en Gradio con miniaturas HD. |
| **Sensors (Sensores)** | Ingesta de archivos PDF/imágenes (`pypdfium2`, `OpenCV`), API de Retrieval Multimodal (NVIDIA Nemotron 3.5 Parse), cliente Ollama Local (`qwen2-vl`), Tesseract OCR. |

---

## 🔄 Flujo Secuencial del Pipeline Multi-Agente

El procesamiento sigue un orden estrictamente desacoplado de 7 etapas:

```text
┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌──────────────┐    ┌───────────┐    ┌──────────────┐
│  Paso 0   │ ──>│  Paso 1   │ ──>│  Paso 2   │ ──>│  Paso 3   │ ──>│  Métricas    │ ──>│  Paso 4   │ ──>│  Métricas    │
│ Carga/HD  │    │ Agente 1  │    │ Agente 2  │    │ Agente 3  │    │ Pre-Scraping │    │ Agente 4  │    │ Post-Scraping│
└───────────┘    └───────────┘    └───────────┘    └───────────┘    └──────────────┘    └───────────┘    └──────────────┘

```

1. **🖼️ Paso 0 — Carga y Renderizado HD:** Ingesta de archivos PDF o imágenes con renderizado de escala suave (`scale=3`, 300 DPI) para preservar la nitidez de trazos manuscritos.
2. **✂️ Paso 1 — Agente 1 (Clasificación & Segmentación):** Inspección de layout (`clasificacion_4`, `clasificacion_2`, `eliminatoria_2`, `info`) y división automatizada de cuadrantes por arquero.
3. **👁️ Paso 2 — Agente 2 (Extractor OCR & VLM Multimodal):** Inferencia vision-language con resiliencia en cascada (NVIDIA Nemotron 3.5 Parse ➔ Ollama Local ➔ Fallback Tesseract).
4. **⚖️ Paso 3 — Agente 3 (Validador Lógico & Reconciliación):** Verificación matemática flecha a flecha, control de certeza (100% vs. Revisión) y cotejo con el padrón local de arqueros.
5. **📊 Métricas e Inspección de Estadísticas Iniciales (Pre-Scraping):** Evaluación cuantitativa de precisión y tasa de error del pipeline interno (Agentes 1 a 3) contra la Verdad Terreno en CSV.
6. **🌐 Paso 4 — Agente 4 (Verificador Web & Scraper Oficial):** Consulta automatizada a `arquerosonline.com.ar`, emparejamiento por huella unívoca `(Categoría + Serie 1 + Serie 2)` y detección de ausencias (`DNS`).
7. **📊 Métricas y Estadísticas Finales (Post-Scraping / Delta de Impacto):** Recálculo de métricas comparativas organizadas por prioridad o cantidad de incidencias para presentar las sugerencias de corrección al operador humano.

---

## 📈 Evaluación Cuantitativa y Benchmark de Eficacia

### 🌐 Impacto Significativo de la Mejora en el Scraping Web (Agente 4)

La optimización del módulo de scraping sobre `arquerosonline.com.ar` representó una mejora crítica en la confiabilidad global del sistema:

* **Resolución de pérdidas y errores del OCR local:** Previamente, al depender únicamente de la extracción óptica local, se producían pérdidas parciales en nombres de arqueros, omisiones o deformaciones en los nombres de clubes y casos donde el puntaje total (o de turno) quedaba mal relevado por el OCR o resultaba ambiguo frente a la suma manuscrita de la planilla.
* **Certeza sobre los valores reales y verdaderos:** Al incorporar el relevamiento web completo (soporte de carga diferida AJAX, resolución de sesión y contraste por Turno 1, Turno 2 y categoría), el sistema dispone de una **fuente de verdad oficial verificable** para cada competencia.
* **Trazabilidad entre dato cierto y dato erróneo:** Gracias a este cotejo en vivo, el operador puede distinguir de forma inequívoca **cuándo un valor extraído es cierto** (`🟢 VALIDADO_OK_WEB`) y **cuándo no es cierto** (`🟡 DISCREPANCIA_CON_SUGERENCIA` o `🔴 ALERTA_PLANILLA_OMISA`), identificando con exactitud diferencias de puntaje por turno, planillas omitidas por el OCR o variaciones en el nombre del arquero y del club antes de consolidar los resultados.

### Métricas de Rendimiento del Pipeline Actual (Agente 3)

* **Precisión por Flecha:** `96.5%` (flechas transcritas exactamente igual a la Verdad Terreno).
* **Tasa de Error por Flecha:** `3.5%` (discrepancias detectadas en anotación o lectura).
* **Planillas 100% Exactas:** `91.7%` (planillas sin un solo error de trascripción).
* **Coincidencia de Puntaje Total:** `95.8%` (coincidencia perfecta en el total acumulado de la competencia).

### Tabla Comparativa contra Línea de Base (Benchmark Oficial)

| Modelo / Pipeline | Precisión Flecha (%) | Error Flecha (%) | Planillas Exactas (%) | Precisión Total (%) |
| --- | --- | --- | --- | --- |
| ⚠️ **Tesseract OCR (Línea de Base Local)** | `68.2%` | `31.8%` | `41.7%` | `58.3%` |
| 🔍 **Nemotron 3.5 Parse (VLM sin Refactorizador)** | `88.4%` | `11.6%` | `75.0%` | `83.3%` |
| 🚀 **Pipeline Multi-Agente Actual (VLM + LLM + Agente 3)** | **`96.5%`** | **`3.5%`** | **`91.7%`** | **`95.8%`** |

---

## 🔍 Ejemplos de Salida de los Agentes

### ✂️ Agente 1 (Manifiesto de Layout y Segmentación)

```json
{
  "archivo_origen": "2026-05-03-S-AFPSF-Planillas.pdf",
  "total_paginas": 1,
  "tareas_agente2": [
    {
      "pagina": 1,
      "target_id": "14A",
      "label": "Pág 1 - Pos 14A",
      "tipo_juego": "clasificacion",
      "layout": "clasificacion_4",
      "ruta_recorte": "/data/processed/crops/pag_1_crop_14A.png",
      "es_cuadrante_vacio": false
    }
  ]
}

```

### 👁️ Agente 2 (Inferencia Raw & JSON Refactorizado)

```json
{
  "valido": true,
  "arquero": "Monserrat Ana Gabriela",
  "target": "14A",
  "club": "AA - Academia de Arqueria Asociació",
  "categoria": "B E80",
  "ronda": "1",
  "distancia": "18m",
  "totales_planilla": {
    "total_puntos": 242,
    "cant_10s": 4,
    "cant_9s": 8
  },
  "series": [
    {"serie": 1, "flechas": ["9", "8", "7"], "suma_parcial_escrita": 24},
    {"serie": 2, "flechas": ["10", "9", "8"], "suma_parcial_escrita": 27}
  ],
  "modelo_usado": "nvidia:nemotron-3.5-parse"
}

```

### ⚖️ Agente 3 (Auditoría Lógica y Control de Certeza)

```json
{
  "pagina": 1,
  "target_id": "14A",
  "arquero": "Monserrat Ana Gabriela",
  "score_certeza": 100.0,
  "estado_auditoria": "APROBADO_AUTOMATICO",
  "matematica_valida": true,
  "totales_oficiales_planilla": {"total_puntos": 242, "cant_10s": 4, "cant_9s": 8},
  "totales_calculados_series": {"total_puntos": 242, "cant_10s": 4, "cant_9s": 8},
  "advertencias": [],
  "errores": []
}

```

### 🌐 Agente 4 (Verificador Web & Sugerencias de Corrección)

```json
{
  "pagina": 1,
  "target_id": "14A",
  "arquero_local": "Leguiz",
  "arquero_web_sugerido": "Leguiza Marcelo Gabriel",
  "categoria_web_sugerida": "Recurvo Masculino (RM)",
  "total_web_sugerido": 254,
  "sugerencias": [
    "👤 Sugerencia Nombre Web: 'Leguiza Marcelo Gabriel' vs Local 'Leguiz'",
    "📊 Coincidencia de Huella: Serie 1=124, Serie 2=130 (Total 254 pts)"
  ],
  "estado_web": "🟡 DISCREPANCIA_NOMBRE_WEB",
  "dns_confirmado": false
}

```

---

## 📁 Organización Detallada del Directorio del Proyecto

```text
.
├── Dockerfile                           # Imagen Linux optimizada (Python 3.12 + OpenCV + Tesseract)
├── docker-compose.yml                   # Orquestación de App + Ollama Docker en red privada
├── pyproject.toml                       # Gestión de dependencias Python con uv / pip
├── README.md                            # Documentación integral del sistema
├── .env                                 # Configuración de variables de entorno y API Keys (NVIDIA NIM)
├── data/                                # Almacenamiento local persistente
│   ├── raw/                             # Planillas originales en PDF / JPG
│   ├── processed/                       # Recortes de cuadrantes y verdad terreno (CSV)
│   └── audit/                           # Archivos de auditoría JSON exportados
├── notebooks/                                   # Notebooks Jupyter secuenciales de evidencia y medición
│   ├── 01_exploracion_datos.ipynb               # Inventario de planillas raw y análisis de Verdad Terreno (CSV)
│   ├── 02_segmentacion_agente1.ipynb            # Renderizado 300 DPI, detección de layout y mejora CLAHE (Agente 1)
│   ├── 03_extraccion_ocr_agente2.ipynb          # Comparativa Tesseract vs. VLM Multimodal + Refactorizador (Agente 2)
│   ├── 04_auditoria_logica_agente3.ipynb        # Deducción de flechas, reconciliación 5/6 y certeza (Agente 3)
│   ├── 05_verificacion_web_agente4.ipynb        # Scraping oficial en arquerosonline.com.ar y cotejo por turnos (Agente 4)
│   └── 06_evaluacion_metricas_benchmark.ipynb   # Medición cuantitativa end-to-end, benchmark y latencia por etapa
├── src/
│   └── tiro_arco/                       # Código fuente principal del sistema multi-agente
│       ├── __init__.py
│       ├── app_tiro_con_arco.py         # Orquestador e Interfaz Web Gradio (v80 Responsiva con Navbar)
│       ├── agente_1_clasificador_segmentador.py  # Agente 1 (Layout y segmentación HD)
│       ├── agente_2_ocr_extractor.py              # Agente 2 (Inferencia VLM Multimodal + Fallback)
│       ├── agente_3_validador_conciliador.py      # Agente 3 (Auditoría lógica y certeza)
│       └── agente_4_scraper_resultados.py        # Agente 4 (Verificador Web & Scraping Oficial)
└── tests/                               # Suite de pruebas automatizadas y de regresión
    ├── test_agente1.py
    ├── test_agente2.py
    ├── test_agente3.py
    └── test_agente4.py

```

---

## 🚀 Guía de Instalación y Ejecución

### Opción A: Ejecución Orquestada con Docker (Recomendada)

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
docker compose logs -f archery_multiagent_app
```

### 6. Frenado del contenedor

Para poder frenar el contenedor de su ejecucion, ejecutá en tu terminal:

```bash
docker compose down

```

### Opción B: Ejecución en Entorno Local con Python (`uv`)

```bash
# 1. Instalar dependencias del sistema operativo (Tesseract OCR y OpenCV)
sudo apt update && sudo apt install -y tesseract-ocr tesseract-ocr-spa libgl1 libglib2.0-0

# 2. Sincronizar el entorno Python e iniciar Gradio
uv sync
uv run tiro-con-arco

```

---

## 👤 Autoría y Derechos

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
# Estadisticas actuales
Comparativa contra Línea de Base (Benchmark de Evaluación)
| Modelo / Pipeline |	Precisión Flecha (%) | Error Flecha (%) | Planillas Exactas (%) | Precisión Total (%) |
| - | - | - | - | - |
| ⚠️ Tesseract OCR (Línea de Base Local) | 68.2% | 31.8% | 41.7% | 58.3% |
| 🔍 Nemotron 3.5 Parse (VLM sin Refactorizador) | 88.4% | 11.6% | 75.0% | 83.3% |
| 🚀 Pipeline Multi-Agente Actual (VLM + LLM + Agente 3) | 96.5% | 3.5% | 91.7% | 95.8% |
