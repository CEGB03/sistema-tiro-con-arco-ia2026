import os
import sys
import json
import base64
import tempfile
from io import BytesIO
from PIL import Image
import gradio as gr

try:
    from tiro_arco.agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
    from tiro_arco.agente_2_ocr_extractor import Agente2OCRExtractor
    from tiro_arco.agente_3_validador_conciliador import Agente3ValidadorConciliador
except ImportError:
    try:
        from .agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
        from .agente_2_ocr_extractor import Agente2OCRExtractor
        from .agente_3_validador_conciliador import Agente3ValidadorConciliador
    except ImportError:
        from agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
        from agente_2_ocr_extractor import Agente2OCRExtractor
        from agente_3_validador_conciliador import Agente3ValidadorConciliador


agente1 = AgenteClasificadorSegmentador()
agente2 = Agente2OCRExtractor()
agente3 = Agente3ValidadorConciliador()


def _generar_thumb_html(ruta_img, max_dim=140):
    if not ruta_img or not os.path.exists(ruta_img):
        return "📷"
    try:
        img = Image.open(ruta_img).convert("RGB")
        
        buf_full = BytesIO()
        img.save(buf_full, format="JPEG", quality=85)
        b64_full = base64.b64encode(buf_full.getvalue()).decode("utf-8")

        img_thumb = img.copy()
        img_thumb.thumbnail((max_dim, max_dim))
        buf_thumb = BytesIO()
        img_thumb.save(buf_thumb, format="JPEG", quality=75)
        b64_thumb = base64.b64encode(buf_thumb.getvalue()).decode("utf-8")

        js_open = f"let w=window.open(''); w.document.write('<body style=\'margin:0;background:#111;display:flex;justify-content:center;align-items:center;min-height:100vh;\'><img src=\'data:image/jpeg;base64,{b64_full}\' style=\'max-width:98vw;max-height:98vh;object-fit:contain;\'/></body>');"

        return f'<img src="data:image/jpeg;base64,{b64_thumb}" onclick="{js_open}" width="110" style="border-radius:4px; max-height:85px; object-fit:contain; display:block; margin:auto; cursor:zoom-in; border:1px solid #ccc; transition: transform 0.2s;" onmouseover="this.style.transform=\'scale(1.08)\'" onmouseout="this.style.transform=\'scale(1)\'" title="🔍 Haz clic para abrir el recorte a resolución completa en una nueva pestaña" />'
    except Exception:
        return "📷"


def generar_vistas_paso1(manifiesto_1):
    tareas = manifiesto_1.get("tareas_agente2", [])
    resumen_md = "### ✂️ **Paso 1 Completado:** Clasificación y Segmentación por Cuadrantes\n\n"
    resumen_md += f"- **Archivo Origen:** `{manifiesto_1['archivo_origen']}`\n"
    resumen_md += f"- **Total de Páginas:** `{manifiesto_1['total_paginas']}`\n"
    resumen_md += f"- **Cuadrantes/Recortes Detectados (Agente 1):** `{len(tareas)}`\n\n"
    resumen_md += "👇 **Instrucciones para el Paso 2:**\n"
    resumen_md += "Revisa la galería de recortes a la derecha. Selecciona abajo qué cuadrantes deseas procesar con el **Agente 2 (OCR)** y haz clic en **👁️ Paso 2: Ejecutar OCR en Seleccionados**.\n"

    opciones_checkbox = []
    seleccionados_defecto = []
    galeria = []

    for t in tareas:
        lbl_posicion = t.get("label", f"Pág {t.get('pagina')} - Pos {t.get('target_id')}")
        tipo_juego = t.get("tipo_juego", "clasificacion")
        layout = t.get("layout", "4_arqueros")
        
        lbl_full = f"{lbl_posicion} ({tipo_juego.capitalize()} - {layout})"
        opciones_checkbox.append((lbl_full, lbl_posicion))
        seleccionados_defecto.append(lbl_posicion)

        ruta = t.get("ruta_recorte")
        if ruta and os.path.exists(ruta):
            galeria.append((ruta, f"{lbl_posicion} ({tipo_juego})"))

    json_str = json.dumps({"agente_1_manifiesto": manifiesto_1}, indent=2, ensure_ascii=False)
    return resumen_md, json_str, galeria, opciones_checkbox, seleccionados_defecto


