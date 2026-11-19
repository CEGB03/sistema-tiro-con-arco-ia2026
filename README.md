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

### Métricas de Rendimiento del Pipeline Actual (Agente 3)
* **Precisión por Flecha:** `96.5%` (flechas transcritas exactamente igual a la Verdad Terreno).
* **Tasa de Error por Flecha:** `3.5%` (discrepancias detectadas en anotación o lectura).
* **Planillas 100% Exactas:** `91.7%` (planillas sin un solo error de trascripción).
* **Coincidencia de Puntaje Total:** `95.8%` (coincidencia perfecta en el total acumulado de la competencia).

### Tabla Comparativa contra Línea de Base (Benchmark Oficial)

| Modelo / Pipeline | Precisión Flecha (%) | Error Flecha (%) | Planillas Exactas (%) | Precisión Total (%) |
| :--- | :---: | :---: | :---: | :---: |
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
├── notebooks/                           # Notebooks Jupyter para benchmark y evaluación
│   └── 01_evaluacion_ocr.ipynb          # Notebook oficial de evaluación contra Verdad Terreno
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
docker compose logs -f archery-app
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
* **Proyecto Capstone:** Inteligencia Artificial (2026).
* **Autor:** Carlos Emanuel Gomez Bonelli.
* **Carrera:** Ingenieria en Informatica (2026).
* **Licencia:** MIT License.
