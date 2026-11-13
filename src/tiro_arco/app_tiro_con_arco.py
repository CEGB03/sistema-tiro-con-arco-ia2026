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
        img_thumb = img.copy()
        img_thumb.thumbnail((max_dim, max_dim))
        buf_thumb = BytesIO()
        img_thumb.save(buf_thumb, format="JPEG", quality=75)
        b64_thumb = base64.b64encode(buf_thumb.getvalue()).decode("utf-8")

        file_url = f"/gradio_api/file={ruta_img}"
        return f'<a href="{file_url}" target="_blank" title="🔍 Haz clic para abrir el recorte en una pestaña nueva en Alta Resolución"><img src="data:image/jpeg;base64,{b64_thumb}" width="110" style="border-radius:4px; max-height:85px; object-fit:contain; display:block; margin:auto; border:2px solid #3b82f6; transition: transform 0.2s;" /><small style="color:#2563eb; font-weight:bold; font-size:11px; display:block; margin-top:3px; text-align:center;">🔍 Abrir imagen ↗</small></a>'
    except Exception:
        return "📷"


# --- PASO 0: CARGA Y RENDERING DE PÁGINAS ---
def cargar_documento_paso0(archivo_input):
    if archivo_input is None:
        return (
            "⚠️ Por favor sube un archivo PDF o imagen válido.",
            [],
            gr.Dropdown(choices=[], value=None),
            None,
            "Esperando archivo...",
            [],
            gr.Dropdown(choices=[], value=None),
            None,
            gr.CheckboxGroup(choices=[]),
            "{}"
        )

    ruta = archivo_input.name
    paginas = agente1.extraer_paginas_pdf_o_imagen(ruta)

    galeria_paginas = []
    choices_paginas = []
    for p in paginas:
        num = p["numero_pagina"]
        ruta_p = p["ruta_actual"]
        lbl = f"Página {num}" + (" (✨ Mejorada)" if p["es_mejorada"] else "")
        choices_paginas.append((lbl, num))
        galeria_paginas.append((ruta_p, lbl))

    primer_num = choices_paginas[0][1] if choices_paginas else None
    img_init = paginas[0]["ruta_actual"] if paginas else None
    msg_status = f"✅ Documento cargado en alta definición: `{os.path.basename(ruta)}`. Se extrajeron `{len(paginas)}` página(s) con Pre-OCR a nivel de hoja. Puedes revisar y mejorar la calidad antes de segmentar cuadrantes."

    return (
        msg_status,
        galeria_paginas,
        gr.Dropdown(choices=choices_paginas, value=primer_num, label="🔍 Seleccionar Página a Inspeccionar/Mejorar"),
        img_init,
        "Páginas listas. Si estás satisfecho con la calidad, haz clic en **✂️ Paso 1: Dividir Cuadrantes**.",
        [],
        gr.Dropdown(choices=[], value=None),
        None,
        gr.CheckboxGroup(choices=[]),
        "{}"
    )


def mejorar_pagina_seleccionada(num_pagina):
    if not num_pagina:
        return "⚠️ Selecciona una página válida.", [], gr.Dropdown(choices=[]), None

    num_pagina = int(num_pagina)
    exito, msg = agente1.mejorar_calidad_pagina(num_pagina)

    paginas = list(agente1.paginas_cache.values())
    galeria_paginas = []
    choices_paginas = []
    for p in paginas:
        lbl = f"Página {p['numero_pagina']}" + (" (✨ Mejorada)" if p["es_mejorada"] else "")
        choices_paginas.append((lbl, p["numero_pagina"]))
        galeria_paginas.append((p["ruta_actual"], lbl))

    img_actual = agente1.paginas_cache[num_pagina]["ruta_actual"] if num_pagina in agente1.paginas_cache else None
    return msg, galeria_paginas, gr.Dropdown(choices=choices_paginas, value=num_pagina), img_actual


def deshacer_pagina_seleccionada(num_pagina):
    if not num_pagina:
        return "⚠️ Selecciona una página válida.", [], gr.Dropdown(choices=[]), None

    num_pagina = int(num_pagina)
    exito, msg = agente1.deshacer_mejora_pagina(num_pagina)

    paginas = list(agente1.paginas_cache.values())
    galeria_paginas = []
    choices_paginas = []
    for p in paginas:
        lbl = f"Página {p['numero_pagina']}" + (" (✨ Mejorada)" if p["es_mejorada"] else "")
        choices_paginas.append((lbl, p["numero_pagina"]))
        galeria_paginas.append((p["ruta_actual"], lbl))

    img_actual = agente1.paginas_cache[num_pagina]["ruta_actual"] if num_pagina in agente1.paginas_cache else None
    return msg, galeria_paginas, gr.Dropdown(choices=choices_paginas, value=num_pagina), img_actual


