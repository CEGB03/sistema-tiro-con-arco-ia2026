#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agente 1: Clasificador y Segmentador de Planillas de Tiro con Arco.

Responsabilidades:
1. Procesar archivos de entrada (PDF multipágina o Imagen).
2. Renderizar páginas de PDF a imágenes ordenadas usando pypdfium2.
3. Clasificar el tipo de juego ('clasificacion', 'eliminatoria', 'sin_modo') y el layout ('4_arqueros', '2_arqueros', '1_arquero', 'portada').
4. Utilizar identificadores POSICIONALES dinámicos (NO hardcodear "1A", "1B", "1C", "1D", ya que el número de contención varía: ej. 5A, 12C, etc. y en eliminatorias es por Puesto/Posición).
5. Aplicar solapes verticales adecuados (empezando en y=0.38*h para cuadrantes inferiores) de modo que el encabezado con datos del arquero NUNCA quede cortado.
6. Emitir un manifiesto JSON estructurado con las tareas ordenadas para el Agente 2 (OCR / Visión).
"""

import os
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


class AgenteClasificadorSegmentador:
    def __init__(self, output_dir=None):
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="archery_agent1_")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

    def analizar_layout(self, ruta_imagen, original_filename=None, tipo_juego_manual=None):
        """
        Analiza la geometría, el nombre original y las líneas del documento para clasificar:
        - tipo_juego: 'clasificacion', 'eliminatoria' o 'sin_modo'
        - layout: '4_arqueros', '2_arqueros', '1_arquero' o 'portada'
        - posiciones_activas: lista de identificadores posicionales (ej. ['Pos_A', 'Pos_B', 'Pos_C', 'Pos_D'] o ['Puesto_1', 'Puesto_2'] o ['Individual'])
        """
        pil_img = Image.open(ruta_imagen)
        img_np = np.array(pil_img.convert('RGB'))
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        filename = (original_filename or os.path.basename(ruta_imagen)).lower()

        # 1. Anulación manual explícita
        if tipo_juego_manual in ["clasificacion", "eliminatoria"]:
            tipo_juego = tipo_juego_manual
            if tipo_juego == "eliminatoria":
                layout = "2_arqueros"
                posiciones = ["Puesto_1", "Puesto_2"]
            else:
                layout = "4_arqueros"
                posiciones = ["Pos_A", "Pos_B", "Pos_C", "Pos_D"]
            return tipo_juego, layout, posiciones

        # 2. Análisis de nombres de archivo específicos
        if "eliminacion" in filename or "duelo" in filename or "2-arqueros" in filename or "enfrentamiento" in filename:
            return "eliminatoria", "2_arqueros", ["Puesto_1", "Puesto_2"]

        # Si el nombre indica una tarjeta individual recortada (ej: 1A-, 1B-, crop_, individual)
        if any(pat in filename for pat in ["crop_", "individual", "1a-", "1b-", "1c-", "1d-", "2a-", "3a-"]):
            return "clasificacion", "1_arquero", ["Individual"]

        # 3. Análisis por Visión de Computadora (Morphology de líneas y proyección central)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        # Detectar líneas horizontales de tablas
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w // 20), 1))
        lines_h = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_h)

        top_density = np.mean(lines_h[0:int(h * 0.35), :])
        bot_density = np.mean(lines_h[int(h * 0.45):int(h * 0.90), :])

        # Verificar presencia de división vertical central (columna divisoria en x = w//2)
        center_strip = thresh[:, int(w * 0.45):int(w * 0.55)]
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, h // 20)))
        lines_v = cv2.morphologyEx(center_strip, cv2.MORPH_OPEN, kernel_v)
        center_v_density = np.mean(lines_v)

        has_tables = (top_density > 0.02 or bot_density > 0.02)

        if not has_tables:
            # Es una portada, carátula o hoja de título
            return "sin_modo", "portada", ["Portada"]

        if center_v_density > 0.5 and top_density > 0.02 and bot_density > 0.02:
            # Grilla 2x2 completa con columna divisoria central -> 4 arqueros por página
            return "clasificacion", "4_arqueros", ["Pos_A", "Pos_B", "Pos_C", "Pos_D"]
        elif top_density > 0.02 and bot_density > 0.02 and center_v_density <= 0.5:
            # Planilla individual con tablas largas que ocupan todo el alto
            return "clasificacion", "1_arquero", ["Individual"]
        else:
            # Por defecto si no hay columna divisoria
            return "clasificacion", "1_arquero", ["Individual"]

    def procesar_documento(self, ruta_archivo, tipo_juego_manual=None):
        """
        Procesa el archivo de entrada (PDF o Imagen) y retorna un
        manifiesto JSON con las imágenes recortadas listas para el Agente 2.
        """
        if not os.path.exists(ruta_archivo):
            raise FileNotFoundError(f"El archivo '{ruta_archivo}' no existe.")

        original_filename = os.path.basename(ruta_archivo)
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
            "archivo_origen": original_filename,
            "total_paginas": len(paginas_imagenes),
            "tareas_agente2": []
        }

        for num_pag, img_path in paginas_imagenes:
            tipo_juego, layout, posiciones_activas = self.analizar_layout(
                img_path,
                original_filename=original_filename,
                tipo_juego_manual=tipo_juego_manual
            )

            img = Image.open(img_path)
            w, h = img.size

            # Definición de coordenadas con SOLAPE ESTRUCTURAL para evitar cortes
            if layout == "4_arqueros":
                # Arriba: 0 a 53% del alto. Abajo: 38% a 100% del alto (Solape del 15% para incluir todo el encabezado de C y D)
                cuadrantes_coords = {
                    "Pos_A": (0, 0, w // 2, int(h * 0.53)),
                    "Pos_B": (w // 2, 0, w, int(h * 0.53)),
                    "Pos_C": (0, int(h * 0.38), w // 2, h),
                    "Pos_D": (w // 2, int(h * 0.38), w, h)
                }
            elif layout == "2_arqueros":
                # Eliminatorias: Dividido verticalmente por puestos (Puesto 1 / Puesto 2)
                cuadrantes_coords = {
                    "Puesto_1": (0, 0, w // 2, h),
                    "Puesto_2": (w // 2, 0, w, h)
                }
            elif layout == "1_arquero":
                # Planilla Individual: 100% de la imagen, sin recortar NADA
                cuadrantes_coords = {"Individual": (0, 0, w, h)}
            else:
                # Portada / Carátula
                cuadrantes_coords = {"Portada": (0, 0, w, h)}

            for pos_id in posiciones_activas:
                coords = cuadrantes_coords[pos_id]
                crop_img = img.crop(coords)
                crop_filename = f"pag_{num_pag}_crop_{pos_id}.png"
                crop_path = os.path.join(self.output_dir, crop_filename)
                crop_img.save(crop_path, "PNG")

                manifiesto["tareas_agente2"].append({
                    "pagina": num_pag,
                    "posicion_slot": pos_id,
                    "tipo_juego": tipo_juego,
                    "layout": layout,
                    "ruta_recorte": crop_path
                })

        return manifiesto
