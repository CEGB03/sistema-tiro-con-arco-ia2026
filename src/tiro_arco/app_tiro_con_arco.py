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
except ImportError:
    try:
        from .agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
        from .agente_2_ocr_extractor import Agente2OCRExtractor
    except ImportError:
        from agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
        from agente_2_ocr_extractor import Agente2OCRExtractor


agente1 = AgenteClasificadorSegmentador()
agente2 = Agente2OCRExtractor()


def _generar_thumb_html(ruta_img, max_dim=140):
    if not ruta_img or not os.path.exists(ruta_img):
        return "📷"
    try:
        img = Image.open(ruta_img).convert("RGB")
        
        # Imagen a resolución completa
        buf_full = BytesIO()
        img.save(buf_full, format="JPEG", quality=85)
        b64_full = base64.b64encode(buf_full.getvalue()).decode("utf-8")

        # Miniatura optimizada
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


def inspeccionar_recorte(opcion_seleccionada, manifiesto_1, manifiesto_2):
    if not manifiesto_2 or not opcion_seleccionada:
        return "⚠️ Selecciona un arquero para ver su salida en crudo.", "{}", None

    transcripciones = manifiesto_2.get("transcripciones", [])
    for t in transcripciones:
        pag = str(t.get('pagina'))
        pos = str(t.get('target_id'))
        trans = t.get("transcripcion", {})
        arquero = trans.get("arquero", "Desconocido")
        target_leido = trans.get("target", "N/A")
        
        target_label = f"Pág {pag} - Pos {pos}"
        if target_label in opcion_seleccionada or pos in opcion_seleccionada:
            raw_text = trans.get("texto_raw_ocr", "(Sin texto en crudo)")
            p_img = t.get("ruta_recorte_procesada") or t.get("ruta_recorte_original")
            json_parsed = json.dumps(trans, indent=2, ensure_ascii=False)
            return raw_text, json_parsed, p_img

    return "⚠️ Recorte no encontrado.", "{}", None


def ejecutar_paso1(archivo_input, tipo_manual, page_overrides=None):
    if archivo_input is None:
        return "⚠️ Por favor sube un archivo válido.", "{}", [], gr.CheckboxGroup(choices=[]), [], None, None, "(Esperando ejecucion)", "{}", None, gr.Dropdown(choices=[])

    ruta = archivo_input.name
    manifiesto_1 = agente1.procesar_documento(ruta, tipo_juego_manual=tipo_manual, page_overrides=page_overrides)
    resumen_md, json_str, galeria, opciones, seleccionados = generar_vistas_paso1(manifiesto_1)

    return (
        resumen_md,
        json_str,
        galeria,
        gr.CheckboxGroup(choices=opciones, value=seleccionados, label="Seleccionar Cuadrantes para OCR (Paso 2)"),
        manifiesto_1,
        None,
        "Esperando ejecución del Paso 2 (OCR)...",
        "{}",
        None,
        gr.Dropdown(choices=[], value=None)
    )


def ejecutar_paso2(seleccionados, manifiesto_1, manifiesto_2_previo):
    if not manifiesto_1:
        return "⚠️ Primero debes ejecutar el Paso 1 (Segmentación).", "{}", [], gr.CheckboxGroup(choices=[]), manifiesto_1, None, "", "{}", None, gr.Dropdown(choices=[])

    if not seleccionados:
        return "⚠️ Por favor selecciona al menos un cuadrante para realizar el OCR.", "{}", [], gr.CheckboxGroup(choices=[]), manifiesto_1, manifiesto_2_previo, "", "{}", None, gr.Dropdown(choices=[])

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
        raw_ocr_init,
        json_init,
        img_init,
        gr.Dropdown(choices=choices_insp, value=primer_insp_key, label="🔍 Seleccionar Arquero/Cuadrante para Inspeccionar Salida en Crudo")
    )


def build_ui():
    with gr.Blocks(title="🎯 Sistema Multi-Agente - Tiro con Arco (v45)") as demo:
        gr.Markdown("# 🎯 Sistema Multi-Agente - Tiro con Arco (v45 - Inspección en Crudo Nemotron/VLM)")
        gr.Markdown("Flujo Rígido y Controlado: **Paso 1** (Segmentación Total) ➡️ **Paso 2** (OCR Selectivo, Salida en Crudo Nemotron y Recortes con Zoom).")

        state_manifiesto_1 = gr.State(None)
        state_manifiesto_2 = gr.State(None)

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

            with gr.Column(scale=2):
                diagnostico_out = gr.Markdown("Esperando ejecución del Paso 1...")
                galeria_out = gr.Gallery(label="Recortes / Cuadrantes Detectados", columns=2)
                json_out = gr.Code(label="Manifiesto JSON Completo (Agente 1 + Agente 2)", language="json")

        gr.Markdown("---")
        gr.Markdown("## 🔬 Inspección Detallada de Salida en Crudo de Nemotron / VLM")
        gr.Markdown("Selecciona un arquero de la lista para analizar el texto sin procesar devuelto por Nemotron antes de cualquier parseo o cotejo:")

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

        btn_paso1.click(
            fn=ejecutar_paso1,
            inputs=[file_input, tipo_manual],
            outputs=[diagnostico_out, json_out, galeria_out, checkbox_cuadrantes, state_manifiesto_1, state_manifiesto_2, raw_ocr_out, json_inspector, image_inspector, dropdown_inspector]
        )

        btn_paso2.click(
            fn=ejecutar_paso2,
            inputs=[checkbox_cuadrantes, state_manifiesto_1, state_manifiesto_2],
            outputs=[diagnostico_out, json_out, galeria_out, checkbox_cuadrantes, state_manifiesto_1, state_manifiesto_2, raw_ocr_out, json_inspector, image_inspector, dropdown_inspector]
        )

    return demo


def main():
    print("=" * 60)
    print("🚀 Servidor Principal Multi-Agente (v45) - Tiro con Arco")
    print("🌍 Abre tu navegador en: http://localhost:7860")
    print("=" * 60)
    demo = build_ui()
    allowed_directories = ["/tmp", tempfile.gettempdir(), os.getcwd(), "/app"]
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, allowed_paths=allowed_directories)


if __name__ == "__main__":
    main()