# --- PASO 1: SEGMENTACIÓN DE CUADRANTES ---


def mejorar_todas_las_paginas_ui():
    exito, msg = agente1.mejorar_todas_las_paginas()
    paginas = list(agente1.paginas_cache.values())
    galeria_paginas = []
    choices_paginas = []
    for p in paginas:
        lbl = f"Página {p['numero_pagina']}" + (" (✨ Mejorada)" if p["es_mejorada"] else "")
        choices_paginas.append((lbl, p["numero_pagina"]))
        galeria_paginas.append((p["ruta_actual"], lbl))

    primer_num = choices_paginas[0][1] if choices_paginas else None
    img_actual = agente1.paginas_cache[primer_num]["ruta_actual"] if primer_num and primer_num in agente1.paginas_cache else None
    return msg, galeria_paginas, gr.Dropdown(choices=choices_paginas, value=primer_num), img_actual


def deshacer_todas_las_paginas_ui():
    exito, msg = agente1.deshacer_todas_las_paginas()
    paginas = list(agente1.paginas_cache.values())
    galeria_paginas = []
    choices_paginas = []
    for p in paginas:
        lbl = f"Página {p['numero_pagina']}" + (" (✨ Mejorada)" if p["es_mejorada"] else "")
        choices_paginas.append((lbl, p["numero_pagina"]))
        galeria_paginas.append((p["ruta_actual"], lbl))

    primer_num = choices_paginas[0][1] if choices_paginas else None
    img_actual = agente1.paginas_cache[primer_num]["ruta_actual"] if primer_num and primer_num in agente1.paginas_cache else None
    return msg, galeria_paginas, gr.Dropdown(choices=choices_paginas, value=primer_num), img_actual


def ejecutar_paso1_segmentacion(archivo_input, tipo_manual):
    if not agente1.paginas_cache and archivo_input:
        agente1.extraer_paginas_pdf_o_imagen(archivo_input.name)

    if not agente1.paginas_cache:
        return (
            "⚠️ Primero debes cargar un archivo.",
            [],
            gr.Dropdown(choices=[], value=None),
            None,
            gr.CheckboxGroup(choices=[]),
            "{}",
            None
        )

    ruta = archivo_input.name if archivo_input else "documento.pdf"
    manifiesto_1 = agente1.procesar_documento(ruta, tipo_juego_manual=tipo_manual)

    tareas = manifiesto_1.get("tareas_agente2", [])
    galeria_cuadrantes = []
    choices_cuadrantes = []
    opciones_checkbox = []
    seleccionados_defecto = []

    for t in tareas:
        lbl = t.get("label", f"Pág {t.get('pagina')} - Pos {t.get('target_id')}")
        tipo_juego = t.get("tipo_juego", "clasificacion")
        es_elim = (tipo_juego == "eliminatoria")
        es_info = t.get("es_pagina_informacion", False) or tipo_juego in ["info", "informacion", "portada"] or es_elim
        es_vacio = t.get("es_cuadrante_vacio", False)

        lbl_mejora = lbl + (" (✨ Mejorado)" if t.get("es_mejorado") else "")
        choices_cuadrantes.append((lbl_mejora, lbl))

        if es_elim:
            lbl_check = f"{lbl} ⚔️ [Eliminatoria - EXCLUIDA]"
            opciones_checkbox.append((lbl_check, lbl))
            tag_gal = " [Eliminatoria Excluida]"
        elif es_info:
            lbl_check = f"{lbl} ℹ️ [Hoja de Información / Portada - EXCLUIDA]"
            opciones_checkbox.append((lbl_check, lbl))
            tag_gal = " [Información Excluida]"
        elif es_vacio:
            lbl_check = f"{lbl} 🎯 ({tipo_juego.capitalize()}) [Sin Puntos / Vacío]"
            opciones_checkbox.append((lbl_check, lbl))
            tag_gal = f" ({tipo_juego.capitalize()}) [Vacío]"
        else:
            lbl_check = f"{lbl} 🎯 ({tipo_juego.capitalize()})"
            opciones_checkbox.append((lbl_check, lbl))
            seleccionados_defecto.append(lbl)
            tag_gal = f" ({tipo_juego.capitalize()})"

        ruta_crop = t.get("ruta_recorte")
        if ruta_crop and os.path.exists(ruta_crop):
            galeria_cuadrantes.append((ruta_crop, f"{lbl}{tag_gal}"))

    primer_key = choices_cuadrantes[0][1] if choices_cuadrantes else None
    img_init = agente1.recortes_cache[primer_key]["ruta_recorte"] if primer_key and primer_key in agente1.recortes_cache else None

    json_str = json.dumps({"agente_1_manifiesto": manifiesto_1}, indent=2, ensure_ascii=False)
    resumen_md = f"### ✂️ **Paso 1 Completado:** División de Cuadrantes por Página con Pre-OCR\\n\\n"
    resumen_md += f"- **Cuadrantes Detectados:** `{len(tareas)}` en `{len(agente1.paginas_cache)}` página(s).\\n\\n"
    resumen_md += "Puedes revisar y aplicar mejoramiento de calidad individual a cada recorte de cuadrante abajo. Haz clic en la miniatura de cualquier tabla para **abrir el recorte en alta resolución en una pestaña nueva**."

    return (
        resumen_md,
        galeria_cuadrantes,
        gr.Dropdown(choices=choices_cuadrantes, value=primer_key, label="🔍 Seleccionar Recorte de Cuadrante a Inspeccionar/Mejorar"),
        img_init,
        gr.CheckboxGroup(choices=opciones_checkbox, value=seleccionados_defecto, label="Seleccionar Cuadrantes Organizados por Página (Paso 2)"),
        json_str,
        manifiesto_1
    )


