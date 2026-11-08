#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 Servidor Principal Multi-Agente (v31 - Flujo Interactivo en 2 Pasos & Clasificación Completa).
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


def ejecutar_paso1(archivo_input, tipo_manual, page_overrides=None):
    if archivo_input is None:
        return "⚠️ Por favor sube un archivo válido.", gr.CheckboxGroup(choices=[]), [], None

    ruta = archivo_input.name
    manifiesto_1 = agente1.procesar_documento(ruta, tipo_juego_manual=tipo_manual, page_overrides=page_overrides)

    tareas = manifiesto_1.get("tareas_agente2", [])
    
    resumen_md = "### ✂️ **Paso 1 Completado:** Clasificación y Segmentación por Cuadrantes\n\n"
    resumen_md += f"- **Archivo Origen:** `{manifiesto_1['archivo_origen']}`\n"
    resumen_md += f"- **Total de Páginas:** `{manifiesto_1['total_paginas']}`\n"
    resumen_md += f"- **Cuadrantes/Recortes Detectados (Agente 1):** `{len(tareas)}`\n\n"
    resumen_md += "👇 **Instrucciones para el Paso 2:**\n"
    resumen_md += "Revisa la galería de recortes a la derecha. Selecciona abajo qué cuadrantes deseas procesar con el **Agente 2 (OCR)** y haz clic en **👁️ Paso 2: Ejecutar OCR en Seleccionados**.\n"

    opciones = []
    galeria = []

    for t in tareas:
        p = t.get("ruta_recorte")
        lbl = t.get("label", f"Pág {t.get('pagina')} - Pos {t.get('target_id')}")
        tipo_j = t.get("tipo_juego", "clasificacion")
        layout = t.get("layout", "4_arqueros")
        
        opciones.append((f"{lbl} ({tipo_j.capitalize()} - {layout})", lbl))
        if p and os.path.exists(p):
            galeria.append((p, f"{lbl} [{tipo_j.capitalize()}]"))

    # Seleccionados por defecto: todos los cuadrantes
    valores_defecto = [lbl for _, lbl in opciones]

    return (
        resumen_md,
        gr.CheckboxGroup(choices=opciones, value=valores_defecto, label="Seleccionar Cuadrantes para Inferencia OCR"),
        galeria,
        manifiesto_1
    )


def generar_vistas_paso2(manifiesto_1, manifiesto_2, seleccionados):
    resumen_md = "### 📊 Diagnóstico Multi-Agente (Paso 2 - OCR completado)\n\n"
    resumen_md += f"- **Archivo Origen:** `{manifiesto_1['archivo_origen']}`\n"
    resumen_md += f"- **Total de Páginas:** `{manifiesto_1['total_paginas']}`\n"
    resumen_md += f"- **Recortes Generados (Agente 1):** `{len(manifiesto_1['tareas_agente2'])}`\n"
    resumen_md += f"- **Cuadrantes Procesados con OCR (Agente 2):** `{len(manifiesto_2['transcripciones'])}` de `{len(seleccionados)}` seleccionados\n\n"
    resumen_md += "#### 🎯 Detalle de Transcripciones por Arquero:\n\n"
    
    resumen_md += "| Posición | Diana | Arquero | Club | Cat | Estado / Modelo |\n"
    resumen_md += "| :--- | :---: | :--- | :--- | :---: | :--- |\n"

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
        lbl_posicion = t.get('label', f"Pág {pag} - Pos {pos}")
        
        sin_p = trans.get("sin_puntos_registrados", False) or len(trans.get("series", [])) == 0
        is_info = (t.get("layout") == "portada" or t.get("tipo_juego") == "info")
        
        if is_info:
            lbl_estado = " [Info/Portada]"
        elif sin_p:
            lbl_estado = " [Sin Puntos]"
        else:
            lbl_estado = ""
        
        opciones_checkbox.append((f"{lbl_posicion} (Diana: {target_leido} | Arquero: {arquero}){lbl_estado}", lbl_posicion))

        if "Fallback" in modelo or "Desconocido" in arquero or not trans.get("valido", True):
            seleccionados_defecto.append(lbl_posicion)

        if is_info:
            estado_modelo = "ℹ️ **Página de Información / Portada**"
        elif sin_p:
            estado_modelo = "⚠️ **Sin Puntos Registrados**"
        elif "Fallback" in modelo:
            estado_modelo = f"⚠️ `{modelo}`"
        else:
            estado_modelo = f"✅ `{modelo}`"

        resumen_md += f"| **{lbl_posicion}** | `{target_leido}` | **{arquero}** | {club} | `{cat}` | {estado_modelo} |\n"

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


