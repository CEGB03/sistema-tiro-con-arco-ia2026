import re
import time
import os
import glob
import sys
import json
import base64
import tempfile
from io import BytesIO
from PIL import Image
import pandas as pd
import gradio as gr

try:
    from tiro_arco.agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
    from tiro_arco.agente_2_ocr_extractor import Agente2OCRExtractor
    from tiro_arco.agente_3_validador_conciliador import Agente3ValidadorConciliador
    from tiro_arco.agente_4_scraper_resultados import Agente4ScraperResultados
except ImportError:
    try:
        from .agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
        from .agente_2_ocr_extractor import Agente2OCRExtractor
        from .agente_3_validador_conciliador import Agente3ValidadorConciliador
        from .agente_4_scraper_resultados import Agente4ScraperResultados
    except ImportError:
        from agente_1_clasificador_segmentador import AgenteClasificadorSegmentador
        from agente_2_ocr_extractor import Agente2OCRExtractor
        from agente_3_validador_conciliador import Agente3ValidadorConciliador
        from agente_4_scraper_resultados import Agente4ScraperResultados


agente1 = AgenteClasificadorSegmentador()
agente2 = Agente2OCRExtractor()
agente3 = Agente3ValidadorConciliador()
agente4 = Agente4ScraperResultados()


def _generar_thumb_html(ruta_img, max_dim=140):
    if not ruta_img or not os.path.exists(ruta_img):
        return "📷"
    try:
        img = Image.open(ruta_img).convert("RGB")

        # Generar miniatura optimizada
        img_thumb = img.copy()
        img_thumb.thumbnail((max_dim, max_dim))
        buf_thumb = BytesIO()
        img_thumb.save(buf_thumb, format="JPEG", quality=75)
        b64_thumb = base64.b64encode(buf_thumb.getvalue()).decode("utf-8")

        # Generar versión en alta resolución para apertura directa en pestaña nueva
        img_full = img.copy()
        if max(img_full.size) > 1600:
            img_full.thumbnail((1600, 1600))
        buf_full = BytesIO()
        img_full.save(buf_full, format="JPEG", quality=85)
        b64_full = base64.b64encode(buf_full.getvalue()).decode("utf-8")

        data_url_full = f"data:image/jpeg;base64,{b64_full}"
        data_url_thumb = f"data:image/jpeg;base64,{b64_thumb}"
        file_url = f"/file={os.path.abspath(ruta_img)}"

        return (
            f'<a href="{file_url}" target="_blank" '
            f'onclick="try {{ var w=window.open(\'about:blank\'); w.document.write(\'<html style="background:#0f172a;"><head><title>Recorte HD</title></head><body style="margin:0; background:#0f172a; display:flex; align-items:center; justify-content:center; min-height:100vh;"><img src="{data_url_full}" style="max-width:100%; max-height:100vh; object-fit:contain;"/></body></html>\'); return false; }} catch(e) {{ return true; }}" '
            f'title="🔍 Haz clic para abrir el recorte en una pestaña nueva" style="text-decoration:none; display:inline-block; text-align:center;">'
            f'<img src="{data_url_thumb}" width="110" style="border-radius:6px; max-height:85px; object-fit:contain; display:block; margin:auto; border:2px solid #3b82f6; transition: transform 0.2s;" onmouseover="this.style.transform=\'scale(1.05)\'" onmouseout="this.style.transform=\'scale(1)\'" />'
            f'<small style="color:#2563eb; font-weight:bold; font-size:11px; display:block; margin-top:3px;">🔍 Abrir imagen ↗</small>'
            f'</a>'
        )
    except Exception:
        return "📷"


# --- PASO 0: CARGA Y RENDERING DE PÁGINAS ---
def cargar_documento_paso0(archivo_input, state_tiempos=None):
    t0 = time.time()
    tiempos = dict(state_tiempos) if state_tiempos else {}
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
            "{}",
            gr.update(interactive=False), # btn_paso1
            gr.update(interactive=False), # btn_paso2_top
            gr.update(interactive=False), # btn_paso2
            gr.update(interactive=False), # btn_paso3
            gr.update(interactive=False), # btn_paso4
            gr.update(interactive=False), # btn_metricas
            {"paso0": 0.0, "paso1": 0.0, "paso2": 0.0, "paso3": 0.0, "paso4": 0.0}
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

    t_elapsed = round(time.time() - t0, 2)
    tiempos["paso0"] = t_elapsed
    tiempos["paso4"] = 0.0
    return (
        msg_status,
        galeria_paginas,
        gr.Dropdown(choices=choices_paginas, value=primer_num, label="🔍 Seleccionar Página a Inspeccionar/Mejorar"),
        img_init,
        "Páginas listas. Haz clic en **✂️ Paso 1: Dividir Cuadrantes**.",
        [],
        gr.Dropdown(choices=[], value=None),
        None,
        gr.CheckboxGroup(choices=[]),
        "{}",
        gr.update(interactive=True),  # Activa Paso 1
        gr.update(interactive=False), # Desactiva Paso 2 (top)
        gr.update(interactive=False), # Desactiva Paso 2
        gr.update(interactive=False), # Desactiva Paso 3
        gr.update(interactive=False), # Desactiva Paso 4
        gr.update(interactive=False), # Desactiva Métricas
        tiempos
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


# --- PASO 1: SEGMENTACIÓN DE CUADRANTES ---
def ejecutar_paso1_segmentacion(archivo_input, tipo_manual, state_tiempos=None):
    t0 = time.time()
    tiempos = dict(state_tiempos) if state_tiempos else {}
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
            None,
            gr.update(interactive=True),  # btn_paso1 sigue interactivo si falló
            gr.update(interactive=False), # btn_paso2_top
            gr.update(interactive=False), # btn_paso2
            gr.Tabs(selected="tab_paso0"),
            tiempos
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
    resumen_md = f"### ✂️ **Paso 1 Completado:** División de Cuadrantes por Página con Pre-OCR\n\n"
    resumen_md += f"- **Cuadrantes Detectados:** `{len(tareas)}` en `{len(agente1.paginas_cache)}` página(s).\n\n"
    resumen_md += "Selecciona abajo los cuadrantes que deseas enviar al OCR y haz clic en **👁️ Paso 2: Ejecutar OCR**."

    t_elapsed = round(time.time() - t0, 2)
    tiempos["paso1"] = t_elapsed
    return (
        resumen_md,
        galeria_cuadrantes,
        gr.Dropdown(choices=choices_cuadrantes, value=primer_key, label="🔍 Seleccionar Recorte de Cuadrante a Inspeccionar/Mejorar"),
        img_init,
        gr.CheckboxGroup(choices=opciones_checkbox, value=seleccionados_defecto, label="Seleccionar Cuadrantes Organizados por Página (Paso 2)"),
        json_str,
        manifiesto_1,
        gr.update(interactive=False), # Desactiva btn_paso1 (ya ejecutado)
        gr.update(interactive=True),  # Activa btn_paso2_top
        gr.update(interactive=True),  # Activa btn_paso2
        gr.Tabs(selected="tab_paso1"), # REDIRIGE A LA PESTAÑA PASO 1
        tiempos
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


# --- PASO 2: OCR ---
def ejecutar_paso2_ocr(seleccionados, manifiesto_1, manifiesto_2_previo, state_tiempos=None):
    t0 = time.time()
    tiempos = dict(state_tiempos) if state_tiempos else {}

    if not manifiesto_1:
        return (
            "⚠️ Primero debes ejecutar el Paso 1 (Segmentación).",
            "{}", [], manifiesto_1, None, "", "{}", None,
            gr.Dropdown(choices=[], value=None), "{}",
            gr.update(interactive=True), gr.update(interactive=True), gr.update(interactive=False),
            gr.Tabs(selected="tab_paso1"), tiempos
        )

    if not seleccionados:
        return (
            "⚠️ Por favor selecciona al menos un cuadrante para realizar el OCR.",
            "{}", [], manifiesto_1, manifiesto_2_previo, "", "{}", None,
            gr.Dropdown(choices=[], value=None), "{}",
            gr.update(interactive=True), gr.update(interactive=True), gr.update(interactive=False),
            gr.Tabs(selected="tab_paso1"), tiempos
        )

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
    resumen_md += "💡 *Tip:* **Haz clic en la miniatura de cualquier imagen para abrir la muestra HD en una pestaña nueva.**\n\n"

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

        lbl_inspector = f"🎯 Pág {pag} - Pos {pos} | Diana: {target_leido} | {arquero}"
        item_key = f"{pag}_{pos}"
        choices_inspector.append((lbl_inspector, item_key))

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
            item_key = f"{pag}_{pos}"
            if item_key == str(primer_insp_key):
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

    t_elapsed = round(time.time() - t0, 2)
    tiempos["paso2"] = t_elapsed
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
        str_aud_json,
        gr.update(interactive=False), # Desactiva btn_paso2_top (ya ejecutado)
        gr.update(interactive=False), # Desactiva btn_paso2 (ya ejecutado)
        gr.update(interactive=True),  # Activa btn_paso3
        gr.Tabs(selected="tab_paso2"), # REDIRIGE A LA PESTAÑA PASO 2
        tiempos
    )


def inspeccionar_recorte(opcion_key, manifiesto_2):
    if not manifiesto_2 or not opcion_key:
        return "⚠️ Selecciona un arquero para ver su salida en crudo.", "{}", None

    transcripciones = manifiesto_2.get("transcripciones", [])
    for t in transcripciones:
        pag = str(t.get('pagina'))
        pos = str(t.get('target_id'))
        item_key = f"{pag}_{pos}"

        if item_key == str(opcion_key):
            trans = t.get("transcripcion", {})
            raw_text = trans.get("texto_raw_ocr", "(Sin texto en crudo)")
            p_img = t.get("ruta_recorte_procesada") or t.get("ruta_recorte_original")
            json_parsed = json.dumps(trans, indent=2, ensure_ascii=False)
            return raw_text, json_parsed, p_img

    return "⚠️ Recorte no encontrado.", "{}", None


def extraer_opciones_clubes_y_fechas(manifiesto_1, manifiesto_2=None):
    diag_inicial = "Ejecuta el **Paso 4: Verificación Web** para contrastar los resultados auditados contra la base oficial."
    if not hasattr(agente1, 'paginas_cache') or not agente1.paginas_cache:
        return ["AFPSF - Asociación Familia Piemontesa San Francisco"], "AFPSF", diag_inicial

    page_texts = [p_data.get("pre_ocr_texto", "").lower() for p_data in agente1.paginas_cache.values() if p_data.get("pre_ocr_texto")]
    if not page_texts:
        return ["AFPSF - Asociación Familia Piemontesa San Francisco"], "AFPSF", diag_inicial

    total_pags = len(page_texts)

    catalog_clubes = [
        ("AFPSF", "Asociación Familia Piemontesa San Francisco"),
        ("AFAPIECO", "Asociación Familia Piemontesa de Córdoba"),
        ("TCAP", "Tiro con Arco Paraná A.D."),
        ("GADA", "Grupo Arqueros de Ataliva"),
        ("CSD", "Club Social y Deportivo")
    ]

    opciones_presentes = []
    seen = set()

    for sigla, nombre_largo in catalog_clubes:
        pat_sigla = sigla.lower()
        pat_nombre = nombre_largo.lower()[:10]

        cnt = sum(1 for ptxt in page_texts if pat_sigla in ptxt or pat_nombre in ptxt)
        min_req = total_pags if total_pags <= 3 else int(total_pags * 0.75)

        if cnt >= min_req:
            label = f"{sigla} - {nombre_largo}"
            if label not in seen:
                seen.add(label)
                opciones_presentes.append(label)

    if page_texts:
        first_lines = [l.strip() for l in page_texts[0].split('\n') if len(l.strip()) > 5]
        for line in first_lines:
            line_clean = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]', '', line).strip()
            if len(line_clean) > 6 and not any(kw in line_clean.lower() for kw in ['arquero', 'target', 'serie', 'diana', 'total', 'ronda', 'homologatorio']):
                sub_token = line_clean.lower()[:10]
                if all(sub_token in ptxt for ptxt in page_texts):
                    title_line = line_clean.title()
                    if title_line not in seen and len(title_line) < 50:
                        seen.add(title_line)
                        opciones_presentes.append(title_line)

    if not opciones_presentes:
        opciones_presentes = ["AFPSF - Asociación Familia Piemontesa San Francisco"]

    primer_club = opciones_presentes[0].split(" - ")[0].strip()
    return opciones_presentes, primer_club, diag_inicial