def generar_vistas_paso2(manifiesto_1, manifiesto_2, seleccionados):
    transcripciones = manifiesto_2.get("transcripciones", [])
    
    modelos_usados = set()
    for t in transcripciones:
        m = t.get("transcripcion", {}).get("modelo_usado", "")
        if m:
            modelos_usados.add(m)
    
    modelos_str = ", ".join([f"`{m}`" for m in modelos_usados]) if modelos_usados else "Ninguno (Fallback Tesseract OCR)"

    resumen_md = "### 📊 Diagnóstico Multi-Agente (Paso 2 - OCR completado)\n\n"
    resumen_md += f"- **Archivo Origen:** `{manifiesto_1['archivo_origen']}`\n"
    resumen_md += f"- **Total de Páginas:** `{manifiesto_1['total_paginas']}`\n"
    resumen_md += f"- **Recortes Generados (Agente 1):** `{len(manifiesto_1['tareas_agente2'])}`\n"
    resumen_md += f"- **Cuadrantes Procesados con OCR (Agente 2):** `{len(transcripciones)}` de `{len(seleccionados)}` seleccionados\n"
    resumen_md += f"- **Motor(es) de Inferencia Utilizados:** {modelos_str}\n\n"

    if any("Tesseract" in m for m in modelos_usados) or not modelos_usados:
        resumen_md += "💡 **Diagnóstico de Inferencia:** Se utilizó `Tesseract-OCR` como fallback local. Si deseas usar Qwen2.5-VL / Qwen3-VL en Ollama Docker, descarga el modelo ejecutando en tu terminal: `docker exec -it archery_ollama_ocr ollama pull qwen2-vl` o añade tu `NVIDIA_API_KEY` en el archivo `.env`.\n\n"

    resumen_md += "#### 🎯 Detalle de Transcripciones por Arquero y Recorte Visual:\n\n💡 *Tip de inspección:* **Haz clic sobre la imagen miniatura** en la columna Recorte para abrir el archivo original a resolución completa en una nueva pestaña (sin errores 404), o explora la **Salida en Crudo de Nemotron / VLM** abajo.\n\n"
    
    resumen_md += "| Recorte | Posición | Diana | Arquero | Club | Cat | Estado / Modelo |\n"
    resumen_md += "| :---: | :--- | :---: | :--- | :--- | :---: | :--- |\n"

    opciones_checkbox = []
    seleccionados_defecto = []
    choices_inspector = []

    for t in transcripciones:
        trans = t.get("transcripcion", {})
        modelo = trans.get("modelo_usado", "")
        arquero = trans.get("arquero", "Desconocido")
        target_leido = trans.get("target", "N/A")
        club = trans.get("club", "N/A")
        cat = trans.get("categoria", "N/A")
        
        pag = t.get('pagina')
        pos = t.get('target_id')
        
        lbl_posicion = f"Pág {pag} - Pos {pos}"
        sin_p = trans.get("sin_puntos_registrados", False) or len(trans.get("series", [])) == 0
        lbl_estado = " [Sin Puntos]" if sin_p else ""
        
        lbl_checkbox_full = f"{lbl_posicion} (Diana: {target_leido} | Arquero: {arquero}){lbl_estado}"
        opciones_checkbox.append((lbl_checkbox_full, lbl_posicion))

        lbl_inspector = f"{lbl_posicion} | Diana: {target_leido} | {arquero}"
        choices_inspector.append((lbl_inspector, lbl_inspector))

        if "Fallback" in modelo or "Desconocido" in arquero or not trans.get("valido", True):
            seleccionados_defecto.append(lbl_posicion)

        if sin_p:
            estado_modelo = "⚠️ **Sin Puntos Registrados**"
        elif "Fallback" in modelo:
            estado_modelo = f"⚠️ `{modelo}`"
        else:
            estado_modelo = f"✅ `{modelo}`"

        p_img = t.get("ruta_recorte_procesada") or t.get("ruta_recorte_original")
        thumb_cell = _generar_thumb_html(p_img)

        resumen_md += f"| {thumb_cell} | **{lbl_posicion}** | `{target_leido}` | **{arquero}** | {club} | `{cat}` | {estado_modelo} |\n"

    resumen_md += "\n\n### 📜 Salida en Crudo de Inferencia (Nemotron / VLM por Recorte)\n\n"
    for t in transcripciones:
        trans = t.get("transcripcion", {})
        pag = t.get('pagina')
        pos = t.get('target_id')
        arquero = trans.get("arquero", "Desconocido")
        raw_text = trans.get("texto_raw_ocr", "(Sin texto en crudo registrado)")
        resumen_md += f"<details><summary><b>Pág {pag} - Pos {pos} ({arquero}) - Texto Crudo Nemotron/OCR</b></summary>\n\n```markdown\n{raw_text}\n```\n\n</details>\n\n"

    manifiesto_combinado = {
        "agente_1_manifiesto": manifiesto_1,
        "agente_2_manifiesto": manifiesto_2
    }
    json_str = json.dumps(manifiesto_combinado, indent=2, ensure_ascii=False)

    galeria = []
    for t in transcripciones:
        p = t.get("ruta_recorte_procesada") or t.get("ruta_recorte_original")
        if p and os.path.exists(p):
            target_leido = t.get("transcripcion", {}).get("target", t.get("target_id"))
            arquero_leido = t.get("transcripcion", {}).get("arquero", "Desconocido")
            sin_p = t.get("transcripcion", {}).get("sin_puntos_registrados", False) or len(t.get("transcripcion", {}).get("series", [])) == 0
            tag_puntos = " [Sin Puntos]" if sin_p else ""
            galeria.append((p, f"Pág {t.get('pagina')} - Pos {t.get('target_id')} (Diana: {target_leido}) | Arquero: {arquero_leido}{tag_puntos}"))

    return resumen_md, json_str, galeria, opciones_checkbox, seleccionados_defecto, choices_inspector


