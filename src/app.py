#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 Servidor Principal y Orquestador Web - Sistema de Tiro con Arco (Multi-Agente)

Lanza la interfaz en local en http://localhost:7860.
En esta fase inicial, invoca al Agente 1 (Clasificador y Segmentador por páginas)
y muestra en pantalla:
- Diagnóstico del archivo (Clasificación vs Eliminatoria, Layout, Páginas)
- Vista previa de páginas y recortes de posiciones/cuadrantes generados
- Manifiesto JSON listo para el Agente 2 (OCR / Visión)
"""

import os
import sys
import json
import gradio as gr
from PIL import Image

from agente_1_clasificador_segmentador import AgenteClasificadorSegmentador

agente_1 = AgenteClasificadorSegmentador()

def tipo_juego_manual_map(val):
    if "Clasificación" in val:
        return "clasificacion"
    elif "Eliminatoria" in val:
        return "eliminatoria"
    return None

def procesar_con_agente_1(file_obj, tipo_juego_override):
    if file_obj is None:
        return "⚠️ Por favor, selecciona un archivo (PDF o Imagen).", [], "{}"

    file_path = file_obj.name
    tipo_manual = None if tipo_juego_override == "Automático" else tipo_juego_manual_map(tipo_juego_override)

    try:
        manifiesto = agente_1.procesar_documento(file_path, tipo_juego_manual=tipo_manual)
        
        # Preparar resumen de diagnóstico
        resumen_md = f"### 📊 Diagnóstico del Agente 1\n"
        resumen_md += f"- **Archivo Origen:** `{manifiesto['archivo_origen']}`\n"
        resumen_md += f"- **Total de Páginas Renderizadas:** `{manifiesto['total_paginas']}`\n"
        resumen_md += f"- **Recortes Generados (Tareas Agente 2):** `{len(manifiesto['tareas_agente2'])}` \n\n"

        # Cargar imágenes de vista previa de los recortes
        gallery_images = []
        for tarea in manifiesto["tareas_agente2"]:
            crop_path = tarea["ruta_recorte"]
            if os.path.exists(crop_path):
                slot_id = tarea.get("posicion_slot", tarea.get("target_id", "Slot"))
                label = f"Pág {tarea['pagina']} - {slot_id} ({tarea['tipo_juego'].capitalize()})"
                gallery_images.append((crop_path, label))

        json_str = json.dumps(manifiesto, indent=2, ensure_ascii=False)
        return resumen_md, gallery_images, json_str

    except Exception as e:
        err_msg = f"❌ Error durante el procesamiento con Agente 1: {str(e)}"
        return err_msg, [], "{}"

with gr.Blocks(title="🎯 Orquestador Multi-Agente - Tiro con Arco") as demo:
    gr.Markdown("# 🎯 Sistema Multi-Agente de Transcripción - Tiro con Arco")
    gr.Markdown("Servidor principal web. Actualmente ejecuta el **Agente 1: Clasificador y Segmentador por Páginas**.")

    with gr.Row():
        with gr.Column(scale=1):
            file_input = gr.File(label="Subir Planilla (PDF o Imagen)", file_types=[".pdf", ".png", ".jpg", ".jpeg"])
            tipo_override = gr.Dropdown(
                label="Modo de Juego",
                choices=["Automático", "Clasificación (4 Arqueros)", "Eliminatoria (2 Arqueros / Duelos)"],
                value="Automático"
            )
            btn_process = gr.Button("🚀 Ejecutar Agente 1 (Segmentar Documento)", variant="primary")

        with gr.Column(scale=2):
            status_box = gr.Markdown(value="Esperando archivo para procesar...")
            gallery_out = gr.Gallery(label="✂️ Recortes Generados por Agente 1", columns=2, height=350)
            json_out = gr.Code(label="📄 Manifiesto JSON Generado (Entrada para Agente 2)", language="json")

    btn_process.click(
        fn=procesar_con_agente_1,
        inputs=[file_input, tipo_override],
        outputs=[status_box, gallery_out, json_out]
    )

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Servidor Principal Multi-Agente - Tiro con Arco")
    print("🌍 Abre tu navegador en: http://localhost:7860")
    print("=" * 60)
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
