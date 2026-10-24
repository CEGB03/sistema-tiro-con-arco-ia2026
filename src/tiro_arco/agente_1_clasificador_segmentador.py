#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 Agente 1: Clasificador y Segmentador Semántico y Geométrico Híbrido (Tiro con Arco).

Responsabilidades:
1. Procesar archivos de entrada (PDF multipágina o Imagen PNG/JPG/JPEG).
2. Renderizar páginas de PDF a imágenes ordenadas usando pypdfium2.
3. Extraer texto vectorial del PDF y texto OCR con pytesseract.
4. Inspeccionar la presencia de grillas físicas mediante morfología OpenCV (líneas de tabla).
5. Clasificar el tipo de juego ('clasificacion', 'eliminatoria' o 'sin_modo') y layout ('4_arqueros', '2_arqueros', '1_arquero', 'portada').
6. Generar los recortes físicos con solape inteligente en disco.
7. Emitir un manifiesto JSON estructurado con la cola de trabajo para el Agente 2.
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

try:
    import pytesseract
    OCR_SUPPORT = True
except ImportError:
    OCR_SUPPORT = False


class AgenteClasificadorSegmentador:
    def __init__(self, output_dir=None):
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="archery_agent1_")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

    def extraer_texto_completo(self, ruta_imagen, pdf_page=None):
        """
        Extrae tanto texto vectorial (si proviene de PDF) como texto OCR (pytesseract).
        """
        texto_vectorial = ""
        texto_ocr = ""

        if pdf_page is not None:
            try:
                textpage = pdf_page.get_textpage()
                texto_vectorial = textpage.get_text_range() or ""
            except Exception:
                texto_vectorial = ""

        if OCR_SUPPORT and os.path.exists(ruta_imagen):
            try:
                img_pil = Image.open(ruta_imagen)
                texto_ocr = pytesseract.image_to_string(img_pil, lang="spa+eng")
            except Exception:
                try:
                    img_pil = Image.open(ruta_imagen)
                    texto_ocr = pytesseract.image_to_string(img_pil)
                except Exception:
                    texto_ocr = ""

        return (texto_vectorial + " " + texto_ocr).lower()

    def analizar_layout(self, ruta_imagen, pdf_page=None, tipo_juego_manual=None):
        """
        Analiza el documento mediante un enfoque híbrido (Texto semántico + Visión OpenCV):
        - tipo_juego: 'clasificacion', 'eliminatoria' o 'sin_modo'
        - layout: '4_arqueros', '2_arqueros', '1_arquero' o 'portada'
        - activos: slots posicionales ['Pos_A'..'Pos_D'] | ['Puesto_1', 'Puesto_2'] | ['Individual'] | ['Portada']
        """
        filename = os.path.basename(ruta_imagen).lower()

        # 1. Override manual si el usuario lo especificó
        if tipo_juego_manual in ["clasificacion", "eliminatoria"]:
            if tipo_juego_manual == "eliminatoria":
                return "eliminatoria", "2_arqueros", ["Puesto_1", "Puesto_2"]
            else:
                return "clasificacion", "4_arqueros", ["Pos_A", "Pos_B", "Pos_C", "Pos_D"]

        # 2. Abrir imagen y calcular aspecto
        img = Image.open(ruta_imagen)
        w, h = img.size
        aspect = w / h

        # 3. Extraer texto semántico combinando PDF vectorial + OCR
        texto = self.extraer_texto_completo(ruta_imagen, pdf_page=pdf_page)

        # 4. Análisis por Visión de Computadora (Morfología de líneas de tabla)
        img_np = np.array(img.convert('RGB'))
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w // 20), 1))
        lines_h = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_h)

        top_h_density = float(np.mean(lines_h[0:int(h * 0.45), :]))
        bot_h_density = float(np.mean(lines_h[int(h * 0.45):int(h * 0.95), :]))
        total_h_density = float(np.mean(lines_h))

        # 5. Detección de Eliminatorias
        kw_eliminatoria = ["total set points", "set points", "ganador", "s.o.", "shoot off", "shoot-off", "contencion", "duelo"]
        has_elim_kw = any(kw in texto for kw in kw_eliminatoria)
        has_posicion_num = bool(re.search(r'posici[oó]n\s*\d+', texto))
        is_filename_elim = any(k in filename for k in ["eliminacion", "duelo", "2-arqueros", "2_arqueros"])
        is_landscape_duel = (aspect > 1.25) and (total_h_density > 1.0)

        if has_elim_kw or has_posicion_num or is_filename_elim or is_landscape_duel:
            return "eliminatoria", "2_arqueros", ["Puesto_1", "Puesto_2"]

        # 6. Detección de Clasificación vs Portada/Info
        has_scorecard_text = any(k in texto for k in ["10s", "9s", "series", "tot.", "sum", "ronda #", "hoja de anotac", "arquero", "atleta"])
        dianas_found = set(re.findall(r'\b\d+[a-d]\b', texto))
        is_filename_1archer = any(k in filename for k in ["1a-", "1b-", "1c-", "1d-", "individual"])
        is_filename_4archers = any(k in filename for k in ["4-arqueros", "4_arqueros"])

        has_table_grid = (top_h_density > 1.2 or bot_h_density > 1.2 or has_scorecard_text or len(dianas_found) > 0)

        if not has_table_grid:
            return "sin_modo", "portada", ["Portada"]

        # 7. Discriminar entre 4 Arqueros y 1 Arquero
        if is_filename_1archer:
            return "clasificacion", "1_arquero", ["Individual"]

        if is_filename_4archers or (top_h_density > 1.2 and bot_h_density > 1.2) or len(dianas_found) >= 3:
            return "clasificacion", "4_arqueros", ["Pos_A", "Pos_B", "Pos_C", "Pos_D"]
        else:
            return "clasificacion", "1_arquero", ["Individual"]

    def procesar_documento(self, ruta_archivo, tipo_juego_manual=None):
        """
        Procesa el archivo de entrada (PDF o Imagen) y retorna un
        manifiesto JSON con las imágenes recortadas listas para el Agente 2.
        """
        if not os.path.exists(ruta_archivo):
            raise FileNotFoundError(f"El archivo '{ruta_archivo}' no existe.")

        es_pdf = ruta_archivo.lower().endswith('.pdf')
        paginas_datos = []

        if es_pdf:
            if not PDF_SUPPORT:
                raise ImportError("Se requiere 'pypdfium2' para procesar archivos PDF.")
            doc = pdfium.PdfDocument(ruta_archivo)
            for i, page in enumerate(doc):
                bitmap = page.render(scale=2)
                pil_img = bitmap.to_pil()
                img_path = os.path.join(self.output_dir, f"pagina_{i+1}.png")
                pil_img.save(img_path)
                paginas_datos.append((i + 1, img_path, page))
        else:
            paginas_datos.append((1, ruta_archivo, None))

        manifiesto = {
            "archivo_origen": os.path.basename(ruta_archivo),
            "total_paginas": len(paginas_datos),
            "tareas_agente2": []
        }

        for num_pag, img_path, pdf_page in paginas_datos:
            tipo_juego, layout, activos = self.analizar_layout(
                img_path, pdf_page=pdf_page, tipo_juego_manual=tipo_juego_manual
            )
            img = Image.open(img_path)
            w, h = img.size

            # Coordenadas de recortes por layout
            if layout == "4_arqueros":
                cuadrantes_coords = {
                    "Pos_A": (0, 0, w // 2, h // 2),
                    "Pos_B": (w // 2, 0, w, h // 2),
                    "Pos_C": (0, int(h * 0.38), w // 2, h),
                    "Pos_D": (int(w * 0.48), int(h * 0.38), w, h)
                }
            elif layout == "2_arqueros":
                cuadrantes_coords = {
                    "Puesto_1": (0, 0, int(w * 0.52), h),
                    "Puesto_2": (int(w * 0.48), 0, w, h)
                }
            else:
                cuadrantes_coords = {
                    "Individual" if layout == "1_arquero" else "Portada": (0, 0, w, h)
                }

            for target_id in activos:
                coords = cuadrantes_coords.get(target_id, (0, 0, w, h))
                crop_img = img.crop(coords)
                crop_filename = f"pag_{num_pag}_crop_{target_id}.png"
                crop_path = os.path.join(self.output_dir, crop_filename)
                crop_img.save(crop_path, "PNG")

                manifiesto["tareas_agente2"].append({
                    "pagina": num_pag,
                    "target_id": target_id,
                    "tipo_juego": tipo_juego,
                    "layout": layout,
                    "ruta_recorte": crop_path
                })

        return manifiesto