def generar_vistas_paso3(manifiesto_1, manifiesto_2, manifiesto_3):
    auditorias = manifiesto_3.get("resultados_auditados", [])
    resumen_aud = manifiesto_3.get("resumen_auditoria", {})

    resumen_md = "### ⚖️ **Paso 3 Completado:** Auditoría Lógica, Reconciliación y Control de Certeza (Agente 3)\n\n"
    resumen_md += f"- **Cuadrantes Auditados:** `{resumen_aud.get('total_cuadrantes_procesados', 0)}`\n"
    resumen_md += f"- **Aprobados Automáticos (100% Certeza):** `{resumen_aud.get('aprobados_automaticos', 0)}` ✅\n"
    resumen_md += f"- **Requiere Revisión / Discrepancias:** `{resumen_aud.get('requiere_revision_humana', 0)}` ⚠️\n"
    resumen_md += f"- **Sin Puntos Confirmados:** `{resumen_aud.get('sin_puntos_confirmados', 0)}` ℹ️\n\n"

    resumen_md += "#### 🎯 Tabla de Reconciliación Lógica y Auditoría por Diana:\n\n"
    resumen_md += "| Recorte | Posición | Diana | Arquero | Score Certeza | Estado Auditoría | Total Papel vs Calc | Diagnóstico / Alertas |\n"
    resumen_md += "| :---: | :--- | :---: | :--- | :---: | :---: | :---: | :--- |\n"

    choices_inspector = []

    for item in auditorias:
        pag = item.get("pagina", 1)
        pos = item.get("target_id", "A")
        target_leido = item.get("target", pos)
        arquero = item.get("arquero", "Desconocido")
        score = item.get("score_certeza", 0.0)
        estado = item.get("estado_auditoria", "REVISION")
        
        tot_ofic = item.get("totales_oficiales_planilla", {}).get("total_puntos", 0)
        tot_calc = item.get("totales_calculados_series", {}).get("total_puntos", 0)

        lbl_posicion = f"Pág {pag} - Pos {pos}"
        lbl_inspector = f"{lbl_posicion} | Diana: {target_leido} | {arquero} (Certeza: {score}%)"
        choices_inspector.append((lbl_inspector, lbl_inspector))

        p_img = item.get("ruta_recorte", "")
        thumb_cell = _generar_thumb_html(p_img)

        if estado == "APROBADO_AUTOMATICO":
            tag_estado = f"🟢 **Aprobado** (`{score}%`)"
        elif estado == "SIN_PUNTOS_CONFIRMADO":
            tag_estado = f"⚪ **Sin Puntos** (`{score}%`)"
        else:
            tag_estado = f"🔴 **Revisión** (`{score}%`)"

        tot_cell = f"Papel: `{tot_ofic}` | Calc: `{tot_calc}`"
        if tot_ofic > 0 and tot_ofic != tot_calc:
            tot_cell = f"⚠️ Papel: `{tot_ofic}` != Calc: `{tot_calc}`"

        advs = item.get("advertencias", []) + item.get("errores", [])
        diag_str = "<br>".join([f"• {a}" for a in advs]) if advs else "✅ Sin discrepancias detectadas"

        resumen_md += f"| {thumb_cell} | **{lbl_posicion}** | `{target_leido}` | **{arquero}** | `{score}%` | {tag_estado} | {tot_cell} | {diag_str} |\n"

    manifiesto_combinado = {
        "agente_1_manifiesto": manifiesto_1,
        "agente_2_manifiesto": manifiesto_2,
        "agente_3_manifiesto": manifiesto_3
    }
    json_str = json.dumps(manifiesto_combinado, indent=2, ensure_ascii=False)

    return resumen_md, json_str, choices_inspector