def mejorar_recorte_seleccionado(label_recorte):
    if not label_recorte:
        return "⚠️ Selecciona un recorte válido.", [], gr.Dropdown(choices=[]), None

    exito, msg = agente1.mejorar_calidad_recorte(label_recorte)

    galeria_cuadrantes = []
    choices_cuadrantes = []
    for k, rec in agente1.recortes_cache.items():
        lbl_mejora = k + (" (✨ Mejorado)" if rec["es_mejorado"] else "")
        choices_cuadrantes.append((lbl_mejora, k))
        galeria_cuadrantes.append((rec["ruta_recorte"], lbl_mejora))

    img_actual = agente1.recortes_cache[label_recorte]["ruta_recorte"] if label_recorte in agente1.recortes_cache else None
    return msg, galeria_cuadrantes, gr.Dropdown(choices=choices_cuadrantes, value=label_recorte), img_actual


def deshacer_recorte_seleccionado(label_recorte):
    if not label_recorte:
        return "⚠️ Selecciona un recorte válido.", [], gr.Dropdown(choices=[]), None

    exito, msg = agente1.deshacer_mejora_recorte(label_recorte)

    galeria_cuadrantes = []
    choices_cuadrantes = []
    for k, rec in agente1.recortes_cache.items():
        lbl_mejora = k + (" (✨ Mejorado)" if rec["es_mejorado"] else "")
        choices_cuadrantes.append((lbl_mejora, k))
        galeria_cuadrantes.append((rec["ruta_recorte"], lbl_mejora))

    img_actual = agente1.recortes_cache[label_recorte]["ruta_recorte"] if label_recorte in agente1.recortes_cache else None
    return msg, galeria_cuadrantes, gr.Dropdown(choices=choices_cuadrantes, value=label_recorte), img_actual


# --- PASO 2: OCR ---


def mejorar_todos_los_recortes_ui():
    exito, msg = agente1.mejorar_todos_los_recortes()
    galeria_cuadrantes = []
    choices_cuadrantes = []
    for k, rec in agente1.recortes_cache.items():
        lbl_mejora = k + (" (✨ Mejorado)" if rec["es_mejorado"] else "")
        choices_cuadrantes.append((lbl_mejora, k))
        galeria_cuadrantes.append((rec["ruta_recorte"], lbl_mejora))

    primer_key = choices_cuadrantes[0][1] if choices_cuadrantes else None
    img_actual = agente1.recortes_cache[primer_key]["ruta_recorte"] if primer_key and primer_key in agente1.recortes_cache else None
    return msg, galeria_cuadrantes, gr.Dropdown(choices=choices_cuadrantes, value=primer_key), img_actual


def deshacer_todos_los_recortes_ui():
    exito, msg = agente1.deshacer_todos_los_recortes()
    galeria_cuadrantes = []
    choices_cuadrantes = []
    for k, rec in agente1.recortes_cache.items():
        lbl_mejora = k + (" (✨ Mejorado)" if rec["es_mejorado"] else "")
        choices_cuadrantes.append((lbl_mejora, k))
        galeria_cuadrantes.append((rec["ruta_recorte"], lbl_mejora))

    primer_key = choices_cuadrantes[0][1] if choices_cuadrantes else None
    img_actual = agente1.recortes_cache[primer_key]["ruta_recorte"] if primer_key and primer_key in agente1.recortes_cache else None
    return msg, galeria_cuadrantes, gr.Dropdown(choices=choices_cuadrantes, value=primer_key), img_actual