def ejecutar_paso2(seleccionados, manifiesto_1, manifiesto_2_previo):
    if not manifiesto_1:
        return "⚠️ Primero debes ejecutar el Paso 1 para segmentar el documento.", "{}", [], gr.CheckboxGroup(choices=[]), manifiesto_1, None

    if not seleccionados:
        return "⚠️ Por favor selecciona al menos un cuadrante para realizar el OCR.", "{}", [], gr.CheckboxGroup(choices=[]), manifiesto_1, None

    print(f"[UI] 👁️ Ejecutando Paso 2 (OCR) para {len(seleccionados)} cuadrante(s): {seleccionados}")

    if manifiesto_2_previo is None:
        manifiesto_1_filtrado = {
            "archivo_origen": manifiesto_1.get("archivo_origen"),
            "total_paginas": manifiesto_1.get("total_paginas"),
            "tareas_agente2": []
        }
        for t in manifiesto_1.get("tareas_agente2", []):
            pag = str(t.get('pagina'))
            target_pos = str(t.get('target_id'))
            lbl = t.get('label', f"Pág {pag} - Pos {target_pos}")
            
            match = False
            for sel in seleccionados:
                if sel == lbl or sel.startswith(lbl) or lbl in sel:
                    match = True
                    break
            if match:
                manifiesto_1_filtrado["tareas_agente2"].append(t)

        manifiesto_2 = agente2.procesar_manifiesto_agente1(manifiesto_1_filtrado)
    else:
        manifiesto_2 = agente2.reintentar_tareas_especificas(manifiesto_1, manifiesto_2_previo, seleccionados)

    resumen_md, json_str, galeria, opciones, selec_def = generar_vistas_paso2(manifiesto_1, manifiesto_2, seleccionados)

    return (
        resumen_md,
        json_str,
        galeria,
        gr.CheckboxGroup(choices=opciones, value=selec_def, label="Cuadrantes Procesados (Seleccionar para Reintentar OCR)"),
        manifiesto_1,
        manifiesto_2
    )


def build_ui():
    with gr.Blocks(title="🎯 Sistema Multi-Agente - Tiro con Arco (v31)") as demo:
        gr.Markdown("# 🎯 Sistema Multi-Agente - Tiro con Arco (v31)")
        gr.Markdown("Flujo Interactivo en 2 Pasos con Clasificación Completa: **Información/Portada**, **Eliminatoria (Duelos)** y **Clasificación (1, 2, 4 Arqueros)**.")

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
                btn_paso1 = gr.Button("✂️ Paso 1: Clasificar y Segmentar Cuadrantes", variant="primary")
                
                gr.Markdown("---")
                gr.Markdown("### 👁️ Paso 2: Selección y OCR")
                checkbox_cuadrantes = gr.CheckboxGroup(choices=[], label="Seleccionar Cuadrantes para Inferencia OCR")
                btn_paso2 = gr.Button("👁️ Paso 2: Ejecutar OCR en Seleccionados", variant="secondary")

            with gr.Column(scale=2):
                diagnostico_out = gr.Markdown("Esperando ejecución del Paso 1...")
                galeria_out = gr.Gallery(label="Recortes / Cuadrantes Detectados", columns=2)
                json_out = gr.Code(label="Manifiesto JSON Completo (Agente 1 + Agente 2)", language="json")

        btn_paso1.click(
            fn=ejecutar_paso1,
            inputs=[file_input, tipo_manual],
            outputs=[diagnostico_out, checkbox_cuadrantes, galeria_out, state_manifiesto_1]
        )

        btn_paso2.click(
            fn=ejecutar_paso2,
            inputs=[checkbox_cuadrantes, state_manifiesto_1, state_manifiesto_2],
            outputs=[diagnostico_out, json_out, galeria_out, checkbox_cuadrantes, state_manifiesto_1, state_manifiesto_2]
        )

    return demo


def main():
    print("=" * 60)
    print("🚀 Servidor Principal Multi-Agente (v31) - Tiro con Arco")
    print("🌍 Abre tu navegador en: http://localhost:7860")
    print("=" * 60)
    demo = build_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)


if __name__ == "__main__":
    main()