def inspeccionar_recorte(opcion_seleccionada, manifiesto_1, manifiesto_2):
    if not manifiesto_2 or not opcion_seleccionada:
        return "⚠️ Selecciona un arquero para ver su salida en crudo.", "{}", None

    transcripciones = manifiesto_2.get("transcripciones", [])
    for t in transcripciones:
        pag = str(t.get('pagina'))
        pos = str(t.get('target_id'))
        trans = t.get("transcripcion", {})
        
        target_label = f"Pág {pag} - Pos {pos}"
        if target_label in opcion_seleccionada or pos in opcion_seleccionada:
            raw_text = trans.get("texto_raw_ocr", "(Sin texto en crudo)")
            p_img = t.get("ruta_recorte_procesada") or t.get("ruta_recorte_original")
            json_parsed = json.dumps(trans, indent=2, ensure_ascii=False)
            return raw_text, json_parsed, p_img

    return "⚠️ Recorte no encontrado.", "{}", None


def inspeccionar_auditoria(opcion_seleccionada, manifiesto_3):
    if not manifiesto_3 or not opcion_seleccionada:
        return json.dumps({"info": "⚠️ Selecciona un arquero para ver el detalle de auditoría."}, indent=2, ensure_ascii=False)

    auditados = manifiesto_3.get("resultados_auditados", [])
    for item in auditados:
        pag = str(item.get('pagina'))
        pos = str(item.get('target_id'))
        arquero = item.get("arquero", "")
        
        target_label = f"Pág {pag} - Pos {pos}"
        if target_label in opcion_seleccionada or pos in opcion_seleccionada or arquero in opcion_seleccionada:
            return json.dumps(item, indent=2, ensure_ascii=False)

    return json.dumps({"info": "⚠️ Detalle de auditoría no encontrado."}, indent=2, ensure_ascii=False)


def ejecutar_paso1(archivo_input, tipo_manual, page_overrides=None):
    if archivo_input is None:
        empty_audit_json = json.dumps({"info": "Esperando ejecución del Paso 3..."}, indent=2, ensure_ascii=False)
        return "⚠️ Por favor sube un archivo válido.", "{}", [], gr.CheckboxGroup(choices=[]), None, None, None, "(Esperando ejecucion)", "{}", None, gr.Dropdown(choices=[]), gr.Dropdown(choices=[]), empty_audit_json

    ruta = archivo_input.name
    manifiesto_1 = agente1.procesar_documento(ruta, tipo_juego_manual=tipo_manual, page_overrides=page_overrides)
    resumen_md, json_str, galeria, opciones, seleccionados = generar_vistas_paso1(manifiesto_1)

    empty_audit_json = json.dumps({"info": "Esperando ejecución del Paso 3 (Auditoría Lógica)..."}, indent=2, ensure_ascii=False)

    return (
        resumen_md,
        json_str,
        galeria,
        gr.CheckboxGroup(choices=opciones, value=seleccionados, label="Seleccionar Cuadrantes para OCR (Paso 2)"),
        manifiesto_1,
        None,
        None,
        "Esperando ejecución del Paso 2 (OCR)...",
        "{}",
        None,
        gr.Dropdown(choices=[], value=None),
        gr.Dropdown(choices=[], value=None),
        empty_audit_json
    )


