#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orquestador Web - Agente 1 con corrección manual por página.
"""

import os
import json
import gradio as gr
import pandas as pd

from .agente_1_clasificador_segmentador import AgenteClasificadorSegmentador

agente_1 = AgenteClasificadorSegmentador()

# Mapping string de UI → tipo_manual del agente
OVERRIDE_MAP = {
    "info": "info",
    "eliminatoria — 2 arqueros": "eliminatoria_2",
    "clasificación — 1 arquero": "clasificacion_1",
    "clasificación — 2 arqueros (lado a lado)": "clasificacion_2_lado",
    "clasificación — 2 arqueros (arriba/abajo)": "clasificacion_2_arriba",
    "clasificación — 4 arqueros": "clasificacion_4",
}

# Opciones que el usuario puede escribir en la columna Override
OVERRIDE_CHOICES = list(OVERRIDE_MAP.keys())


def tipo_global_map(val):
    if "Automático" in val:
        return None
    if "Información" in val:
        return "info"
    if "Eliminatoria" in val:
        return "eliminatoria_2"
    if "Clasificación — 1" in val:
        return "clasificacion_1"
    if "Clasificación — 2" in val and "lado" in val:
        return "clasificacion_2_lado"
    if "Clasificación — 2" in val and "arriba" in val:
        return "clasificacion_2_arriba"
    if "Clasificación — 4" in val:
        return "clasificacion_4"
    return None


def _formatear_resumen(manifiesto):
    r = "### 📊 Diagnóstico del Agente 1\n\n"
    r += f"- **Archivo:** `{manifiesto['archivo_origen']}`\n"
    r += f"- **Páginas:** `{manifiesto['total_paginas']}`\n"
    r += f"- **Recortes:** `{len(manifiesto['tareas_agente2'])}`\n"
    r += f"- **Entrada mixta:** `{'Sí' if manifiesto['entrada_mixta'] else 'No'}`\n\n"
    r += "#### 📄 Detalle por página\n\n"
    for p in manifiesto["tipos_pagina"]:
        r += (f"- **Pág. {p['numero']}:** `{p['tipo']}/{p['layout']}` "
              f"({p['metodo_deteccion']})\n")
    return r


def _formatear_galeria(manifiesto):
    gal = []
    for t in manifiesto["tareas_agente2"]:
        p = t["ruta_recorte"]
        if os.path.exists(p):
            label = f"Pág {t['pagina']} - {t['posicion_slot']} ({t['tipo_juego']})"
            gal.append((p, label))
    return gal


def _tabla_paginas(manifiesto):
    """Construye la tabla editable con 3 columnas."""
    rows = []
    for p in manifiesto["tipos_pagina"]:
        # Etiqueta legible del layout detectado
        etiqueta_detectada = {
            "portada": "info",
            "eliminatoria_2": "eliminatoria — 2 arqueros",
            "1_arquero": "clasificación — 1 arquero",
            "2_arqueros_lado_a_lado": "clasificación — 2 arqueros (lado a lado)",
            "2_arqueros_arriba_abajo": "clasificación — 2 arqueros (arriba/abajo)",
            "4_arqueros": "clasificación — 4 arqueros",
        }.get(p["layout"], "clasificación — 1 arquero")
        # La columna Override arranca igual a lo detectado
        rows.append([p["numero"], etiqueta_detectada, etiqueta_detectada])
    return pd.DataFrame(rows, columns=["Página", "Detectado", "Override"])


def procesar_inicial(file_obj, tipo_global, state):
    if file_obj is None:
        return ("⚠️ Subí un archivo para empezar.", [], "{}", gr.update(), state or {})

    state = state or {}
    state["file_path"] = file_obj.name
    state["tipo_global_str"] = tipo_global
    tipo_manual = tipo_global_map(tipo_global)
    state["tipo_global_manual"] = tipo_manual

    try:
        manifiesto = agente_1.procesar_documento(
            file_obj.name, tipo_juego_manual=tipo_manual
        )
        state["manifiesto"] = manifiesto

        return (
            _formatear_resumen(manifiesto),                         # status_box
            _formatear_galeria(manifiesto),                         # gallery_out
            json.dumps(manifiesto, indent=2, ensure_ascii=False),   # json_out
            _tabla_paginas(manifiesto),                             # df_paginas
            state,                                                  # state
        )
    except Exception as e:
        return (f"❌ Error: {e}", [], "{}", gr.update(), state)


def regenerar_con_overrides(state, df_paginas, tipo_global):
    if not state or "file_path" not in state:
        return ("⚠️ Primero procesá un archivo.", [], "{}", gr.update(), state)

    if df_paginas is None or len(df_paginas) == 0:
        return ("⚠️ No hay páginas para regenerar.", [], "{}", gr.update(), state)

    page_overrides = {}
    for _, row in df_paginas.iterrows():
        try:
            num = int(row["Página"])
        except (ValueError, TypeError):
            continue
        override_txt = str(row["Override"]).strip()
        mapped = OVERRIDE_MAP.get(override_txt)
        if mapped:
            page_overrides[num] = mapped

    tipo_manual_global = tipo_global_map(tipo_global) if tipo_global else None

    try:
        manifiesto = agente_1.procesar_documento(
            state["file_path"],
            tipo_juego_manual=tipo_manual_global,
            page_overrides=page_overrides,
        )
        state["manifiesto"] = manifiesto

        return (
            _formatear_resumen(manifiesto),
            _formatear_galeria(manifiesto),
            json.dumps(manifiesto, indent=2, ensure_ascii=False),
            _tabla_paginas(manifiesto),
            state,
        )
    except Exception as e:
        return (f"❌ Error al regenerar: {e}", [], "{}", gr.update(), state)


def build_ui():
    with gr.Blocks(title="🎯 Orquestador Multi-Agente - Tiro con Arco") as demo:
        state = gr.State(value={})

        gr.Markdown("# 🎯 Sistema Multi-Agente - Tiro con Arco")
        gr.Markdown(
            "Subí un PDF o imagen. Si la detección falla en alguna página, "
            "corregila en la tabla y volvé a generar."
        )

        with gr.Row():
            with gr.Column(scale=1):
                file_input = gr.File(
                    label="Subir planilla (PDF o imagen)",
                    file_types=[".pdf", ".png", ".jpg", ".jpeg"],
                )
                tipo_global = gr.Dropdown(
                    label="Modo global (opcional)",
                    choices=[
                        "Automático (detectar por página)",
                        "Clasificación — 1 Arquero",
                        "Clasificación — 2 Arqueros (lado a lado)",
                        "Clasificación — 2 Arqueros (arriba/abajo)",
                        "Clasificación — 4 Arqueros",
                        "Eliminatoria — 2 Arqueros",
                        "Página de Información / Portada",
                    ],
                    value="Automático (detectar por página)",
                )
                btn_procesar = gr.Button("🚀 Procesar archivo", variant="primary")

            with gr.Column(scale=2):
                status_box = gr.Markdown("Esperando archivo...")
                gallery_out = gr.Gallery(
                    label="✂️ Recortes generados", columns=2, height=400
                )
                json_out = gr.Code(
                    label="📄 Manifiesto JSON", language="json"
                )

        gr.Markdown("---")
        gr.Markdown("### ✏️ Corrección por página")
        gr.Markdown(
            "Valores válidos para la columna **Override**:\n\n"
            "- `info`\n"
            "- `eliminatoria — 2 arqueros`\n"
            "- `clasificación — 1 arquero`\n"
            "- `clasificación — 2 arqueros (lado a lado)`\n"
            "- `clasificación — 2 arqueros (arriba/abajo)`\n"
            "- `clasificación — 4 arqueros`"
        )

        df_paginas = gr.Dataframe(
            headers=["Página", "Detectado", "Override"],
            datatype=["number", "str", "str"],
            interactive=True,
            wrap=True,
            label="Tabla de páginas (editá la columna Override)",
        )
        btn_regenerar = gr.Button(
            "🔄 Aplicar correcciones y regenerar", variant="secondary"
        )

        # Eventos: 5 outputs, 5 valores de retorno
        btn_procesar.click(
            fn=procesar_inicial,
            inputs=[file_input, tipo_global, state],
            outputs=[status_box, gallery_out, json_out, df_paginas, state],
        )
        btn_regenerar.click(
            fn=regenerar_con_overrides,
            inputs=[state, df_paginas, tipo_global],
            outputs=[status_box, gallery_out, json_out, df_paginas, state],
        )

    return demo


def main():
    print("=" * 60)
    print("🚀 Sistema Multi-Agente - Tiro con Arco")
    print("🌍 http://localhost:7860")
    print("=" * 60)
    demo = build_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)


if __name__ == "__main__":
    main()