def seleccionar_cuadrantes_validos_ui(manifiesto_1):
    if not manifiesto_1:
        return gr.CheckboxGroup(value=[])
    tareas = manifiesto_1.get("tareas_agente2", [])
    validos = []
    for t in tareas:
        lbl = t.get("label", f"Pág {t.get('pagina')} - Pos {t.get('target_id')}")
        tipo_juego = t.get("tipo_juego", "clasificacion")
        es_elim = (tipo_juego == "eliminatoria")
        es_info = t.get("es_pagina_informacion", False) or tipo_juego in ["info", "informacion", "portada"] or es_elim
        es_vacio = t.get("es_cuadrante_vacio", False)
        if not es_info and not es_vacio:
            validos.append(lbl)
    return gr.CheckboxGroup(value=validos)


def seleccionar_todos_cuadrantes_ui(manifiesto_1):
    if not manifiesto_1:
        return gr.CheckboxGroup(value=[])
    tareas = manifiesto_1.get("tareas_agente2", [])
    todos = [t.get("label", f"Pág {t.get('pagina')} - Pos {t.get('target_id')}") for t in tareas]
    return gr.CheckboxGroup(value=todos)


def desmarcar_todos_cuadrantes_ui():
    return gr.CheckboxGroup(value=[])


def ejecutar_paso2_ocr(seleccionados, manifiesto_1, manifiesto_2_previo):
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

    transcripciones = manifiesto_2.get("transcripciones", [])
    modelos_usados = set()
    for t in transcripciones:
        m = t.get("transcripcion", {}).get("modelo_usado", "")
        if m:
            modelos_usados.add(m)

    modelos_str = ", ".join([f"`{m}`" for m in modelos_usados]) if modelos_usados else "Ninguno (Descartados / Local)"

    resumen_md = "### 📊 Diagnóstico Multi-Agente (Paso 2 - OCR completado)\n\n"
    resumen_md += f"- **Cuadrantes Procesados con OCR (Agente 2):** `{len(transcripciones)}` de `{len(seleccionados)}` seleccionados\n"
    resumen_md += f"- **Motor(es) de Inferencia Utilizados:** {modelos_str}\n\n"
    resumen_md += "💡 *Tip:* **Haz clic en la miniatura de cualquier imagen de la tabla para abrir el recorte en alta resolución en una pestaña nueva.**\n\n"

    resumen_md += "| Recorte | Posición | Diana | Arquero | Club | Cat | Estado / Modelo |\n"
    resumen_md += "| :---: | :--- | :---: | :--- | :--- | :---: | :--- |\n"

    choices_inspector = []
    galeria = []

    for t in transcripciones:
        trans = t.get("transcripcion", {})
        modelo = trans.get("modelo_usado", "")
        arquero = trans.get("arquero", "Desconocido")
        target_leido = trans.get("target", "N/A")
        club = trans.get("club", "N/A")
        cat = trans.get("categoria", "N/A")
        tipo_j = t.get("tipo_juego", trans.get("tipo_juego", "clasificacion"))

        pag = t.get('pagina')
        pos = t.get('target_id')
        lbl_posicion = f"Pág {pag} - {tipo_j.capitalize()} (Pos {pos})"
        sin_p = trans.get("sin_puntos_registrados", False) or len(trans.get("series", [])) == 0
        es_info_p = (tipo_j == "informacion") or ("Portada" in trans.get("observacion", ""))

        if es_info_p:
            estado_modelo = "ℹ️ **Hoja de Información / Portada**"
        elif sin_p:
            estado_modelo = f"⚪ **Sin Puntos Registrados (`{tipo_j.capitalize()}`)**"
        else:
            if "Fallback" in modelo:
                estado_modelo = f"⚠️ `{modelo}`"
            else:
                estado_modelo = f"✅ `{modelo}`"

        lbl_inspector = f"{lbl_posicion} | Diana: {target_leido} | {arquero}"
        choices_inspector.append((lbl_inspector, lbl_inspector))

        p_img = t.get("ruta_recorte_procesada") or t.get("ruta_recorte_original")
        thumb_cell = _generar_thumb_html(p_img)

        resumen_md += f"| {thumb_cell} | **{lbl_posicion}** | `{target_leido}` | **{arquero}** | {club} | `{cat}` | {estado_modelo} |\n"

        if p_img and os.path.exists(p_img):
            tag_puntos = " [Sin Puntos]" if sin_p else ""
            galeria.append((p_img, f"{lbl_posicion} (Diana: {target_leido}) | Arquero: {arquero}{tag_puntos}"))

    primer_insp_key = choices_inspector[0][1] if choices_inspector else None

    raw_ocr_init = ""
    json_init = "{}"
    img_init = None
    if primer_insp_key:
        for t in transcripciones:
            pag = str(t.get('pagina'))
            pos = str(t.get('target_id'))
            if f"Pág {pag}" in primer_insp_key and pos in primer_insp_key:
                raw_ocr_init = t.get("transcripcion", {}).get("texto_raw_ocr", "")
                json_init = json.dumps(t.get("transcripcion", {}), indent=2, ensure_ascii=False)
                img_init = t.get("ruta_recorte_procesada") or t.get("ruta_recorte_original")
                break

    ruta_aud = manifiesto_2.get("ruta_archivo_auditoria_json", "")
    str_aud_json = "{}"
    if ruta_aud and os.path.exists(ruta_aud):
        try:
            with open(ruta_aud, "r", encoding="utf-8") as f_aud:
                str_aud_json = f_aud.read()
        except Exception:
            pass

    manifiesto_combinado = {
        "agente_1_manifiesto": manifiesto_1,
        "agente_2_manifiesto": manifiesto_2
    }
    json_str = json.dumps(manifiesto_combinado, indent=2, ensure_ascii=False)

    return (
        resumen_md,
        json_str,
        galeria,
        manifiesto_1,
        manifiesto_2,
        raw_ocr_init,
        json_init,
        img_init,
        gr.Dropdown(choices=choices_inspector, value=primer_insp_key, label="🔍 Seleccionar Arquero/Cuadrante para Inspeccionar Salida en Crudo"),
        str_aud_json
    )