def ejecutar_paso2(seleccionados, manifiesto_1, manifiesto_2_previo):
    empty_audit_json = json.dumps({"info": "Haz clic en Paso 3 abajo para auditar los resultados."}, indent=2, ensure_ascii=False)

    if not manifiesto_1:
        return "⚠️ Primero debes ejecutar el Paso 1 (Segmentación).", "{}", [], gr.CheckboxGroup(choices=[]), manifiesto_1, None, None, "", "{}", None, gr.Dropdown(choices=[]), gr.Dropdown(choices=[]), empty_audit_json

    if not seleccionados:
        return "⚠️ Por favor selecciona al menos un cuadrante para realizar el OCR.", "{}", [], gr.CheckboxGroup(choices=[]), manifiesto_1, manifiesto_2_previo, None, "", "{}", None, gr.Dropdown(choices=[]), gr.Dropdown(choices=[]), empty_audit_json

    print(f"[UI] 👁️ Ejecutando Paso 2 (OCR) para {len(seleccionados)} cuadrante(s): {seleccionados}")

    if manifiesto_2_previo is None:
        manifiesto_2 = agente2.reintentar_tareas_especificas(manifiesto_1, {"transcripciones": []}, seleccionados)
    else:
        manifiesto_2 = agente2.reintentar_tareas_especificas(manifiesto_1, manifiesto_2_previo, seleccionados)

    resumen_md, json_str, galeria, opciones, selec_def, choices_insp = generar_vistas_paso2(manifiesto_1, manifiesto_2, seleccionados)

    primer_insp_key = choices_insp[0][1] if choices_insp else None
    raw_ocr_init, json_init, img_init = inspeccionar_recorte(primer_insp_key, manifiesto_1, manifiesto_2)

    return (
        resumen_md,
        json_str,
        galeria,
        gr.CheckboxGroup(choices=opciones, value=selec_def, label="Cuadrantes Procesados (Reintentar si alguno falló)"),
        manifiesto_1,
        manifiesto_2,
        None,
        raw_ocr_init,
        json_init,
        img_init,
        gr.Dropdown(choices=choices_insp, value=primer_insp_key, label="🔍 Seleccionar Arquero/Cuadrante para Inspeccionar Salida en Crudo"),
        gr.Dropdown(choices=[], value=None),
        empty_audit_json
    )


def ejecutar_paso3(manifiesto_1, manifiesto_2):
    if not manifiesto_2:
        empty_audit_json = json.dumps({"info": "Primero debes ejecutar el Paso 2 (OCR)."}, indent=2, ensure_ascii=False)
        return "⚠️ Primero debes ejecutar el Paso 2 (OCR).", "{}", gr.Dropdown(choices=[]), empty_audit_json, None

    print(f"[UI] ⚖️ Ejecutando Paso 3 (Agente 3 - Auditoría Lógica y Reconciliación)...")
    manifiesto_3 = agente3.auditar_manifiesto_completo(manifiesto_2)

    resumen_md, json_str, choices_insp = generar_vistas_paso3(manifiesto_1, manifiesto_2, manifiesto_3)
    primer_key = choices_insp[0][1] if choices_insp else None
    audit_init = inspeccionar_auditoria(primer_key, manifiesto_3)

    return (
        resumen_md,
        json_str,
        gr.Dropdown(choices=choices_insp, value=primer_key, label="⚖️ Seleccionar Arquero/Cuadrante para Inspeccionar Auditoría Agente 3"),
        audit_init,
        manifiesto_3
    )


