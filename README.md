# sistema-tiro-con-arco-ia2026

## Ayudamemoria de organizacion
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




### Creacion del entorno virtual para asilar las dependencias

```Shell
python -m venv venv
```

### Instalacion de dependencias

```Shell
pip install -r requirements.txt
```

> [!CAUTION]
> Se necesita tener una NVIDIA_API_KEY que se puede reclamar gratis en su pagina web (al momento del desarrollo 18/11/2026)

### Ejecucion

```Shell
python src/app_tiro_con_arco.py
```


# Agentes

## Agente 1: clasificador y segmentador

**Objetivo:** Recibir el archivo (PDF multipágina o Imagen), procesar página por página, detectar el tipo de planilla (**Clasificación** vs  **Eliminatoria** ) y segmentar ordenadamente los cuadrantes de arqueros con OpenCV/Pillow, emitiendo un manifiesto JSON con la cola de trabajo