def inspeccionar_recorte(opcion_seleccionada, manifiesto_2):
    if not manifiesto_2 or not opcion_seleccionada:
        return "⚠️ Selecciona un arquero para ver su salida en crudo.", "{}", None

    transcripciones = manifiesto_2.get("transcripciones", [])
    for t in transcripciones:
        pag = str(t.get('pagina'))
        pos = str(t.get('target_id'))
        trans = t.get("transcripcion", {})

        target_label = f"Pág {pag}"
        if target_label in opcion_seleccionada and pos in opcion_seleccionada:
            raw_text = trans.get("texto_raw_ocr", "(Sin texto en crudo)")
            p_img = t.get("ruta_recorte_procesada") or t.get("ruta_recorte_original")
            json_parsed = json.dumps(trans, indent=2, ensure_ascii=False)
            return raw_text, json_parsed, p_img

    return "⚠️ Recorte no encontrado.", "{}", None


# --- PASO 3: AUDITORÍA ---
def ejecutar_paso3_auditoria(manifiesto_1, manifiesto_2):
    if not manifiesto_2:
        empty_audit_json = json.dumps({"info": "Primero debes ejecutar el Paso 2 (OCR)."}, indent=2, ensure_ascii=False)
        return "⚠️ Primero debes ejecutar el Paso 2 (OCR).", "{}", gr.Dropdown(choices=[]), empty_audit_json, None, "{}"

    print(f"[UI] ⚖️ Ejecutando Paso 3 (Agente 3 - Auditoría Lógica y Reconciliación)...")
    manifiesto_3 = agente3.auditar_manifiesto_completo(manifiesto_2)

    auditorias = manifiesto_3.get("resultados_auditados", [])
    resumen_aud = manifiesto_3.get("resumen_auditoria", {})

    resumen_md = "### ⚖️ **Paso 3 Completado:** Auditoría Lógica, Reconciliación y Control de Certeza (Agente 3)\n\n"
    resumen_md += f"- **Cuadrantes Auditados:** `{resumen_aud.get('total_cuadrantes_procesados', 0)}`\n"
    resumen_md += f"- **Aprobados Automáticos (100% Certeza):** `{resumen_aud.get('aprobados_automaticos', 0)}` ✅\n"
    resumen_md += f"- **Requiere Revisión / Discrepancias:** `{resumen_aud.get('requiere_revision_humana', 0)}` ⚠️\n"
    resumen_md += f"- **Sin Puntos Confirmados:** `{resumen_aud.get('sin_puntos_confirmados', 0)}` ℹ️\n\n"

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

        if tot_ofic == 0 and tot_calc > 0:
            tot_cell = f"Papel: `N/A (Sin Total Escrito)` | Calc: `{tot_calc}`"
        elif tot_ofic > 0 and tot_ofic != tot_calc:
            tot_cell = f"⚠️ Papel: `{tot_ofic}` != Calc: `{tot_calc}`"
        else:
            tot_cell = f"Papel: `{tot_ofic}` | Calc: `{tot_calc}`"

        advs = item.get("advertencias", []) + item.get("errores", [])
        diag_str = "<br>".join([f"• {a}" for a in advs]) if advs else "✅ Sin discrepancias detectadas"

        resumen_md += f"| {thumb_cell} | **{lbl_posicion}** | `{target_leido}` | **{arquero}** | `{score}%` | {tag_estado} | {tot_cell} | {diag_str} |\n"

    primer_key = choices_inspector[0][1] if choices_inspector else None
    audit_init = json.dumps(auditorias[0], indent=2, ensure_ascii=False) if auditorias else "{}"

    ruta_aud = manifiesto_2.get("ruta_archivo_auditoria_json", "")
    str_aud_json = "{}"
    if ruta_aud and os.path.exists(ruta_aud):
        try:
            with open(ruta_aud, "r", encoding="utf-8") as f_aud:
                str_aud_json = f_aud.read()
        except Exception:
            pass

    manifiesto_combinado = {
        "agente_1_manifiesto": manifiesto_1,
        "agente_2_manifiesto": manifiesto_2,
        "agente_3_manifiesto": manifiesto_3
    }
    json_str = json.dumps(manifiesto_combinado, indent=2, ensure_ascii=False)

    return (
        resumen_md,
        json_str,
        gr.Dropdown(choices=choices_inspector, value=primer_key, label="⚖️ Seleccionar Arquero/Cuadrante para Inspeccionar Auditoría Agente 3"),
        audit_init,
        manifiesto_3,
        str_aud_json
    )


