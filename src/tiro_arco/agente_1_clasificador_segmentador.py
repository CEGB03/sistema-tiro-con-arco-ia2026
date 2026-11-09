#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agente 1 v13: Con Padding de margen (20px) para evitar recortar los bordes exteriores de las tablas.
"""

import os
import re
import json
import tempfile
from PIL import Image
import numpy as np
import cv2

try:
    import pypdfium2 as pdfium
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False


def extract_target_from_filename(filename):
    m = re.search(r'(?:^|[^0-9a-zA-Z])([0-9]{1,2}[A-Da-d])(?:$|[^0-9a-zA-Z])', filename)
    if m:
        return m.group(1).upper()
    return None


class AgenteClasificadorSegmentador:
    def __init__(self, output_dir=None):
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="archery_agent1_")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

    def analizar_layout(self, ruta_imagen, tipo_juego_manual=None):
        filename = os.path.basename(ruta_imagen).lower()

        if tipo_juego_manual and tipo_juego_manual != "Auto":
            m = str(tipo_juego_manual).lower()
            if "info" in m or "portada" in m:
                return "info", "portada"
            elif "eliminatoria" in m or "duelo" in m or "2" in m:
                return "eliminatoria", "2_arqueros"
            elif "clasificacion_1" in m or "1_arquero" in m or "individual" in m:
                return "clasificacion", "1_arquero"
            elif "clasificacion_2" in m:
                return "clasificacion", "2_arqueros"
            elif "clasificacion_4" in m or "4_arqueros" in m:
                return "clasificacion", "4_arqueros"

        keywords_eliminatoria = ["puesto", "s.o.", "so", "ganador", "duelo", "eliminac"]
        if any(kw in filename for kw in keywords_eliminatoria):
            return "eliminatoria", "2_arqueros"

        if any(p in filename for p in ["4-arqueros", "4arqueros"]):
            return "clasificacion", "4_arqueros"

        pattern_1_arquero = r'^(?:[0-9]{1,2}[a-d])[\_\-]|(?:crop|recorte|individual|1[-_]arquero|1arquero)'
        if re.search(pattern_1_arquero, filename):
            return "clasificacion", "1_arquero"

        pil_img = Image.open(ruta_imagen)
        w, h = pil_img.size

        if w < 750 and h < 850:
            return "clasificacion", "1_arquero"

        if w > h * 1.2:
            return "clasificacion", "2_arqueros"

        return "clasificacion", "4_arqueros"

    def procesar_documento(self, ruta_archivo, tipo_juego_manual=None, page_overrides=None):
        if not os.path.exists(ruta_archivo):
            raise FileNotFoundError(f"El archivo '{ruta_archivo}' no existe.")

        es_pdf = ruta_archivo.lower().endswith('.pdf')
        paginas_imagenes = []

        if es_pdf:
            if not PDF_SUPPORT:
                raise ImportError("Se requiere 'pypdfium2' para procesar archivos PDF.")
            doc = pdfium.PdfDocument(ruta_archivo)
            for i, page in enumerate(doc):
                bitmap = page.render(scale=2)
                pil_img = bitmap.to_pil()
                img_path = os.path.join(self.output_dir, f"pagina_{i+1}.png")
                pil_img.save(img_path)
                paginas_imagenes.append((i + 1, img_path))
        else:
            paginas_imagenes.append((1, ruta_archivo))

        manifiesto = {
            "archivo_origen": os.path.basename(ruta_archivo),
            "total_paginas": len(paginas_imagenes),
            "tareas_agente2": []
        }

        fn_global = os.path.basename(ruta_archivo)
        target_desde_nombre = extract_target_from_filename(fn_global)

        # Margin/Padding para evitar recortar los bordes de la grilla
        margin = 20

        for num_pag, img_path in paginas_imagenes:
            modo_manual = tipo_juego_manual
            if page_overrides and isinstance(page_overrides, dict):
                modo_manual = page_overrides.get(str(num_pag), modo_manual)

            tipo_juego, layout = self.analizar_layout(img_path, tipo_juego_manual=modo_manual)
            img = Image.open(img_path)
            w, h = img.size

            if layout == "portada" or tipo_juego == "info":
                cuadrantes_coords = {"Portada": (0, 0, w, h)}
            elif layout == "4_arqueros":
                cuadrantes_coords = {
                    "A": (0, 0, min(w, w // 2 + margin), min(h, h // 2 + margin)),
                    "B": (max(0, w // 2 - margin), 0, w, min(h, h // 2 + margin)),
                    "C": (0, max(0, h // 2 - margin), min(w, w // 2 + margin), h),
                    "D": (max(0, w // 2 - margin), max(0, h // 2 - margin), w, h)
                }
            elif layout == "2_arqueros":
                cuadrantes_coords = {
                    "A": (0, 0, min(w, w // 2 + margin), h),
                    "B": (max(0, w // 2 - margin), 0, w, h)
                }
            else:
                tid = target_desde_nombre if target_desde_nombre else "1A"
                cuadrantes_coords = {tid: (0, 0, w, h)}

            for target_pos, coords in cuadrantes_coords.items():
                crop_img = img.crop(coords)
                crop_filename = f"pag_{num_pag}_pos_{target_pos}.png"
                crop_path = os.path.join(self.output_dir, crop_filename)
                crop_img.save(crop_path, "PNG")

                label_str = f"Pág {num_pag} - Pos {target_pos}"
                manifiesto["tareas_agente2"].append({
                    "pagina": num_pag,
                    "target_id": target_pos,
                    "tipo_juego": tipo_juego,
                    "layout": layout,
                    "ruta_recorte": crop_path,
                    "label": label_str
                })

        print(f"[Agente 1] ✂️ Completada la clasificación y segmentación de {len(paginas_imagenes)} página(s) con padding de {margin}px.")
        return manifiesto