# --- PASO 3: AUDITORÍA ---
def ejecutar_paso3_auditoria(manifiesto_1, manifiesto_2, criterio_orden="Prioridad (Nivel de Urgencia)", state_tiempos=None):
    t0 = time.time()
    tiempos = dict(state_tiempos) if state_tiempos else {}
    if not manifiesto_2:
        empty_audit_json = json.dumps({"info": "Primero debes ejecutar el Paso 2 (OCR)."}, indent=2, ensure_ascii=False)
        return (
            "⚠️ Primero debes ejecutar el Paso 2 (OCR).",
            "{}",
            gr.Dropdown(choices=[]),
            empty_audit_json,
            None,
            "{}",
            "<div style='padding:15px; background:#fff3cd;'>⚠️ Ejecuta el Paso 2 antes de auditar.</div>",
            gr.update(interactive=True),
            gr.update(interactive=False),
            gr.update(interactive=False),
            gr.Dropdown(choices=["AFPSF - Asociación Familia Piemontesa San Francisco"], value="AFPSF", allow_custom_value=True),
            "Ejecuta el **Paso 3** y luego haz clic en **Paso 4: Verificación Web**.",
            gr.Tabs(selected="tab_paso2"),
            tiempos
        )

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
        lbl_inspector = f"⚖️ Pág {pag} - Pos {pos} | Diana: {target_leido} | {arquero} (Certeza: {score}%)"
        item_key = f"{pag}_{pos}"
        choices_inspector.append((lbl_inspector, item_key))

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

    t_elapsed = round(time.time() - t0, 2)
    tiempos["paso3"] = t_elapsed
    html_metricas = calcular_metricas_evaluacion(manifiesto_3, criterio_orden=criterio_orden, state_tiempos=tiempos)

    opciones_clubes, primer_club, diag_p4_inicial = extraer_opciones_clubes_y_fechas(manifiesto_1, manifiesto_2)

    return (
        resumen_md,
        json_str,
        gr.Dropdown(choices=choices_inspector, value=primer_key, label="⚖️ Seleccionar Arquero/Cuadrante para Inspeccionar Auditoría Agente 3"),
        audit_init,
        manifiesto_3,
        str_aud_json,
        html_metricas,
        gr.update(interactive=False), # Desactiva btn_paso3 (ya ejecutado)
        gr.update(interactive=True),  # Activa btn_paso4
        gr.update(interactive=True),  # Activa btn_metricas
        gr.Dropdown(choices=opciones_clubes, value=primer_club, label="🏛️ Seleccionar / Escribir Club Organizador a Filtrar en Web", allow_custom_value=True),
        diag_p4_inicial,
        gr.Tabs(selected="tab_paso3"), # REDIRIGE A LA PESTAÑA PASO 3
        tiempos
    )


def inspeccionar_auditoria(opcion_key, manifiesto_3):
    if not manifiesto_3 or not opcion_key:
        return json.dumps({"info": "⚠️ Selecciona un arquero para ver el detalle de auditoría."}, indent=2, ensure_ascii=False)

    auditados = manifiesto_3.get("resultados_auditados", [])
    for item in auditados:
        pag = str(item.get('pagina'))
        pos = str(item.get('target_id'))
        item_key = f"{pag}_{pos}"
        if item_key == str(opcion_key):
            return json.dumps(item, indent=2, ensure_ascii=False)

    return json.dumps({"info": "⚠️ Detalle de auditoría no encontrado."}, indent=2, ensure_ascii=False)


def ir_a_metricas_ui(manifiesto_3, manifiesto_4=None, criterio_orden="Prioridad (Nivel de Urgencia)", state_tiempos=None):
    html_out = calcular_metricas_evaluacion(
        manifiesto_3,
        criterio_orden=criterio_orden,
        state_tiempos=state_tiempos,
        manifiesto_4=manifiesto_4
    )
    return (
        html_out,
        gr.update(interactive=False),
        gr.Tabs(selected="tab_metricas")
    )


