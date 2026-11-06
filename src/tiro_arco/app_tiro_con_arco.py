#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 Servidor Principal Multi-Agente (v27 - Desacoplamiento Página/Contención y Reintento Selectivo).
"""

import os
import sys
import json
import gradio as gr

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


agente1 = AgenteClasificadorSegmentador()
agente2 = Agente2OCRExtractor()


def generar_vistas(manifiesto_1, manifiesto_2):
    resumen_md = f"### 📊 Diagnóstico Multi-Agente (Reintento Selectivo Activo)\\n\\n"
    resumen_md += f"- **Archivo Origen:** `{manifiesto_1['archivo_origen']}`\\n"
    resumen_md += f"- **Total de Páginas:** `{manifiesto_1['total_paginas']}`\\n"
    resumen_md += f"- **Recortes Generados (Agente 1):** `{len(manifiesto_1['tareas_agente2'])}`\\n"
    resumen_md += f"- **Transcripciones OCR (Agente 2):** `{len(manifiesto_2['transcripciones'])}`\\n\\n"
    resumen_md += "#### 🎯 Detalle de Transcripciones por Arquero:\\n"

    opciones_checkbox = []
    seleccionados_defecto = []

    for t in manifiesto_2.get("transcripciones", []):
        trans = t.get("transcripcion", {})
        modelo = trans.get("modelo_usado", "")
        arquero = trans.get("arquero", "Desconocido")
        target_leido = trans.get("target", "N/A")
        club = trans.get("club", "N/A")
        cat = trans.get("categoria", "N/A")
        
        pag = t.get('pagina')
        pos = t.get('target_id')
        
        lbl_posicion = f"Pág {pag} - Posición {pos}"
        lbl_checkbox = f"{lbl_posicion} (Diana: {target_leido} | Arquero: {arquero})"
        opciones_checkbox.append(lbl_checkbox)

        # Si cayó al Fallback o devolvió datos desconocidos, se selecciona por defecto para reintento
        if "Fallback" in modelo or "Desconocido" in arquero or not trans.get("valido", True):
            seleccionados_defecto.append(lbl_checkbox)

        resumen_md += f"- **{lbl_posicion}:** Diana Leída: `{target_leido}` | Arquero: `{arquero}` | Club: `{club}` | Cat: `{cat}` | Modelo: `{modelo}`\\n"

    manifiesto_combinado = {
        "agente_1_manifiesto": manifiesto_1,
        "agente_2_manifiesto": manifiesto_2
    }

    galeria = []
    for t in manifiesto_2.get("transcripciones", []):
        p = t.get("ruta_recorte_procesada") or t.get("ruta_recorte_original")
        if p and os.path.exists(p):
            target_leido = t.get("transcripcion", {}).get("target", t.get("target_id"))
            sin_p = t.get("transcripcion", {}).get("sin_puntos_registrados", False) or len(t.get("transcripcion", {}).get("series", [])) == 0
            tag_puntos = " [Sin Puntos]" if sin_p else ""
            galeria.append((p, f"Pág {t.get('pagina')} - Pos {t.get('target_id')} (Diana: {target_leido}){tag_puntos}"))

    return resumen_md, json.dumps(manifiesto_combinado, indent=2, ensure_ascii=False), galeria, opciones_checkbox, seleccionados_defecto


def ejecutar_pipeline_multiagente(archivo_input, tipo_manual, page_overrides=None):
    if archivo_input is None:
        return "⚠️ Por favor sube un archivo válido.", "{}", [], gr.CheckboxGroup(choices=[]), [], None, None

    ruta = archivo_input.name
    manifiesto_1 = agente1.procesar_documento(ruta, tipo_juego_manual=tipo_manual, page_overrides=page_overrides)
    manifiesto_2 = agente2.procesar_manifiesto_agente1(manifiesto_1)

    resumen_md, json_str, galeria, opciones, seleccionados = generar_vistas(manifiesto_1, manifiesto_2)

    return (
        resumen_md,
        json_str,
        galeria,
        gr.CheckboxGroup(choices=opciones, value=seleccionados, label="Seleccionar Arqueros a Reintentar OCR"),
        manifiesto_1,
        manifiesto_2
    )


def reintentar_ocr_seleccionados(seleccionados, manifiesto_1, manifiesto_2):
    if not manifiesto_1 or not manifiesto_2:
        return "⚠️ No hay un manifiesto previo cargado.", "{}", [], gr.CheckboxGroup(choices=[]), manifiesto_1, manifiesto_2

    if not seleccionados:
        resumen_md, json_str, galeria, opciones, selec = generar_vistas(manifiesto_1, manifiesto_2)
        return resumen_md, json_str, galeria, gr.CheckboxGroup(choices=opciones, value=selec), manifiesto_1, manifiesto_2

    print(f"[UI] 🔄 Solicitando reintento de OCR para: {seleccionados}")
    manifiesto_2_actualizado = agente2.reintentar_tareas_especificas(manifiesto_1, manifiesto_2, seleccionados)

    resumen_md, json_str, galeria, opciones, selec = generar_vistas(manifiesto_1, manifiesto_2_actualizado)

    return (
        resumen_md,
        json_str,
        galeria,
        gr.CheckboxGroup(choices=opciones, value=selec, label="Seleccionar Arqueros a Reintentar OCR"),
        manifiesto_1,
        manifiesto_2_actualizado
    )


def build_ui():
    with gr.Blocks(title="🎯 Sistema Multi-Agente - Tiro con Arco (v27)") as demo:
        gr.Markdown("# 🎯 Sistema Multi-Agente - Tiro con Arco (v27)")
        gr.Markdown("Segmentación Física por Posición Espacial (Agente 1) + Extracción OCR e Identificación de Contención/Diana (Agente 2).")

        state_manifiesto_1 = gr.State(None)
        state_manifiesto_2 = gr.State(None)

        with gr.Row():
            with gr.Column(scale=1):
                file_input = gr.File(label="Subir Planilla (Imagen PNG/JPG o PDF)", file_types=[".png", ".jpg", ".jpeg", ".pdf"])
                tipo_manual = gr.Dropdown(
                    label="Modo de Juego Manual (Opcional)",
                    choices=["Auto", "info", "eliminatoria_2", "clasificacion_1", "clasificacion_2_lado", "clasificacion_2_arriba", "clasificacion_4"],
                    value="Auto"
                )
                btn_run = gr.Button("🚀 Ejecutar Pipeline Multi-Agente", variant="primary")
                
                gr.Markdown("---")
                gr.Markdown("### 🔄 Reintento Selectivo")
                checkbox_reintento = gr.CheckboxGroup(choices=[], label="Seleccionar Arqueros a Reintentar OCR")
                btn_reintentar = gr.Button("🔄 Reintentar OCR Seleccionados", variant="secondary")

            with gr.Column(scale=2):
                diagnostico_out = gr.Markdown("Esperando ejecución...")
                galeria_out = gr.Gallery(label="Recortes Procesados", columns=2)
                json_out = gr.Code(label="Manifiesto JSON Completo (Agente 1 + Agente 2)", language="json")

        btn_run.click(
            fn=ejecutar_pipeline_multiagente,
            inputs=[file_input, tipo_manual],
            outputs=[diagnostico_out, json_out, galeria_out, checkbox_reintento, state_manifiesto_1, state_manifiesto_2]
        )

        btn_reintentar.click(
            fn=reintentar_ocr_seleccionados,
            inputs=[checkbox_reintento, state_manifiesto_1, state_manifiesto_2],
            outputs=[diagnostico_out, json_out, galeria_out, checkbox_reintento, state_manifiesto_1, state_manifiesto_2]
        )

    return demo


def main():
    print("=" * 60)
    print("🚀 Servidor Principal Multi-Agente (v27) - Tiro con Arco")
    print("🌍 Abre tu navegador en: http://localhost:7860")
    print("=" * 60)
    demo = build_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)


if __name__ == "__main__":
    main()