def inspeccionar_auditoria(opcion_seleccionada, manifiesto_3):
    if not manifiesto_3 or not opcion_seleccionada:
        return json.dumps({"info": "⚠️ Selecciona un arquero para ver el detalle de auditoría."}, indent=2, ensure_ascii=False)

    auditados = manifiesto_3.get("resultados_auditados", [])
    for item in auditados:
        pag = str(item.get('pagina'))
        pos = str(item.get('target_id'))

        target_label = f"Pág {pag}"
        if target_label in opcion_seleccionada and pos in opcion_seleccionada:
            return json.dumps(item, indent=2, ensure_ascii=False)

    return json.dumps({"info": "⚠️ Detalle de auditoría no encontrado."}, indent=2, ensure_ascii=False)


# --- CONSTRUCCIÓN DE LA INTERFAZ WEB GRADIO ---
def build_ui():
    with gr.Blocks(title="🎯 Sistema Multi-Agente - Tiro con Arco (v69)") as demo:
        gr.Markdown("# 🎯 Sistema Multi-Agente - Tiro con Arco (v69 - Mejoras Masivas de Calidad y Control Checkbox)")
        gr.Markdown("Flujo de Alta Usabilidad: **Paso 0** (Carga + Mejora Masiva de Páginas) ➡️ **Paso 1** (Segmentación + Mejora Masiva de Recortes) ➡️ **Paso 2** (Selección Masiva Checkbox + OCR 100% Sincronizado) ➡️ **Paso 3** (Auditoría Lógica y Deducción).")

        state_manifiesto_1 = gr.State(None)
        state_manifiesto_2 = gr.State(None)
        state_manifiesto_3 = gr.State(None)

        with gr.Row():
            with gr.Column(scale=1):
                file_input = gr.File(label="📂 Subir Planilla (Imagen PNG/JPG o PDF)", file_types=[".png", ".jpg", ".jpeg", ".pdf"])
                tipo_manual = gr.Dropdown(
                    label="Modo de Juego Manual (Opcional)",
                    choices=["Auto", "info", "eliminatoria_2", "clasificacion_1", "clasificacion_2", "clasificacion_4"],
                    value="Auto"
                )
                btn_cargar = gr.Button("🖼️ Cargar y Renderear Páginas", variant="primary")

                gr.Markdown("---")
                gr.Markdown("### 🛠️ Inspección y Mejora de Páginas (Paso 0)")
                dropdown_paginas = gr.Dropdown(choices=[], label="🔍 Seleccionar Página a Inspeccionar/Mejorar")
                with gr.Row():
                    btn_mejorar_pag = gr.Button("✨ Mejorar Página Seleccionada")
                    btn_deshacer_pag = gr.Button("↩️ Deshacer Página Seleccionada")
                with gr.Row():
                    btn_mejorar_todas_pag = gr.Button("✨ Mejorar TODAS las Páginas", variant="secondary")
                    btn_deshacer_todas_pag = gr.Button("↩️ Deshacer TODAS las Páginas", variant="secondary")
                btn_paso1 = gr.Button("✂️ Paso 1: Dividir Cuadrantes en Páginas", variant="primary")

                gr.Markdown("---")
                gr.Markdown("### 👁️ Selección y OCR (Paso 2)")
                checkbox_cuadrantes = gr.CheckboxGroup(choices=[], label="Seleccionar Cuadrantes Organizados por Página (Paso 2)")
                with gr.Row():
                    btn_seleccionar_validos = gr.Button("🎯 Seleccionar Cuadrantes Válidos", variant="primary")
                    btn_seleccionar_todos = gr.Button("☑️ Seleccionar Todos", variant="secondary")
                    btn_desmarcar_todos = gr.Button("☐ Desmarcar Todos", variant="secondary")
                btn_paso2 = gr.Button("👁️ Paso 2: Ejecutar OCR en Seleccionados", variant="secondary")

                gr.Markdown("---")
                gr.Markdown("### ⚖️ Auditoría Lógica (Paso 3)")
                btn_paso3 = gr.Button("⚖️ Paso 3: Ejecutar Auditoría Lógica (Agente 3)", variant="primary")

            with gr.Column(scale=2):
                status_paso0 = gr.Markdown("Esperando archivo...")
                galeria_paginas_out = gr.Gallery(label="🖼️ Galería de Páginas Físicas Extraídas", columns=2, preview=True)
                visor_pagina_out = gr.Image(label="🖼️ Visor de Página Seleccionada (Inspección y Enfoque)", interactive=False)

                gr.Markdown("---")
                diagnostico_out = gr.Markdown("Esperando división de cuadrantes (Paso 1)...")
                galeria_cuadrantes_out = gr.Gallery(label="✂️ Galería de Recortes de Cuadrantes", columns=2, preview=True)

                with gr.Row():
                    dropdown_cuadrantes = gr.Dropdown(choices=[], label="🔍 Seleccionar Recorte de Cuadrante a Inspeccionar/Mejorar")
                    visor_cuadrante_out = gr.Image(label="🖼️ Visor de Recorte de Cuadrante", interactive=False)

                with gr.Row():
                    btn_mejorar_recorte = gr.Button("✨ Mejorar Recorte Seleccionado")
                    btn_deshacer_recorte = gr.Button("↩️ Deshacer Recorte Seleccionado")
                with gr.Row():
                    btn_mejorar_todos_recortes = gr.Button("✨ Mejorar TODOS los Recortes", variant="secondary")
                    btn_deshacer_todos_recortes = gr.Button("↩️ Deshacer TODOS los Recortes", variant="secondary")

                json_out = gr.Code(label="Manifiesto JSON Completo (Agente 1 + Agente 2 + Agente 3)", language="json")

        gr.Markdown("---")
        gr.Markdown("## 📄 Auditoría JSON de Inferencia: Nemotron Raw vs JSON Refactorizado MVP")
        json_auditoria_nemotron = gr.Code(label="📄 Archivo de Auditoría Nemotron Raw vs JSON Refactorizado (auditoria_nemotron_raw_vs_refactorizado.json)", language="json")

        gr.Markdown("---")
        gr.Markdown("## ⚖️ Resultado de Auditoría Lógica y Control de Certeza (Paso 3)")

        with gr.Row():
            with gr.Column(scale=1):
                dropdown_audit = gr.Dropdown(choices=[], label="⚖️ Seleccionar Arquero/Cuadrante para Inspeccionar Auditoría Agente 3")
            with gr.Column(scale=2):
                json_audit_inspector = gr.Code(label="📋 Detalle de Reconciliación y Auditoría (Agente 3)", language="json")

        gr.Markdown("---")
        gr.Markdown("## 🔬 Inspección Detallada y Visor de Recortes (Paso 2)")

        with gr.Row():
            with gr.Column(scale=1):
                dropdown_inspector = gr.Dropdown(choices=[], label="🔍 Seleccionar Arquero/Cuadrante para Inspeccionar Salida en Crudo")
                image_inspector = gr.Image(label="🖼️ Visor de Recorte Interactivo (Zoom / Pan / Pantalla Completa)", interactive=False)
            with gr.Column(scale=2):
                raw_ocr_out = gr.Code(label="📜 Salida en Crudo Retornada por Nemotron / VLM (Texto Bruto)", language="markdown")
                json_inspector = gr.Code(label="🎯 Campos JSON Procesados y Cotejados", language="json")

        # --- EVENTOS ---
        btn_cargar.click(
            fn=cargar_documento_paso0,
            inputs=[file_input],
            outputs=[
                status_paso0, galeria_paginas_out, dropdown_paginas, visor_pagina_out, diagnostico_out,
                galeria_cuadrantes_out, dropdown_cuadrantes, visor_cuadrante_out,
                checkbox_cuadrantes, json_out
            ]
        )

        dropdown_paginas.change(
            fn=lambda num: (agente1.paginas_cache[int(num)]["ruta_actual"] if num and int(num) in agente1.paginas_cache else None),
            inputs=[dropdown_paginas],
            outputs=[visor_pagina_out]
        )

        btn_mejorar_pag.click(
            fn=mejorar_pagina_seleccionada,
            inputs=[dropdown_paginas],
            outputs=[status_paso0, galeria_paginas_out, dropdown_paginas, visor_pagina_out]
        )

        btn_deshacer_pag.click(
            fn=deshacer_pagina_seleccionada,
            inputs=[dropdown_paginas],
            outputs=[status_paso0, galeria_paginas_out, dropdown_paginas, visor_pagina_out]
        )

        btn_mejorar_todas_pag.click(
            fn=mejorar_todas_las_paginas_ui,
            inputs=[],
            outputs=[status_paso0, galeria_paginas_out, dropdown_paginas, visor_pagina_out]
        )

        btn_deshacer_todas_pag.click(
            fn=deshacer_todas_las_paginas_ui,
            inputs=[],
            outputs=[status_paso0, galeria_paginas_out, dropdown_paginas, visor_pagina_out]
        )

        btn_paso1.click(
            fn=ejecutar_paso1_segmentacion,
            inputs=[file_input, tipo_manual],
            outputs=[
                diagnostico_out, galeria_cuadrantes_out, dropdown_cuadrantes, visor_cuadrante_out,
                checkbox_cuadrantes, json_out, state_manifiesto_1
            ]
        )

        dropdown_cuadrantes.change(
            fn=lambda lbl: (agente1.recortes_cache[lbl]["ruta_recorte"] if lbl and lbl in agente1.recortes_cache else None),
            inputs=[dropdown_cuadrantes],
            outputs=[visor_cuadrante_out]
        )

        btn_mejorar_recorte.click(
            fn=mejorar_recorte_seleccionado,
            inputs=[dropdown_cuadrantes],
            outputs=[status_paso0, galeria_cuadrantes_out, dropdown_cuadrantes, visor_cuadrante_out]
        )

        btn_deshacer_recorte.click(
            fn=deshacer_recorte_seleccionado,
            inputs=[dropdown_cuadrantes],
            outputs=[status_paso0, galeria_cuadrantes_out, dropdown_cuadrantes, visor_cuadrante_out]
        )

        btn_mejorar_todos_recortes.click(
            fn=mejorar_todos_los_recortes_ui,
            inputs=[],
            outputs=[status_paso0, galeria_cuadrantes_out, dropdown_cuadrantes, visor_cuadrante_out]
        )

        btn_deshacer_todos_recortes.click(
            fn=deshacer_todos_los_recortes_ui,
            inputs=[],
            outputs=[status_paso0, galeria_cuadrantes_out, dropdown_cuadrantes, visor_cuadrante_out]
        )

        btn_seleccionar_validos.click(
            fn=seleccionar_cuadrantes_validos_ui,
            inputs=[state_manifiesto_1],
            outputs=[checkbox_cuadrantes]
        )

        btn_seleccionar_todos.click(
            fn=seleccionar_todos_cuadrantes_ui,
            inputs=[state_manifiesto_1],
            outputs=[checkbox_cuadrantes]
        )

        btn_desmarcar_todos.click(
            fn=desmarcar_todos_cuadrantes_ui,
            inputs=[],
            outputs=[checkbox_cuadrantes]
        )

        btn_paso2.click(
            fn=ejecutar_paso2_ocr,
            inputs=[checkbox_cuadrantes, state_manifiesto_1, state_manifiesto_2],
            outputs=[
                diagnostico_out, json_out, galeria_cuadrantes_out, state_manifiesto_1, state_manifiesto_2,
                raw_ocr_out, json_inspector, image_inspector, dropdown_inspector, json_auditoria_nemotron
            ]
        )

        dropdown_inspector.change(
            fn=inspeccionar_recorte,
            inputs=[dropdown_inspector, state_manifiesto_2],
            outputs=[raw_ocr_out, json_inspector, image_inspector]
        )

        dropdown_audit.change(
            fn=inspeccionar_auditoria,
            inputs=[dropdown_audit, state_manifiesto_3],
            outputs=[json_audit_inspector]
        )

        btn_paso3.click(
            fn=ejecutar_paso3_auditoria,
            inputs=[state_manifiesto_1, state_manifiesto_2],
            outputs=[diagnostico_out, json_out, dropdown_audit, json_audit_inspector, state_manifiesto_3, json_auditoria_nemotron]
        )

    return demo


def main():
    print("=" * 60)
    print("🚀 Servidor Principal Multi-Agente (v69) - Tiro con Arco")
    print("🌍 Abre tu navegador en: http://localhost:7860")
    print("=" * 60)
    demo = build_ui()
    allowed_directories = ["/tmp", tempfile.gettempdir(), os.getcwd(), "/app"]
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, allowed_paths=allowed_directories)


if __name__ == "__main__":
    main()