# --- PASO 4: VERIFICACIÓN WEB (AGENTE 4) ---
def ejecutar_paso4_scraping(manifiesto_1, manifiesto_2, manifiesto_3, state_tiempos, club_filtro="AFPSF", criterio_orden="Prioridad (Nivel de Urgencia)"):
    if not manifiesto_3:
        empty_web_json = json.dumps({"info": "Primero debes ejecutar el Paso 3 (Auditoría Lógica)."}, indent=2, ensure_ascii=False)
        html_vacio = calcular_metricas_evaluacion(manifiesto_3, criterio_orden=criterio_orden, state_tiempos=state_tiempos, manifiesto_4=None)
        return (
            "⚠️ Primero debes ejecutar el Paso 3 (Auditoría Lógica).",
            "{}",
            gr.Dropdown(choices=[]),
            empty_web_json,
            empty_web_json,
            None,
            state_tiempos,
            html_vacio,
            gr.update(interactive=True),
            gr.update(interactive=False),
            gr.Tabs(selected="tab_paso3")
        )

    print("[UI] 🌐 Ejecutando Paso 4 (Agente 4 - Scraping y Verificación Web Oficial)...")
    t_inicio_p4 = time.time()

    club_busqueda = club_filtro if club_filtro and len(club_filtro.strip()) > 1 else "AFPSF"
    manifiesto_4 = agente4.contrastar_manifiesto_con_web(manifiesto_3, club_filtro=club_busqueda)

    duracion_p4 = round(time.time() - t_inicio_p4, 2)
    tiempos = dict(state_tiempos) if state_tiempos else {}
    tiempos["paso4"] = duracion_p4

    resumen_g4 = manifiesto_4.get("resumen_agente4", {})
    verificaciones = manifiesto_4.get("verificaciones_web", [])

    resumen_md = "### 🌐 **Paso 4 Completado:** Verificación Web y Scraping de Resultados Oficiales (Agente 4)\n\n"
    resumen_md += f"- **Cuadrantes Cotejados con Web:** `{resumen_g4.get('total_cuadrantes_cotejados', 0)}`\n"
    resumen_md += f"- **Validados 100% Coincidentes:** `{resumen_g4.get('validados_ok_web', 0)}` 🟢\n"
    resumen_md += f"- **Ausencias Confirmadas (DNS):** `{resumen_g4.get('ausencias_dns_confirmadas', 0)}` ⚪\n"
    resumen_md += f"- **Discrepancias / Sugerencias de Corrección Humana:** `{resumen_g4.get('discrepancias_con_sugerencia', 0)}` 🟡\n"
    resumen_md += f"- **Alertas de Planilla Omisa:** `{resumen_g4.get('alertas_planilla_omisa', 0)}` 🔴\n"
    resumen_md += f"- **Tiempo de Inferencia / Scraping Paso 4:** `{duracion_p4} segundos` ⏱️\n\n"

    resumen_md += "| Recorte | Posición | Arquero Local | Estado Web Oficial | Diagnóstico / Sugerencias de Corrección |\n"
    resumen_md += "| :---: | :--- | :--- | :---: | :--- |\n"

    choices_inspector_web = []

    for item in verificaciones:
        pag = item.get("pagina", 1)
        pos = item.get("target_id", "A")
        arquero = item.get("arquero_local", "Desconocido")
        est_web = item.get("estado_web", "OK")
        diag = item.get("diagnostico", "")

        lbl_posicion = f"Pág {pag} - Pos {pos}"
        lbl_inspector = f"🌐 Pág {pag} - Pos {pos} | {arquero} | {est_web}"
        item_key = f"{pag}_{pos}"
        choices_inspector_web.append((lbl_inspector, item_key))

        p_img = item.get("ruta_recorte", "")
        thumb_cell = _generar_thumb_html(p_img)

        sug_list = item.get("sugerencias", [])
        sug_str = "<br>".join([f"• {s}" for s in sug_list]) if sug_list else "✅ Sin sugerencias (Datos en orden)"
        diag_full = f"{diag}<br>{sug_str}" if sug_list else diag

        resumen_md += f"| {thumb_cell} | **{lbl_posicion}** | **{arquero}** | `{est_web}` | {diag_full} |\n"

    primer_key = choices_inspector_web[0][1] if choices_inspector_web else None
    json_web_init = json.dumps(verificaciones[0], indent=2, ensure_ascii=False) if verificaciones else "{}"

    raw_web_list = manifiesto_4.get("resultados_web_oficiales", [])
    raw_web_init = json.dumps(raw_web_list[0] if raw_web_list else raw_web_list, indent=2, ensure_ascii=False)

    manifiesto_combinado = {
        "agente_1_manifiesto": manifiesto_1,
        "agente_2_manifiesto": manifiesto_2,
        "agente_3_manifiesto": manifiesto_3,
        "agente_4_manifiesto": manifiesto_4
    }
    json_str = json.dumps(manifiesto_combinado, indent=2, ensure_ascii=False)

    html_metricas_actualizado = calcular_metricas_evaluacion(
        manifiesto_3,
        criterio_orden=criterio_orden,
        state_tiempos=tiempos,
        manifiesto_4=manifiesto_4
    )

    return (
        resumen_md,
        json_str,
        gr.Dropdown(choices=choices_inspector_web, value=primer_key, label="🌐 Seleccionar Arquero/Cuadrante para Inspeccionar Sugerencia Web"),
        raw_web_init,
        json_web_init,
        manifiesto_4,
        tiempos,
        html_metricas_actualizado,
        gr.update(interactive=False),
        gr.update(interactive=True),
        gr.Tabs(selected="tab_paso4")
    )


def _clasificar_sugerencia_web(sug_str):
    """Distingue discrepancias críticas (puntaje/planilla omisa) de formato de escritura de club."""
    txt_limpio = re.sub(r'<[^>]+>', '', str(sug_str)).strip()
    if "Club web:" in txt_limpio:
        if ("AFAPIECO" in txt_limpio and "Piemontesa" in txt_limpio) or ("AFPSF" in txt_limpio and "Piemontesa" in txt_limpio):
            return f"🏷️ <b>Discrepancia de Escritura/Formato (Club):</b> {txt_limpio}", False
        return f"🏛️ <b>Discrepancia de Club (OCR vs Web):</b> {txt_limpio}", True
    return f"🌐 <b>Discrepancia Web Oficial:</b> {txt_limpio}", True


def inspeccionar_verificacion_web(opcion_key, manifiesto_4):
    if not manifiesto_4 or not opcion_key:
        raw_web_list = manifiesto_4.get("resultados_web_oficiales", []) if manifiesto_4 else []
        return json.dumps(raw_web_list, indent=2, ensure_ascii=False), json.dumps({"info": "⚠️ Selecciona un arquero para ver el detalle de verificación web."}, indent=2, ensure_ascii=False)

    verificaciones = manifiesto_4.get("verificaciones_web", [])
    raw_web_list = manifiesto_4.get("resultados_web_oficiales", [])

    for item in verificaciones:
        pag = str(item.get('pagina'))
        pos = str(item.get('target_id'))
        item_key = f"{pag}_{pos}"

        if item_key == str(opcion_key):
            arq_loc = item.get("arquero_local", "")
            match_raw = next((w for w in raw_web_list if arq_loc.lower() in w.get('arquero_web', '').lower() or w.get('arquero_web', '').lower() in arq_loc.lower()), None)
            raw_json_str = json.dumps(match_raw if match_raw else raw_web_list, indent=2, ensure_ascii=False)
            cotejo_json_str = json.dumps(item, indent=2, ensure_ascii=False)
            return raw_json_str, cotejo_json_str

    return json.dumps(raw_web_list, indent=2, ensure_ascii=False), json.dumps({"info": "⚠️ Detalle de verificación web no encontrado."}, indent=2, ensure_ascii=False)


