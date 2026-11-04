#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 Servidor Principal Multi-Agente Gradio - Tiro con Arco (Agente 1 + Agente 2).
"""

import os
import json
import gradio as gr
from tiro_arco.agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
from tiro_arco.agente_2_ocr_extractor import Agente2OCRExtractor


def ejecutar_pipeline_multiagente(archivo_input, tipo_juego_manual):
    if archivo_input is None:
        return "⚠️ Por favor, selecciona o sube un archivo (PDF o Imagen).", "", None

    ruta_archivo = archivo_input.name if hasattr(archivo_input, 'name') else str(archivo_input)
    
    try:
        agente1 = AgenteClasificadorSegmentador()
        manifiesto1 = agente1.procesar_documento(ruta_archivo, tipo_juego_manual=tipo_juego_manual)
    except Exception as e:
        return f"❌ Error en Agente 1 (Segmentación): {str(e)}", "", None

    try:
        agente2 = Agente2OCRExtractor()
        manifiesto2 = agente2.procesar_manifiesto_agente1(manifiesto1)
    except Exception as e:
        manifiesto2 = {"error": f"Falla en Agente 2: {str(e)}", "transcripciones": []}

    resumen_md = "### 📊 Diagnóstico Multi-Agente (Agente 1 + Agente 2)\n"
    resumen_md += f"- **Archivo Origen:** `{manifiesto1.get('archivo_origen', '')}`\n"
    resumen_md += f"- **Total de Páginas:** `{manifiesto1.get('total_paginas', 0)}`\n"
    resumen_md += f"- **Tareas de Segmentación (Agente 1):** `{len(manifiesto1.get('tareas_agente2', []))}`\n"
    resumen_md += f"- **Transcripciones OCR (Agente 2):** `{len(manifiesto2.get('transcripciones', []))}`\n\n"

    resumen_md += "#### 🎯 Detalle de Transcripciones por Arquero:\n"
    for item in manifiesto2.get("transcripciones", []):
        tr = item.get("transcripcion", {})
        resumen_md += f"- **Página {item.get('pagina')} ({item.get('target_id')}):** Arquero: `{tr.get('arquero', 'N/A')}` | Diana: `{tr.get('target', 'N/A')}` | Modelo: `{tr.get('modelo_usado', 'N/A')}`\n"

    json_str = json.dumps({
        "agente_1_manifiesto": manifiesto1,
        "agente_2_manifiesto": manifiesto2
    }, indent=2, ensure_ascii=False)

    return resumen_md, json_str, manifiesto1


def construir_interfaz():
    with gr.Blocks(title="Sistema Multi-Agente Tiro con Arco") as demo:
        gr.Markdown("# 🎯 Sistema Multi-Agente para Planillas de Tiro con Arco")
        gr.Markdown("Pipeline inteligente: **Agente 1 (Segmentación PDI)** ➔ **Agente 2 (Preprocesamiento & OCR Multimodal NVIDIA NIM)**")

        with gr.Row():
            with gr.Column(scale=1):
                archivo_input = gr.File(label="Subir Planilla (PDF o Imagen PNG/JPG)", file_types=[".pdf", ".png", ".jpg", ".jpeg"])
                tipo_juego_manual = gr.Dropdown(
                    label="Modo Juego (Opcional - Detección Automática por defecto)",
                    choices=["Auto", "clasificacion", "eliminatoria"],
                    value="Auto"
                )
                btn_ejecutar = gr.Button("🚀 Ejecutar Pipeline Multi-Agente", variant="primary")

            with gr.Column(scale=2):
                resumen_output = gr.Markdown(label="Resumen de Diagnóstico")
                json_output = gr.Code(label="Manifiesto Resultante (JSON)", language="json")

        btn_ejecutar.click(
            fn=ejecutar_pipeline_multiagente,
            inputs=[archivo_input, tipo_juego_manual],
            outputs=[resumen_output, json_output]
        )

    return demo


def main():
    print("============================================================")
    print("🚀 Servidor Principal Multi-Agente - Tiro con Arco")
    print("🌍 Abre tu navegador en: http://localhost:7860")
    print("============================================================")
    demo = construir_interfaz()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)


if __name__ == "__main__":
    main()
