#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 Aplicación Principal - Orquestador Multi-Agente (Gradio UI).
Sistema de Reconocimiento y Validacion de Planillas de Tiro con Arco.
"""

import os
import sys
import json
import tempfile
import pandas as pd
import gradio as gr

# Soporte para ejecucion como paquete (tiro_arco) o como script directo
try:
    from tiro_arco.agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
    from tiro_arco.agente_2_ocr_extractor import Agente2OCRExtractor
except ImportError:
    try:
        from .agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
        from .agente_2_ocr_extractor import Agente2OCRExtractor
    except ImportError:
        from agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
        from agente_2_ocr_extractor import Agente2OCRExtractor


def procesar_planilla_completa(archivo_entrada, api_key_input=""):
    if not archivo_entrada:
        return "⚠️ Por favor, sube una imagen o archivo PDF de la planilla.", None, None, ""

    ruta_archivo = archivo_entrada if isinstance(archivo_entrada, str) else archivo_entrada.name
    api_key = api_key_input.strip() if api_key_input else None

    # 1. Agente 1: Clasificación y Segmentación
    agente1 = AgenteClasificadorSegmentador()
    manifiesto1 = agente1.procesar_documento(ruta_archivo)

    # 2. Agente 2: Preprocesamiento y Extracción OCR
    agente2 = Agente2OCRExtractor(api_key=api_key)
    manifiesto2 = agente2.procesar_manifiesto_agente1(manifiesto1)

    # 3. Resumen y Consolidacion
    resumen_md = "### 📊 Diagnóstico Multi-Agente (Agente 1 + Agente 2)"
    resumen_md += f"- **Archivo Origen:** `{manifiesto1.get('archivo_origen', '')}`"
    resumen_md += f"- **Total de Páginas:** `{manifiesto1.get('total_paginas', 0)}`"
    resumen_md += f"- **Tareas de Segmentación (Agente 1):** `{len(manifiesto1.get('tareas_agente2', []))}`"
    resumen_md += f"- **Transcripciones OCR (Agente 2):** `{len(manifiesto2.get('transcripciones', []))}`"

    # Construir Tabla de Datos
    filas = []
    for item in manifiesto2.get("transcripciones", []):
        ocr = item.get("transcripcion", {})
        tot_escritos = ocr.get("totales_planilla_escritos", {})
        tot_calc = ocr.get("totales_planilla_calculados", {})
        cotejo = "✅ Coincide" if ocr.get("cotejo_total_coincide", False) else "⚠️ Discrepancia"
        
        filas.append({
            "Página": item.get("pagina"),
            "Target ID": item.get("target_id"),
            "Tipo": item.get("tipo_juego"),
            "Arquero": ocr.get("arquero", "N/A"),
            "Club": ocr.get("club", "N/A"),
            "Categoría": ocr.get("categoria", "N/A"),
            "Puntos Escritos": tot_escritos.get("total_puntos", 0),
            "Puntos Calculados": tot_calc.get("total_puntos", 0),
            "10s / Xs": f"{tot_calc.get('cant_10s', 0)}",
            "9s": f"{tot_calc.get('cant_9s', 0)}",
            "Estado Cotejo": cotejo,
            "Modelo OCR": ocr.get("modelo_usado", "N/A")
        })

    df_resumen = pd.DataFrame(filas) if filas else pd.DataFrame()

    json_manifest = json.dumps({
        "agente_1_clasificacion": manifiesto1,
        "agente_2_transcripcion": manifiesto2
    }, indent=2, ensure_ascii=False)

    return resumen_md, df_resumen, json_manifest, json_manifest


def construir_interfaz():
    with gr.Blocks(title="🎯 Sistema IA Tiro con Arco 2026") as demo:
        gr.Markdown("# 🎯 Sistema Multi-Agente de Reconocimiento y Validación de Planillas")
        gr.Markdown("Flujo automatizado: **Agente 1** (Segmentación OpenCV) + **Agente 2** (Multimodal Vision / OCR).")

        with gr.Row():
            with gr.Column(scale=1):
                input_file = gr.File(label="📄 Cargar Planilla (PDF o PNG/JPG)")
                input_api_key = gr.Textbox(label="🔑 NVIDIA API Key (Opcional si está en .env)", type="password")
                btn_procesar = gr.Button("🚀 Procesar Planilla", variant="primary")

            with gr.Column(scale=2):
                output_resumen = gr.Markdown()
                output_df = gr.Dataframe(label="📋 Resumen de Arqueros y Transcripción")
                output_json_view = gr.Code(label="🔍 Manifiesto JSON Consolidado (Agente 1 + Agente 2)", language="json")
                output_json_hidden = gr.Textbox(visible=False)

        btn_procesar.click(
            fn=procesar_planilla_completa,
            inputs=[input_file, input_api_key],
            outputs=[output_resumen, output_df, output_json_view, output_json_hidden]
        )

    return demo


def main():
    demo = construir_interfaz()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)


if __name__ == "__main__":
    main()