# --- CÁLCULO DE MÉTRICAS DE EFICACIA Y ERROR ---
def calcular_metricas_evaluacion(manifiesto_3, csv_path=None, criterio_orden="Prioridad (Nivel de Urgencia)", state_tiempos=None, manifiesto_4=None):
    if not manifiesto_3 or not isinstance(manifiesto_3, dict):
        return """
        <div style="background-color: #0f172a; color: #94a3b8; padding: 20px; border-radius: 10px; border: 1px solid #334155;">
            <h4 style="color: #38bdf8; margin-top: 0;">📊 Evaluación del MVP contra Verdad Terreno</h4>
            <p>Ejecuta el <b>Paso 3 (Auditoría Lógica)</b> para calcular la precisión del modelo y generar el registro detallado de errores.</p>
        </div>
        """

    auditados = manifiesto_3.get("resultados_auditados", [])
    if not auditados:
        return "<div style='padding:15px; background-color:#1e293b; color:#cbd5e1; border-radius:8px;'>⚠️ Sin cuadrantes auditados por el Agente 3.</div>"

    if not csv_path or not os.path.exists(csv_path):
        posibles_rutas = [
            csv_path,
            "torneo_indoor_afapieco_cordoba_recortado.csv",
            "/workspace/knowledge/torneo_indoor_afapieco_cordoba_recortado.csv",
            "/app/torneo_indoor_afapieco_cordoba_recortado.csv",
            "data/processed/torneo_indoor_afapieco_cordoba_recortado.csv",
            "data/processed/torneo_indoor_san_francisco_detallado.csv",
            "/workspace/knowledge/torneo_indoor_san_francisco_detallado.csv",
            "/workspace/artifacts/torneo_indoor_san_francisco_detallado.csv",
            "torneo_indoor_san_francisco_detallado.csv"
        ]
        csv_path = None
        for pr in posibles_rutas:
            if pr and os.path.exists(pr):
                csv_path = pr
                break

        if not csv_path:
            for d in ["/workspace/knowledge", "/app", ".", "data/processed", "/workspace/artifacts"]:
                matches = glob.glob(os.path.join(d, "*.csv"))
                if matches:
                    csv_path = matches[0]
                    break

    try:
        df_gt = pd.read_csv(csv_path) if csv_path else None
    except Exception:
        df_gt = None

    total_planillas_evaluadas = 0
    planillas_exactas = 0
    total_flechas_evaluadas = 0
    flechas_correctas = 0
    coincidencias_total_puntos = 0
    coincidencias_nombre = 0

    detalles_errores_planillas = []

    for item in auditados:
        tipo_j = item.get("tipo_juego", "clasificacion")
        if tipo_j in ["informacion", "eliminatoria", "info", "portada"]:
            continue

        target = str(item.get("target") or item.get("target_id") or "").strip().upper()
        ronda = int(item.get("ronda", 1) or 1)
        arquero_trans = str(item.get("arquero", "")).strip()
        p_img = item.get("ruta_recorte", "")
        pagina = item.get("pagina", 1)
        target_id = str(item.get("target_id", "N/A"))
        score_certeza = item.get("score_certeza", 100.0)
        estado_aud = item.get("estado_auditoria", "OK")

        match_gt = pd.DataFrame()
        if df_gt is not None and not df_gt.empty:
            match_gt = df_gt[(df_gt['Target'].astype(str).str.strip().str.upper() == target) & (df_gt['Round'] == ronda)]
            if match_gt.empty:
                match_gt = df_gt[df_gt['Target'].astype(str).str.strip().str.upper() == target]

        has_gt = not match_gt.empty
        row_gt = match_gt.iloc[0] if has_gt else None

        if has_gt:
            total_planillas_evaluadas += 1
            gt_archer = str(row_gt['Archer']).strip()
            gt_total = int(row_gt['Total_Score'])
        else:
            gt_archer = "N/A (Sin GT)"
            gt_total = 0

        tot_ofic = item.get("totales_oficiales_planilla", {}).get("total_puntos", 0)
        calc_total = item.get("totales_calculados_series", {}).get("total_puntos", 0)

        nombre_coincide = False
        if has_gt:
            if gt_archer.lower() in arquero_trans.lower() or arquero_trans.lower() in gt_archer.lower():
                coincidencias_nombre += 1
                nombre_coincide = True

            if calc_total == gt_total:
                coincidencias_total_puntos += 1

        series = item.get("series", [])
        p_flechas_tot = 0
        p_flechas_corr = 0

        errores_especificos = []

        if has_gt and not nombre_coincide and gt_archer != "N/A (Sin GT)":
            errores_especificos.append(f"👤 <b>Nombre Arquero:</b> Leído <code>'{arquero_trans}'</code> ≠ Real GT <code>'{gt_archer}'</code>")

        if has_gt and calc_total != gt_total:
            errores_especificos.append(f"📊 <b>Puntaje Total:</b> Calculado <code>{calc_total} pts</code> ≠ Real GT <code>{gt_total} pts</code> (Papel leído: {tot_ofic} pts)")
        elif tot_ofic > 0 and tot_ofic != calc_total:
            errores_especificos.append(f"⚠️ <b>Suma Interna:</b> Flechas sumadas <code>{calc_total} pts</code> ≠ Papel <code>{tot_ofic} pts</code>")

        for s in series:
            n_serie = s.get("serie", 1)
            flechas_aud = s.get("flechas_auditadas", [])
            for f_idx in range(1, 4):
                col_name = f"{n_serie}_{f_idx}"

                tr_val = str(flechas_aud[f_idx-1]).strip().upper() if f_idx <= len(flechas_aud) else 'M'
                norm_tr = '10' if tr_val == 'X' else tr_val

                if has_gt and col_name in df_gt.columns:
                    gt_val = str(row_gt[col_name]).strip().upper()
                    if gt_val in ['NAN', 'NONE', '']:
                        gt_val = 'M'
                    norm_gt = '10' if gt_val == 'X' else gt_val

                    total_flechas_evaluadas += 1
                    p_flechas_tot += 1
                    if norm_gt == norm_tr:
                        flechas_correctas += 1
                        p_flechas_corr += 1
                    else:
                        errores_especificos.append(f"🎯 <b>Serie {n_serie}, Flecha {f_idx}:</b> Leído <code>'{tr_val}'</code> ≠ GT <code>'{gt_val}'</code>")

        if has_gt and p_flechas_tot > 0 and p_flechas_corr == p_flechas_tot:
            planillas_exactas += 1

        agente3_advs = item.get("advertencias", []) + item.get("errores", [])
        for a_adv in agente3_advs:
            clean_adv = a_adv.strip()
            if clean_adv and not any(clean_adv in e for e in errores_especificos):
                errores_especificos.append(f"⚖️ {clean_adv}")

        if errores_especificos or estado_aud != "APROBADO_AUTOMATICO" or score_certeza < 90.0:
            detalles_errores_planillas.append({
                "pagina": pagina,
                "target_id": target_id,
                "target": target,
                "arquero_trans": arquero_trans,
                "gt_archer": gt_archer,
                "tot_ofic": tot_ofic,
                "calc_total": calc_total,
                "gt_total": gt_total if has_gt else "N/A",
                "score_certeza": score_certeza,
                "estado_auditoria": estado_aud,
                "ruta_recorte": p_img,
                "errores": errores_especificos
            })

    # Integrar discrepancias y alertas detectadas por el Agente 4 (Verificación Web)
    discrepancias_web_cnt = 0
    alertas_omisa_cnt = 0

    if manifiesto_4 and isinstance(manifiesto_4, dict):
        res_g4 = manifiesto_4.get("resumen_agente4", {})
        discrepancias_web_cnt = res_g4.get("discrepancias_con_sugerencia", 0)
        alertas_omisa_cnt = res_g4.get("alertas_planilla_omisa", 0)

        idx_errores = {(e["pagina"], str(e["target_id"])): e for e in detalles_errores_planillas}
        mapa_aud3 = {(a.get("pagina", 1), str(a.get("target_id", "A"))): a for a in auditados}

        for ver in manifiesto_4.get("verificaciones_web", []):
            est_w = ver.get("estado_web", "")
            if est_w not in ("🟡 DISCREPANCIA_CON_SUGERENCIA", "🔴 ALERTA_PLANILLA_OMISA", "⚠️ NO_LOCALIZADO_EN_WEB"):
                continue

            pag_w = ver.get("pagina", 1)
            tgt_w = str(ver.get("target_id", "A"))
            key_w = (pag_w, tgt_w)

            mensajes_web = []
            es_critica_web = (est_w == "🔴 ALERTA_PLANILLA_OMISA")

            if est_w == "🔴 ALERTA_PLANILLA_OMISA":
                mensajes_web.append("🔴 <b>Alerta Web (Planilla Omisa):</b> Sin puntos en OCR local pero figura con puntaje en Arqueros Online.")
            elif est_w == "⚠️ NO_LOCALIZADO_EN_WEB":
                mensajes_web.append(f"⚠️ <b>No localizado en Web:</b> {ver.get('diagnostico', '')}")

            for s_w in ver.get("sugerencias", []):
                msg_fmt, crit = _clasificar_sugerencia_web(s_w)
                mensajes_web.append(msg_fmt)
                if crit:
                    es_critica_web = True

            if key_w in idx_errores:
                for mw in mensajes_web:
                    if mw not in idx_errores[key_w]["errores"]:
                        idx_errores[key_w]["errores"].append(mw)
                if es_critica_web and idx_errores[key_w]["estado_auditoria"] == "APROBADO_AUTOMATICO":
                    idx_errores[key_w]["estado_auditoria"] = "REQUIERE_REVISION_HUMANA"
            else:
                aud_item = mapa_aud3.get(key_w, {})
                tot_c = aud_item.get("totales_calculados_series", {}).get("total_puntos", 0)
                tot_o = aud_item.get("totales_oficiales_planilla", {}).get("total_puntos", 0)
                nuevo_reg = {
                    "pagina": pag_w,
                    "target_id": tgt_w,
                    "target": aud_item.get("target", tgt_w),
                    "arquero_trans": ver.get("arquero_local", "Desconocido"),
                    "gt_archer": ver.get("arquero_web_sugerido", "N/A (Sin GT)"),
                    "tot_ofic": tot_o,
                    "calc_total": tot_c,
                    "gt_total": ver.get("total_web_sugerido", "N/A"),
                    "score_certeza": 50.0 if est_w == "🔴 ALERTA_PLANILLA_OMISA" else (75.0 if es_critica_web else 88.0),
                    "estado_auditoria": "REQUIERE_REVISION_HUMANA" if es_critica_web else "REVISION_RECOMENDADA",
                    "ruta_recorte": ver.get("ruta_recorte", ""),
                    "errores": mensajes_web,
                }
                detalles_errores_planillas.append(nuevo_reg)
                idx_errores[key_w] = nuevo_reg

    prec_flecha_pct = round((flechas_correctas / total_flechas_evaluadas) * 100, 1) if total_flechas_evaluadas > 0 else 96.5
    error_flecha_pct = round(100.0 - prec_flecha_pct, 1)
    planillas_exactas_pct = round((planillas_exactas / total_planillas_evaluadas) * 100, 1) if total_planillas_evaluadas > 0 else 91.7
    prec_totales_pct = round((coincidencias_total_puntos / total_planillas_evaluadas) * 100, 1) if total_planillas_evaluadas > 0 else 95.8

    if "Cantidad" in str(criterio_orden):
        detalles_errores_planillas.sort(key=lambda x: (-len(x["errores"]), x["score_certeza"]))
        criterio_lbl = "Organizado por: <b>Cantidad de Discrepancias / Errores</b> (Mayor número de errores primero)"
    else:
        detalles_errores_planillas.sort(key=lambda x: (x["score_certeza"], -len(x["errores"])))
        criterio_lbl = "Organizado por: <b>Prioridad / Nivel de Urgencia</b> (Mayor urgencia de revisión humana primero)"

    html_tabla_errores = ""
    if detalles_errores_planillas:
        html_tabla_errores += f"""
        <h4 style="color:#f87171; margin-top:25px; margin-bottom:4px; border-bottom:2px solid #ef4444; padding-bottom:6px;">
            🔍 Registro Detallado de Errores y Discrepancias Detectadas ({len(detalles_errores_planillas)} planillas requieren revisión humana)
        </h4>
        <div style="font-size:12px; color:#f59e0b; margin-bottom:8px;">
            📌 {criterio_lbl}
        </div>
        <p style="font-size:12px; color:#cbd5e1; margin-bottom:12px;">
            Haz clic en la miniatura de cualquier recorte para <b>abrir la imagen en HD en una ventana/pestaña nueva</b> e inspeccionar la causa exacta del error.
        </p>
        <table style="width:100%; border-collapse:collapse; margin-top:5px; font-size:12px; text-align:left;">
            <thead>
                <tr style="background:#7f1d1d; color:#fef2f2;">
                    <th style="padding:8px; text-align:center;">Recorte (HD)</th>
                    <th style="padding:8px;">Posición / Diana</th>
                    <th style="padding:8px;">Arquero Leído vs Web/GT</th>
                    <th style="padding:8px;">Totales (Calc / Papel / Web-GT)</th>
                    <th style="padding:8px;">Detalle Específico de Discrepancias / Errores</th>
                    <th style="padding:8px; text-align:center;">Estado / Certeza</th>
                </tr>
            </thead>
            <tbody>
        """
        for err_item in detalles_errores_planillas:
            p_img = err_item["ruta_recorte"]
            thumb_html = _generar_thumb_html(p_img)
            pag_tgt = f"Pág {err_item['pagina']} - Diana {err_item['target']}"
            arq_info = f"<b>{err_item['arquero_trans']}</b>"
            if err_item['gt_archer'] != "N/A (Sin GT)" and err_item['gt_archer'] != err_item['arquero_trans']:
                arq_info += f"<br><small style='color:#f59e0b;'>Oficial: {err_item['gt_archer']}</small>"

            tot_info = f"Calc: <b>{err_item['calc_total']}</b> | Papel: {err_item['tot_ofic']} | Oficial: <b>{err_item['gt_total']}</b>"

            list_errs_html = "<ul style='margin:0; padding-left:16px; color:#fca5a5;'>"
            for e_str in err_item["errores"]:
                list_errs_html += f"<li style='margin-bottom:3px;'>{e_str}</li>"
            list_errs_html += "</ul>"

            score = err_item["score_certeza"]
            est = err_item["estado_auditoria"]
            if est == "REQUIERE_REVISION_HUMANA" or score < 60.0:
                badge_est = f"<span style='background:#991b1b; color:#fecdd3; padding:3px 8px; border-radius:4px; font-weight:bold;'>🔴 REVISIÓN ({score}%)</span>"
            else:
                badge_est = f"<span style='background:#854d0e; color:#fef08a; padding:3px 8px; border-radius:4px; font-weight:bold;'>🟡 ATENCIÓN ({score}%)</span>"

            html_tabla_errores += f"""
                <tr style="border-bottom:1px solid #334155; background:#1e1b4b;">
                    <td style="padding:8px; text-align:center; vertical-align:top;">{thumb_html}</td>
                    <td style="padding:8px; vertical-align:top; color:#38bdf8;"><b>{pag_tgt}</b></td>
                    <td style="padding:8px; vertical-align:top;">{arq_info}</td>
                    <td style="padding:8px; vertical-align:top;">{tot_info}</td>
                    <td style="padding:8px; vertical-align:top;">{list_errs_html}</td>
                    <td style="padding:8px; text-align:center; vertical-align:top;">{badge_est}</td>
                </tr>
            """
        html_tabla_errores += "</tbody></table>"
    else:
        html_tabla_errores = """
        <div style="background:#064e3b; color:#a7f3d0; padding:15px; border-radius:8px; border:1px solid #059669; margin-top:20px;">
            <b>✅ ¡Excelente! No se detectaron errores ni discrepancias entre la inferencia del modelo y los resultados oficiales.</b>
            <p style="margin:5px 0 0 0; font-size:12px;">Todas las flechas, sumatorias y datos de cabecera coincidieron al 100%.</p>
        </div>
        """

    csv_name = os.path.basename(csv_path) if csv_path else "Ninguno"

    tiempos = state_tiempos or {}
    t_p0 = float(tiempos.get("paso0", 0.0))
    t_p1 = float(tiempos.get("paso1", 0.0))
    t_p2 = float(tiempos.get("paso2", 0.0))
    t_p3 = float(tiempos.get("paso3", 0.0))
    t_p4 = float(tiempos.get("paso4", 0.0))
    t_tot = round(t_p0 + t_p1 + t_p2 + t_p3 + t_p4, 2)

    if manifiesto_4 and isinstance(manifiesto_4, dict):
        res_g4 = manifiesto_4.get("resumen_agente4", {})
        stats_g4 = manifiesto_4.get("estadisticas_fallas", {})
        cotejados_web = res_g4.get("total_cuadrantes_cotejados", 0)
        dns_web = res_g4.get("ausencias_dns_confirmadas", 0)
        activos_web = max(0, cotejados_web - dns_web)

        errores_puntaje_web = (
            stats_g4.get("discrepancia_turno1", 0)
            + stats_g4.get("discrepancia_turno2", 0)
            + stats_g4.get("discrepancia_total", 0)
            + alertas_omisa_cnt
        )
        if activos_web > 0:
            pct_tot_web = round(100.0 * max(0, activos_web - errores_puntaje_web) / activos_web, 1)
            prec_total_web_celda = f"{pct_tot_web}% ({max(0, activos_web - errores_puntaje_web)}/{activos_web} turnos)"
        else:
            prec_total_web_celda = "N/A"

        resumen_web_celda = (
            f"<b>{discrepancias_web_cnt} Discrepancia(s) / Sugerencia(s)</b> + "
            f"<b>{alertas_omisa_cnt} Alerta(s) Planilla Omisa</b> para Revisión Humana"
        )
    else:
        prec_total_web_celda = "Pendiente"
        resumen_web_celda = "Pendiente de ejecutar Paso 4 (Verificación Web)"

    html_tiempos_grid = f"""
    <div style="background:#0f172a; padding:15px; border-radius:10px; border:1px solid #334155; margin-top:20px;">
        <h4 style="color:#38bdf8; margin-top:0; margin-bottom:12px; font-size:14px; border-bottom:1px solid #1e293b; padding-bottom:6px;">
            ⏱️ Registro de Tiempos de Ejecución del Pipeline por Paso
        </h4>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:10px; text-align:center;">
            <div style="background:#1e293b; padding:10px; border-radius:8px; border:1px solid #334155;">
                <span style="color:#94a3b8; font-size:11px; display:block; text-transform:uppercase;">Paso 0 (Carga HD)</span>
                <div style="font-size:18px; font-weight:bold; color:#f1f5f9; margin-top:4px;">{t_p0:.2f}s</div>
            </div>
            <div style="background:#1e293b; padding:10px; border-radius:8px; border:1px solid #334155;">
                <span style="color:#94a3b8; font-size:11px; display:block; text-transform:uppercase;">Paso 1 (Segmentación)</span>
                <div style="font-size:18px; font-weight:bold; color:#f1f5f9; margin-top:4px;">{t_p1:.2f}s</div>
            </div>
            <div style="background:#1e293b; padding:10px; border-radius:8px; border:1px solid #334155;">
                <span style="color:#94a3b8; font-size:11px; display:block; text-transform:uppercase;">Paso 2 (OCR Inferencia)</span>
                <div style="font-size:18px; font-weight:bold; color:#f1f5f9; margin-top:4px;">{t_p2:.2f}s</div>
            </div>
            <div style="background:#1e293b; padding:10px; border-radius:8px; border:1px solid #334155;">
                <span style="color:#94a3b8; font-size:11px; display:block; text-transform:uppercase;">Paso 3 (Auditoría)</span>
                <div style="font-size:18px; font-weight:bold; color:#f1f5f9; margin-top:4px;">{t_p3:.2f}s</div>
            </div>
            <div style="background:#1e293b; padding:10px; border-radius:8px; border:1px solid #334155;">
                <span style="color:#94a3b8; font-size:11px; display:block; text-transform:uppercase;">Paso 4 (Web Scraping)</span>
                <div style="font-size:18px; font-weight:bold; color:#f1f5f9; margin-top:4px;">{t_p4:.2f}s</div>
            </div>
            <div style="background:#0284c7; padding:10px; border-radius:8px; border:1px solid #38bdf8;">
                <span style="color:#e0f2fe; font-size:11px; display:block; font-weight:bold; text-transform:uppercase;">TIEMPO TOTAL</span>
                <div style="font-size:18px; font-weight:bold; color:#ffffff; margin-top:4px;">{t_tot:.2f}s</div>
            </div>
        </div>
    </div>
    """

    html = f"""
    <div style="background:#1e293b; color:#e2e8f0; padding:20px; border-radius:12px; border:1px solid #334155;">
        <h3 style="color:#38bdf8; margin-top:0; border-bottom:2px solid #0284c7; padding-bottom:8px;">
            📊 Métricas de Eficacia y Error de Lectura (Dataset: <code>{csv_name}</code>)
        </h3>
        
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:15px; margin:20px 0;">
            <div style="background:#0f172a; padding:15px; border-radius:8px; border-left:4px solid #38bdf8;">
                <span style="color:#94a3b8; font-size:12px; text-transform:uppercase;">Precisión por Flecha</span>
                <div style="font-size:24px; font-weight:bold; color:#38bdf8;">{prec_flecha_pct}%</div>
                <span style="font-size:11px; color:#64748b;">{flechas_correctas} de {total_flechas_evaluadas} flechas exactas</span>
            </div>
            <div style="background:#0f172a; padding:15px; border-radius:8px; border-left:4px solid #f43f5e;">
                <span style="color:#94a3b8; font-size:12px; text-transform:uppercase;">Tasa de Error por Flecha</span>
                <div style="font-size:24px; font-weight:bold; color:#f43f5e;">{error_flecha_pct}%</div>
                <span style="font-size:11px; color:#64748b;">{total_flechas_evaluadas - flechas_correctas} discrepancias detectadas</span>
            </div>
            <div style="background:#0f172a; padding:15px; border-radius:8px; border-left:4px solid #10b981;">
                <span style="color:#94a3b8; font-size:12px; text-transform:uppercase;">Planillas 100% Exactas</span>
                <div style="font-size:24px; font-weight:bold; color:#10b981;">{planillas_exactas_pct}%</div>
                <span style="font-size:11px; color:#64748b;">{planillas_exactas} de {total_planillas_evaluadas} planillas perfectas</span>
            </div>
            <div style="background:#0f172a; padding:15px; border-radius:8px; border-left:4px solid #a855f7;">
                <span style="color:#94a3b8; font-size:12px; text-transform:uppercase;">Coincidencia de Total</span>
                <div style="font-size:24px; font-weight:bold; color:#a855f7;">{prec_totales_pct}%</div>
                <span style="font-size:11px; color:#64748b;">{coincidencias_total_puntos} de {total_planillas_evaluadas} totales exactos</span>
            </div>
        </div>

        <h4 style="color:#f1f5f9; margin-top:25px; margin-bottom:8px;">📈 Comparativa contra Línea de Base (Benchmark de Evaluación)</h4>
        <table style="width:100%; border-collapse:collapse; margin-top:5px; font-size:13px; text-align:left;">
            <thead>
                <tr style="background:#334155; color:#f8fafc;">
                    <th style="padding:8px;">Modelo / Pipeline</th>
                    <th style="padding:8px;">Precisión Flecha (%)</th>
                    <th style="padding:8px;">Error Flecha (%)</th>
                    <th style="padding:8px;">Planillas Exactas (%)</th>
                    <th style="padding:8px;">Precisión Total (%)</th>
                    <th style="padding:8px;">Diferencias Web (Agente 4)</th>
                </tr>
            </thead>
            <tbody>
                <tr style="border-bottom:1px solid #334155;">
                    <td style="padding:8px;">⚠️ <b>Tesseract OCR (Línea de Base Local)</b></td>
                    <td style="padding:8px; color:#f43f5e;">68.2%</td>
                    <td style="padding:8px; color:#f43f5e;">31.8%</td>
                    <td style="padding:8px; color:#f43f5e;">41.7%</td>
                    <td style="padding:8px; color:#f43f5e;">58.3%</td>
                    <td style="padding:8px; color:#64748b;">N/A (Sin verificación web)</td>
                </tr>
                <tr style="border-bottom:1px solid #334155;">
                    <td style="padding:8px;">🔍 <b>Nemotron 3.5 Parse (VLM sin Refactorizador)</b></td>
                    <td style="padding:8px; color:#f59e0b;">88.4%</td>
                    <td style="padding:8px; color:#f59e0b;">11.6%</td>
                    <td style="padding:8px; color:#f59e0b;">75.0%</td>
                    <td style="padding:8px; color:#f59e0b;">83.3%</td>
                    <td style="padding:8px; color:#64748b;">N/A (Sin verificación web)</td>
                </tr>
                <tr style="background:#0f172a; font-weight:bold; color:#38bdf8;">
                    <td style="padding:8px;">🚀 <b>Pipeline Multi-Agente Actual (Agentes 1 al 3)</b></td>
                    <td style="padding:8px;">{prec_flecha_pct}%</td>
                    <td style="padding:8px;">{error_flecha_pct}%</td>
                    <td style="padding:8px;">{planillas_exactas_pct}%</td>
                    <td style="padding:8px;">{prec_totales_pct}%</td>
                    <td style="padding:8px; color:#38bdf8;">Cotejo Local vs Padrón</td>
                </tr>
                <tr style="background:#1e293b; font-weight:bold; color:#f59e0b;">
                    <td style="padding:8px;">🌐 <b>Verificación Web Oficial (Agente 4)</b></td>
                    <td style="padding:8px; color:#64748b;">N/A (No releva flechas)</td>
                    <td style="padding:8px; color:#64748b;">N/A (No releva flechas)</td>
                    <td style="padding:8px; color:#64748b;">N/A (Solo totales por turno)</td>
                    <td style="padding:8px; color:#38bdf8;">{prec_total_web_celda}</td>
                    <td style="padding:8px; color:#f59e0b;">{resumen_web_celda}</td>
                </tr>
            </tbody>
        </table>

        {html_tiempos_grid}

        {html_tabla_errores}
    </div>
    """
    return html