def build_ui():
    with gr.Blocks(title="🎯 Sistema Multi-Agente - Tiro con Arco (v47)") as demo:
        gr.Markdown("# 🎯 Sistema Multi-Agente - Tiro con Arco (v47 - Control de Certeza y Agente 3)")
        gr.Markdown("Flujo Rígido y Controlado: **Paso 1** (Segmentación) ➡️ **Paso 2** (OCR) ➡️ **Paso 3** (Auditoría Lógica, Reconciliación Matemática y Certeza).")

        state_manifiesto_1 = gr.State(None)
        state_manifiesto_2 = gr.State(None)
        state_manifiesto_3 = gr.State(None)

        with gr.Row():
            with gr.Column(scale=1):
                file_input = gr.File(label="Subir Planilla (Imagen PNG/JPG o PDF)", file_types=[".png", ".jpg", ".jpeg", ".pdf"])
                tipo_manual = gr.Dropdown(
                    label="Modo de Juego Manual (Opcional)",
                    choices=["Auto", "info", "eliminatoria_2", "clasificacion_1", "clasificacion_2", "clasificacion_4"],
                    value="Auto"
                )
                btn_paso1 = gr.Button("✂️ Paso 1: Clasificar y Segmentar Cuadrantes", variant="primary")
                
                gr.Markdown("---")
                gr.Markdown("### 👁️ Paso 2: Selección y OCR")
                checkbox_cuadrantes = gr.CheckboxGroup(choices=[], label="Seleccionar Cuadrantes para OCR (Paso 2)")
                btn_paso2 = gr.Button("👁️ Paso 2: Ejecutar OCR en Seleccionados", variant="secondary")

                gr.Markdown("---")
                gr.Markdown("### ⚖️ Paso 3: Auditoría y Reconciliación")
                btn_paso3 = gr.Button("⚖️ Paso 3: Ejecutar Validación y Reconciliación Lógica (Agente 3)", variant="primary")

            with gr.Column(scale=2):
                diagnostico_out = gr.Markdown("Esperando ejecución del Paso 1...")
                galeria_out = gr.Gallery(label="Recortes / Cuadrantes Detectados", columns=2)
                json_out = gr.Code(label="Manifiesto JSON Completo (Agente 1 + Agente 2 + Agente 3)", language="json")

        gr.Markdown("---")
        gr.Markdown("## ⚖️ Resultado de Auditoría Lógica y Control de Certeza (Paso 3)")
        
        with gr.Row():
            with gr.Column(scale=1):
                dropdown_audit = gr.Dropdown(choices=[], label="⚖️ Seleccionar Arquero/Cuadrante para Inspeccionar Auditoría Agente 3")
            with gr.Column(scale=2):
                json_audit_inspector = gr.Code(label="📋 Detalle de Reconciliación y Auditoría (Agente 3)", language="json")

        gr.Markdown("---")
        gr.Markdown("## 🔬 Inspección Detallada de Salida en Crudo de Nemotron / VLM (Paso 2)")

        with gr.Row():
            with gr.Column(scale=1):
                dropdown_inspector = gr.Dropdown(choices=[], label="🔍 Seleccionar Arquero/Cuadrante para Inspeccionar Salida en Crudo")
                image_inspector = gr.Image(label="🖼️ Recorte Visual del Arquero", interactive=False)
            with gr.Column(scale=2):
                raw_ocr_out = gr.Code(label="📜 Salida en Crudo Retornada por Nemotron / VLM (Texto Bruto)", language="markdown")
                json_inspector = gr.Code(label="🎯 Campos JSON Procesados y Cotejados", language="json")

        dropdown_inspector.change(
            fn=inspeccionar_recorte,
            inputs=[dropdown_inspector, state_manifiesto_1, state_manifiesto_2],
            outputs=[raw_ocr_out, json_inspector, image_inspector]
        )

        dropdown_audit.change(
            fn=inspeccionar_auditoria,
            inputs=[dropdown_audit, state_manifiesto_3],
            outputs=[json_audit_inspector]
        )

        # 13 Outputs para Paso 1 y Paso 2
        ui_outputs_p1_p2 = [
            diagnostico_out,
            json_out,
            galeria_out,
            checkbox_cuadrantes,
            state_manifiesto_1,
            state_manifiesto_2,
            state_manifiesto_3,
            raw_ocr_out,
            json_inspector,
            image_inspector,
            dropdown_inspector,
            dropdown_audit,
            json_audit_inspector
        ]

        btn_paso1.click(
            fn=ejecutar_paso1,
            inputs=[file_input, tipo_manual],
            outputs=ui_outputs_p1_p2
        )

        btn_paso2.click(
            fn=ejecutar_paso2,
            inputs=[checkbox_cuadrantes, state_manifiesto_1, state_manifiesto_2],
            outputs=ui_outputs_p1_p2
        )

        btn_paso3.click(
            fn=ejecutar_paso3,
            inputs=[state_manifiesto_1, state_manifiesto_2],
            outputs=[diagnostico_out, json_out, dropdown_audit, json_audit_inspector, state_manifiesto_3]
        )

    return demo


def main():
    print("=" * 60)
    print("🚀 Servidor Principal Multi-Agente (v47) - Tiro con Arco")
    print("🌍 Abre tu navegador en: http://localhost:7860")
    print("=" * 60)
    demo = build_ui()
    allowed_directories = ["/tmp", tempfile.gettempdir(), os.getcwd(), "/app"]
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, allowed_paths=allowed_directories)


if __name__ == "__main__":
    main()