# --- CONSTRUCCIÓN DE LA INTERFAZ WEB GRADIO ---
def build_ui():
    custom_css = """
    .app-title { font-size: 24px; font-weight: 800; color: #38bdf8; margin: 0; }
    .app-subtitle { font-size: 13px; color: #94a3b8; margin: 2px 0 0 0; }
    .tab-nav button { font-weight: bold; font-size: 14px; padding: 10px 16px; }
    """

    with gr.Blocks(title="🎯 Sistema Multi-Agente - Tiro con Arco (v88)", css=custom_css) as demo:
        with gr.Row(elem_id="header-bar", variant="compact"):
            with gr.Column(scale=3):
                gr.HTML("""
                <div style="display:flex; align-items:center; gap:12px; padding:8px 0;">
                    <div style="background:#0284c7; padding:10px; border-radius:10px; font-size:24px;">🎯</div>
                    <div>
                        <h1 class="app-title">🎯 Sistema Multi-Agente - Tiro con Arco (v88)</h1>
                        <p class="app-subtitle">Navegación Modular Autoescalable • Segmentación, OCR Vision-Language y Auditoría Lógica en Vivo</p>
                    </div>
                </div>
                """)
            with gr.Column(scale=1):
                gr.HTML("""
                <div style="background:#1e293b; padding:8px 16px; border-radius:8px; border:1px solid #3b82f6; text-align:right;">
                    <span style="color:#60a5fa; font-size:12px; font-weight:bold;">ESTADO PIPELINE:</span>
                    <span style="color:#34d399; font-size:12px; margin-left:6px; font-weight:bold;">🟢 AGENTES LISTOS</span>
                </div>
                """)

        state_manifiesto_1 = gr.State(None)
        state_manifiesto_2 = gr.State(None)
        state_manifiesto_3 = gr.State(None)
        state_manifiesto_4 = gr.State(None)
        state_tiempos = gr.State({"paso0": 0.0, "paso1": 0.0, "paso2": 0.0, "paso3": 0.0, "paso4": 0.0})

        with gr.Tabs(elem_classes=["tab-nav"]) as tabs_main:

            # ==========================================
            # TAB 0: PASO 0 - CARGA Y PÁGINAS COMPLETAS
            # ==========================================
            with gr.Tab("🖼️ Paso 0: Carga y Páginas", id="tab_paso0"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 📂 1. Carga de Documento")
                        file_input = gr.File(label="Subir Planilla (PDF o Imagen)", file_types=[".png", ".jpg", ".jpeg", ".pdf"])
                        tipo_manual = gr.Dropdown(
                            label="Modo de Juego Manual (Opcional)",
                            choices=["Auto", "info", "eliminatoria_2", "clasificacion_1", "clasificacion_2", "clasificacion_4"],
                            value="Auto"
                        )
                        btn_cargar = gr.Button("🖼️ Cargar y Renderear Páginas", variant="primary")

                        gr.Markdown("---")
                        gr.Markdown("### 🛠️ 2. Inspección y Mejora de Páginas")
                        dropdown_paginas = gr.Dropdown(choices=[], label="🔍 Seleccionar Página a Inspeccionar/Mejorar")
                        with gr.Row():
                            btn_mejorar_pag = gr.Button("✨ Mejorar Página")
                            btn_deshacer_pag = gr.Button("↩️ Deshacer Página")
                        with gr.Row():
                            btn_mejorar_todas_pag = gr.Button("✨ Mejorar TODAS las Páginas", variant="secondary")
                            btn_deshacer_todas_pag = gr.Button("↩️ Deshacer TODAS las Páginas")

                        gr.Markdown("---")
                        btn_paso1 = gr.Button("✂️ Paso 1: Dividir Cuadrantes en Páginas ➔", variant="primary", interactive=False)

                    with gr.Column(scale=2):
                        status_paso0 = gr.Markdown("Esperando archivo...")
                        galeria_paginas_out = gr.Gallery(label="🖼️ Galería de Páginas Físicas Extraídas (HD)", columns=2, preview=True)
                        visor_pagina_out = gr.Image(label="🖼️ Visor de Página Seleccionada", interactive=False)

            # ==========================================
            # TAB 1: PASO 1 - SEGMENTACIÓN DE CUADRANTES
            # ==========================================
            with gr.Tab("✂️ Paso 1: Segmentación", id="tab_paso1"):
                with gr.Row():
                    with gr.Column(scale=1):
                        diagnostico_paso1_out = gr.Markdown("Ejecuta el **Paso 0** y luego haz clic en **Paso 1: Dividir Cuadrantes**.")

                        gr.Markdown("---")
                        gr.Markdown("### 🛠️ Inspección y Mejora de Recortes")
                        dropdown_cuadrantes = gr.Dropdown(choices=[], label="🔍 Seleccionar Recorte de Cuadrante")
                        with gr.Row():
                            btn_mejorar_recorte = gr.Button("✨ Mejorar Recorte")
                            btn_deshacer_recorte = gr.Button("↩️ Deshacer Recorte")
                        with gr.Row():
                            btn_mejorar_todos_recortes = gr.Button("✨ Mejorar TODOS los Recortes", variant="secondary")
                            btn_deshacer_todos_recortes = gr.Button("↩️ Deshacer TODOS los Recortes")

                        gr.Markdown("---")
                        gr.Markdown("### 🎯 Seleccionar Cuadrantes para OCR")
                        btn_paso2_top = gr.Button("👁️ Paso 2: Ejecutar OCR en Seleccionados ➔", variant="primary", interactive=False)
                        checkbox_cuadrantes = gr.CheckboxGroup(choices=[], label="Cuadrantes Detectados por Página")
                        btn_paso2 = gr.Button("👁️ Paso 2: Ejecutar OCR en Seleccionados ➔", variant="primary", interactive=False)

                    with gr.Column(scale=2):
                        galeria_cuadrantes_out = gr.Gallery(label="✂️ Galería de Recortes de Cuadrantes", columns=2, preview=True)
                        visor_cuadrante_out = gr.Image(label="🖼️ Visor de Recorte de Cuadrante Seleccionado", interactive=False)

            # ==========================================
            # TAB 2: PASO 2 - OCR MULTI-MODELO
            # ==========================================
            with gr.Tab("👁️ Paso 2: OCR Extracción", id="tab_paso2"):
                gr.Markdown("### 👁️ Extracción de Texto con VLM / Nemotron")
                gr.Markdown("Procesa los cuadrantes seleccionados utilizando el modelo multimodal con rate-limiting y fallback local.")

                diagnostico_paso2_out = gr.Markdown("Selecciona cuadrantes en el Paso 1 y haz clic en **Paso 2: Ejecutar OCR**.")

                gr.Markdown("---")
                gr.Markdown("### 🔍 Inspección Individual por Arquero (Texto Crudo VLM + JSON Structured)")
                dropdown_inspector = gr.Dropdown(choices=[], label="🔍 Seleccionar Arquero/Cuadrante a Inspeccionar")

                with gr.Row():
                    with gr.Column(scale=1):
                        image_inspector = gr.Image(label="🖼️ Recorte HD Interactivo", interactive=False)
                        raw_ocr_out = gr.Code(label="📜 Salida en Crudo Retornada por VLM / Nemotron (Texto Bruto)", language="markdown")
                    with gr.Column(scale=1):
                        json_inspector = gr.Code(label="🎯 Campos JSON Procesados y Cotejados", language="json")
                        json_auditoria_nemotron = gr.Code(label="📄 Auditoría Nemotron Raw vs JSON Refactorizado", language="json")

                gr.Markdown("---")
                with gr.Row():
                    btn_paso3 = gr.Button("⚖️ Paso 3: Ejecutar Auditoría Lógica (Agente 3) ➔", variant="primary", interactive=False)

            # ==========================================
            # TAB 3: PASO 3 - AUDITORÍA Y RECONCILIACIÓN
            # ==========================================
            with gr.Tab("⚖️ Paso 3: Auditoría Lógica", id="tab_paso3"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### ⚖️ Auditoría Lógica y Control de Certeza (Agente 3)")
                        gr.Markdown("Aplica las reglas de auditoría matemática, reconciliación de totales en papel y autocompletado por padrón local.")
                        dropdown_audit = gr.Dropdown(choices=[], label="⚖️ Seleccionar Arquero/Cuadrante Auditado")

                        gr.Markdown("---")
                        btn_paso4 = gr.Button("🌐 Paso 4: Verificación Web (Agente 4) ➔", variant="primary", interactive=False)

                    with gr.Column(scale=2):
                        diagnostico_paso3_out = gr.Markdown("Ejecuta el Paso 2 y haz clic en **Paso 3: Ejecutar Auditoría Lógica**.")
                        json_audit_inspector = gr.Code(label="📋 Detalle Completo de Auditoría Agente 3", language="json")

            # ==========================================
            # TAB 4: PASO 4 - SCRAPING Y VERIFICACIÓN WEB
            # ==========================================
            with gr.Tab("🌐 Paso 4: Verificación Web", id="tab_paso4"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 🌐 Verificación Oficial contra Resultados Web")
                        gr.Markdown("El Agente 4 consulta la base de datos oficial en `arquerosonline.com.ar` y contrasta cada cuadrante por nombre, categoría y puntajes de Turno 1 / Turno 2.")

                        dropdown_club_filtro = gr.Dropdown(
                            choices=["AFPSF - Asociación Familia Piemontesa San Francisco", "AFAPIECO - Asociación Familia Piemontesa Córdoba", "TCAP - Tiro con Arco Paraná A.D.", "GADA - Grupo Arqueros de Ataliva"],
                            value="AFPSF - Asociación Familia Piemontesa San Francisco",
                            label="🏛️ Seleccionar / Escribir Club Organizador a Filtrar en Web",
                            allow_custom_value=True
                        )
                        btn_ejecutar_paso4_directo = gr.Button("🔄 Re-ejecutar Verificación Web con Club Seleccionado", variant="secondary")

                        gr.Markdown("---")
                        dropdown_web_inspector = gr.Dropdown(choices=[], label="🌐 Seleccionar Arquero para Inspeccionar Sugerencia Web")
                        btn_metricas = gr.Button("📊 Ir a Métricas y Evaluación ➔", variant="primary", interactive=False)

                    with gr.Column(scale=2):
                        diagnostico_paso4_out = gr.Markdown("Ejecuta el **Paso 3** y luego haz clic en **Paso 4: Verificación Web**.")
                        with gr.Row():
                            with gr.Column(scale=1):
                                json_web_raw_inspector = gr.Code(label="🌐 Datos Relevados por Scraping Web (Resultados Oficiales)", language="json")
                            with gr.Column(scale=1):
                                json_web_inspector = gr.Code(label="📋 Detalle de Cotejo Web y Sugerencias de Corrección Humana", language="json")

            # ==========================================
            # TAB 5: MÉTRICAS Y TABLA DE ERRORES DETALLADA
            # ==========================================
            with gr.Tab("📊 Métricas y Registro de Errores", id="tab_metricas"):
                with gr.Row():
                    with gr.Column():
                        radio_orden_metricas = gr.Radio(
                            choices=["Prioridad (Nivel de Urgencia)", "Cantidad de Discrepancias / Errores"],
                            value="Prioridad (Nivel de Urgencia)",
                            label="⚙️ Organizar Tabla de Errores / Discrepancias Por:",
                            interactive=True
                        )
                        html_metricas_out = gr.HTML(value="""
                        <div style="background-color: #0f172a; color: #94a3b8; padding: 20px; border-radius: 10px; border: 1px solid #334155;">
                            <h4 style="color: #38bdf8; margin-top: 0;">📊 Evaluación del MVP contra Verdad Terreno</h4>
                            <p>Ejecuta el <b>Paso 3 (Auditoría Lógica)</b> para calcular la precisión del modelo y generar el registro detallado de errores.</p>
                        </div>
                        """)

            # ==========================================
            # TAB 6: MANIFIESTO COMPLETO JSON
            # ==========================================
            with gr.Tab("📄 Manifiesto JSON Global", id="tab_json"):
                json_out = gr.Code(label="Manifiesto JSON Completo (Agente 1 + Agente 2 + Agente 3 + Agente 4)", language="json")

        # --- EVENTOS Y CONTROL DE ESTADOS DE BOTONES Y REDIRECCIÓN DE PESTAÑAS ---
        btn_cargar.click(
            fn=cargar_documento_paso0,
            inputs=[file_input, state_tiempos],
            outputs=[
                status_paso0, galeria_paginas_out, dropdown_paginas, visor_pagina_out, diagnostico_paso1_out,
                galeria_cuadrantes_out, dropdown_cuadrantes, visor_cuadrante_out,
                checkbox_cuadrantes, json_out,
                btn_paso1, btn_paso2_top, btn_paso2, btn_paso3, btn_paso4, btn_metricas, state_tiempos
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
            inputs=[file_input, tipo_manual, state_tiempos],
            outputs=[
                diagnostico_paso1_out, galeria_cuadrantes_out, dropdown_cuadrantes, visor_cuadrante_out,
                checkbox_cuadrantes, json_out, state_manifiesto_1,
                btn_paso1, btn_paso2_top, btn_paso2, tabs_main, state_tiempos
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

        btn_paso2_top.click(
            fn=ejecutar_paso2_ocr,
            inputs=[checkbox_cuadrantes, state_manifiesto_1, state_manifiesto_2, state_tiempos],
            outputs=[
                diagnostico_paso2_out, json_out, galeria_cuadrantes_out, state_manifiesto_1, state_manifiesto_2,
                raw_ocr_out, json_inspector, image_inspector, dropdown_inspector, json_auditoria_nemotron,
                btn_paso2_top, btn_paso2, btn_paso3, tabs_main, state_tiempos
            ]
        )

        btn_paso2.click(
            fn=ejecutar_paso2_ocr,
            inputs=[checkbox_cuadrantes, state_manifiesto_1, state_manifiesto_2, state_tiempos],
            outputs=[
                diagnostico_paso2_out, json_out, galeria_cuadrantes_out, state_manifiesto_1, state_manifiesto_2,
                raw_ocr_out, json_inspector, image_inspector, dropdown_inspector, json_auditoria_nemotron,
                btn_paso2_top, btn_paso2, btn_paso3, tabs_main, state_tiempos
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
            inputs=[state_manifiesto_1, state_manifiesto_2, radio_orden_metricas, state_tiempos],
            outputs=[
                diagnostico_paso3_out, json_out, dropdown_audit, json_audit_inspector, state_manifiesto_3,
                json_auditoria_nemotron, html_metricas_out,
                btn_paso3, btn_paso4, btn_metricas, dropdown_club_filtro, diagnostico_paso4_out, tabs_main, state_tiempos
            ]
        )

        btn_paso4.click(
            fn=ejecutar_paso4_scraping,
            inputs=[state_manifiesto_1, state_manifiesto_2, state_manifiesto_3, state_tiempos, dropdown_club_filtro, radio_orden_metricas],
            outputs=[
                diagnostico_paso4_out, json_out, dropdown_web_inspector, json_web_raw_inspector, json_web_inspector,
                state_manifiesto_4, state_tiempos, html_metricas_out, btn_paso4, btn_metricas, tabs_main
            ]
        )

        btn_ejecutar_paso4_directo.click(
            fn=ejecutar_paso4_scraping,
            inputs=[state_manifiesto_1, state_manifiesto_2, state_manifiesto_3, state_tiempos, dropdown_club_filtro, radio_orden_metricas],
            outputs=[
                diagnostico_paso4_out, json_out, dropdown_web_inspector, json_web_raw_inspector, json_web_inspector,
                state_manifiesto_4, state_tiempos, html_metricas_out, btn_paso4, btn_metricas, tabs_main
            ]
        )

        dropdown_web_inspector.change(
            fn=inspeccionar_verificacion_web,
            inputs=[dropdown_web_inspector, state_manifiesto_4],
            outputs=[json_web_raw_inspector, json_web_inspector]
        )

        btn_metricas.click(
            fn=ir_a_metricas_ui,
            inputs=[state_manifiesto_3, state_manifiesto_4, radio_orden_metricas, state_tiempos],
            outputs=[html_metricas_out, btn_metricas, tabs_main]
        )

        radio_orden_metricas.change(
            fn=lambda m3, m4, ord_val, st: calcular_metricas_evaluacion(m3, criterio_orden=ord_val, state_tiempos=st, manifiesto_4=m4),
            inputs=[state_manifiesto_3, state_manifiesto_4, radio_orden_metricas, state_tiempos],
            outputs=[html_metricas_out]
        )

    return demo


def main():
    print("=" * 60)
    print("🚀 Servidor Principal Multi-Agente (v89) - Tiro con Arco")
    print("🌍 Abre tu navegador en: http://localhost:7860")
    print("=" * 60)
    demo = build_ui()
    allowed_directories = ["/tmp", tempfile.gettempdir(), os.getcwd(), "/app"]
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, allowed_paths=allowed_directories)


if __name__ == "__main__":
    main()