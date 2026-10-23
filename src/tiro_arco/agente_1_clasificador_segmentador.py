#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agente 1: Clasificador y Segmentador de Planillas de Tiro con Arco.

Soporta:
- Clasificatoria: 1, 2 (lado a lado o arriba/abajo) o 4 arqueros.
- Eliminatoria:   2 arqueros (lado a lado).
- Hoja de información / portada / carátula: página completa marcada como "info".
- Entrada PDF multipágina con páginas de tipos MIXTOS.

Detección (de más fiable a menos):
1. Override manual (viene de la UI).
2. Nombre de archivo.
3. Análisis visual con OpenCV:
   - Conteo de líneas horizontales/verticales.
   - Densidad de tinta.
   - Conteo de filas dentro de una celda → distingue clasificación (10) de eliminatoria (5).
"""

import os
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
        os.makedirs(self.output_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    # UTILIDADES DE ANÁLISIS
    # ------------------------------------------------------------------ #
    @staticmethod
    def _contar_picos(proyeccion_1d, umbral):
        """
        Cuenta "picos" en una proyección 1D agrupando valores contiguos
        que superan el umbral. Un pico = una línea detectada.
        """
        en_pico = (proyeccion_1d > umbral).astype(int)
        if en_pico.sum() == 0:
            return 0
        cambios = np.diff(en_pico)
        n_inicios = int(np.sum(cambios == 1))
        if en_pico[0] == 1:
            n_inicios += 1
        return n_inicios

    def _analizar_estructura(self, img_np):
        """
        Analiza la estructura de la página con conteos de líneas y densidad.

        Returns dict con:
            n_h, n_v: cantidad de líneas horizontales/verticales largas
            densidad: fracción de tinta en el cuerpo (0-1)
            lines_h, lines_v: máscaras de líneas (para cortes)
            x_div, y_div: coordenadas de las divisorias (si existen)
        """
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        # Líneas horizontales largas (≥30% del ancho)
        kernel_h = cv2.getStructuringElement(
            cv2.MORPH_RECT, (max(20, int(w * 0.30)), 1)
        )
        lines_h = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_h)

        # Líneas verticales largas (≥20% del alto)
        kernel_v = cv2.getStructuringElement(
            cv2.MORPH_RECT, (1, max(20, int(h * 0.20)))
        )
        lines_v = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_v)

        row_sums_h = np.sum(lines_h, axis=1).astype(float)
        col_sums_v = np.sum(lines_v, axis=0).astype(float)

        n_h = self._contar_picos(row_sums_h, w * 0.20)
        n_v = self._contar_picos(col_sums_v, h * 0.15)

        # Densidad de tinta en el cuerpo (sin márgenes)
        cuerpo = thresh[int(h * 0.10):int(h * 0.90), int(w * 0.05):int(w * 0.95)]
        densidad = float(np.mean(cuerpo)) / 255.0

        # Coordenadas de divisorias (para corte posterior)
        x_div = None
        z_ini, z_fin = int(w * 0.30), int(w * 0.70)
        if z_fin > z_ini:
            sub = col_sums_v[z_ini:z_fin]
            if len(sub) > 0 and sub.max() > 0.5 * h:
                cand = z_ini + int(np.argmax(sub))
                if int(w * 0.15) < cand < int(w * 0.85):
                    x_div = cand

        y_div = None
        z_ini, z_fin = int(h * 0.30), int(h * 0.70)
        if z_fin > z_ini:
            sub = row_sums_h[z_ini:z_fin]
            if len(sub) > 0 and sub.max() > 0.7 * w:
                cand = z_ini + int(np.argmax(sub))
                if int(h * 0.15) < cand < int(h * 0.85):
                    y_div = cand

        return {
            "n_h": n_h,
            "n_v": n_v,
            "densidad": densidad,
            "lines_h": lines_h,
            "lines_v": lines_v,
            "x_div": x_div,
            "y_div": y_div,
        }

    def _contar_filas_celda(self, img_np, x_ini, y_ini, x_fin, y_fin):
        """
        Cuenta las líneas horizontales internas en una celda típica.
        Sirve para distinguir:
          - clasificación: ~11-13 filas
          - eliminatoria:   ~6-8 filas
        """
        if x_fin <= x_ini or y_fin <= y_ini:
            return 0
        region = img_np[y_ini:y_fin, x_ini:x_fin]
        gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        h_reg, w_reg = gray.shape

        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        kernel_h = cv2.getStructuringElement(
            cv2.MORPH_RECT, (max(15, int(w_reg * 0.50)), 1)
        )
        lines_h = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_h)
        row_sums = np.sum(lines_h, axis=1).astype(float)
        return self._contar_picos(row_sums, w_reg * 0.20)

    # ------------------------------------------------------------------ #
    # DECISIÓN DE LAYOUT
    # ------------------------------------------------------------------ #
    def _layout_desde_manual(self, tipo_manual, diag):
        mapa = {
            "info": ("info", "portada", ["Portada"]),
            "eliminatoria_2": ("eliminatoria", "2_arqueros_lado_a_lado", ["Puesto_1", "Puesto_2"]),
            "clasificacion_1": ("clasificacion", "1_arquero", ["Individual"]),
            "clasificacion_2_lado": ("clasificacion", "2_arqueros_lado_a_lado", ["Pos_A", "Pos_B"]),
            "clasificacion_2_arriba": ("clasificacion", "2_arqueros_arriba_abajo", ["Pos_A", "Pos_B"]),
            "clasificacion_4": ("clasificacion", "4_arqueros", ["Pos_A", "Pos_B", "Pos_C", "Pos_D"]),
        }
        return mapa.get(tipo_manual, mapa["clasificacion_1"])

    def analizar_layout(self, ruta_imagen, original_filename=None, tipo_juego_manual=None, page_override=None):
        pil_img = Image.open(ruta_imagen)
        img_np = np.array(pil_img.convert("RGB"))
        h, w = img_np.shape[:2]

        diag = self._analizar_estructura(img_np)

        # 0. Override de PÁGINA tiene prioridad absoluta
        if page_override:
            tipo_pagina, layout, posiciones = self._layout_desde_manual(page_override, diag)
            diag["metodo_deteccion"] = "override_pagina"
            return tipo_pagina, layout, posiciones, diag

        filename = (original_filename or os.path.basename(ruta_imagen)).lower()

        # 1. Override global
        if tipo_juego_manual:
            tipo_pagina, layout, posiciones = self._layout_desde_manual(tipo_juego_manual, diag)
            diag["metodo_deteccion"] = "override_global"
            return tipo_pagina, layout, posiciones, diag

        # 2. Nombre de archivo
        if any(p in filename for p in ["portada", "caratula", "info"]):
            diag["metodo_deteccion"] = "nombre_archivo"
            return "info", "portada", ["Portada"], diag

        if any(p in filename for p in ["eliminac", "duelo", "enfrentamiento"]):
            diag["metodo_deteccion"] = "nombre_archivo"
            return "eliminatoria", "2_arqueros_lado_a_lado", ["Puesto_1", "Puesto_2"], diag

        if any(p in filename for p in ["4-arqueros", "cuadrantes"]):
            diag["metodo_deteccion"] = "nombre_archivo"
            return "clasificacion", "4_arqueros", ["Pos_A", "Pos_B", "Pos_C", "Pos_D"], diag

        if any(p in filename for p in ["individual", "1a-", "crop_"]):
            diag["metodo_deteccion"] = "nombre_archivo"
            return "clasificacion", "1_arquero", ["Individual"], diag

        # 3. Análisis visual
        diag["metodo_deteccion"] = "visual"

        # 3.1. Página con poco contenido → info
        if diag["n_h"] < 5 or diag["densidad"] < 0.025:
            diag["razon"] = f"poco_contenido(n_h={diag['n_h']}, dens={diag['densidad']:.3f})"
            return "info", "portada", ["Portada"], diag

        # 3.2. Grid 2x2 completo (división vertical Y horizontal fuerte) → 4_arqueros
        if diag["x_div"] is not None and diag["y_div"] is not None and diag["n_h"] >= 15:
            diag["razon"] = f"grid_2x2(n_h={diag['n_h']}, n_v={diag['n_v']})"
            return "clasificacion", "4_arqueros", ["Pos_A", "Pos_B", "Pos_C", "Pos_D"], diag

        # 3.3. Solo división vertical fuerte → 2 arqueros lado a lado
        if diag["x_div"] is not None and diag["n_h"] >= 6:
            # Distinguir clasificación (10 series) vs eliminatoria (5 sets)
            x_ini = int(w * 0.05)
            x_fin = diag["x_div"]
            y_ini = int(h * 0.15)
            y_fin = int(h * 0.85)
            n_filas = self._contar_filas_celda(img_np, x_ini, y_ini, x_fin, y_fin)

            if n_filas <= 8:
                diag["razon"] = f"2_cols_eliminatoria(filas={n_filas})"
                return "eliminatoria", "2_arqueros_lado_a_lado", ["Puesto_1", "Puesto_2"], diag
            else:
                diag["razon"] = f"2_cols_clasificacion(filas={n_filas})"
                return "clasificacion", "2_arqueros_lado_a_lado", ["Pos_A", "Pos_B"], diag

        # 3.4. Solo división horizontal → 2 arqueros arriba/abajo
        if diag["y_div"] is not None and diag["n_h"] >= 10:
            diag["razon"] = f"2_filas(n_h={diag['n_h']})"
            return "clasificacion", "2_arqueros_arriba_abajo", ["Pos_A", "Pos_B"], diag

        # 3.5. Muchas líneas sin estructura clara → 4_arqueros por defecto
        if diag["n_h"] >= 15:
            diag["razon"] = f"muchas_lineas(n_h={diag['n_h']})"
            return "clasificacion", "4_arqueros", ["Pos_A", "Pos_B", "Pos_C", "Pos_D"], diag

        # 3.6. Default: 1 arquero
        diag["razon"] = f"default(n_h={diag['n_h']}, n_v={diag['n_v']})"
        return "clasificacion", "1_arquero", ["Individual"], diag

    # ------------------------------------------------------------------ #
    # PROCESAMIENTO DEL DOCUMENTO
    # ------------------------------------------------------------------ #
    def procesar_documento(self, ruta_archivo, tipo_juego_manual=None, page_overrides=None):
        if not os.path.exists(ruta_archivo):
            raise FileNotFoundError(f"El archivo '{ruta_archivo}' no existe.")

        page_overrides = page_overrides or {}

        original_filename = os.path.basename(ruta_archivo)
        es_pdf = ruta_archivo.lower().endswith(".pdf")
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
            "tipos_pagina": [],
            "entrada_mixta": False,
            "tareas_agente2": [],
        }

        for num_pag, img_path in paginas_imagenes:
            page_ovr = page_overrides.get(num_pag)

            tipo_pagina, layout, posiciones_activas, diag = self.analizar_layout(
                img_path,
                original_filename=original_filename,
                tipo_juego_manual=tipo_juego_manual,
                page_override=page_ovr,
            )
            
            manifiesto["tipos_pagina"].append({
                "numero": num_pag,
                "tipo": tipo_pagina,
                "layout": layout,
                "metodo_deteccion": diag.get("metodo_deteccion", "desconocido"),
                "razon": diag.get("razon", ""),
                "n_h": diag.get("n_h", 0),
                "n_v": diag.get("n_v", 0),
                "densidad": round(diag.get("densidad", 0), 4),
            })

            # Página de info/portada
            if layout == "portada":
                manifiesto["tareas_agente2"].append({
                    "pagina": num_pag,
                    "posicion_slot": "Pagina_Info",
                    "tipo_juego": "info",
                    "layout": "portada",
                    "ruta_recorte": img_path,
                })
                continue

            img = Image.open(img_path)
            w, h = img.size
            ov_x = int(w * 0.08)
            ov_y = int(h * 0.08)

            if layout == "4_arqueros":
                x_div = diag["x_div"] or (w // 2)
                y_div = diag["y_div"] or (h // 2)
                cuadrantes_coords = {
                    "Pos_A": (0, 0, min(x_div + ov_x, w), min(y_div + ov_y, h)),
                    "Pos_B": (max(x_div - ov_x, 0), 0, w, min(y_div + ov_y, h)),
                    "Pos_C": (0, max(y_div - ov_y, 0), min(x_div + ov_x, w), h),
                    "Pos_D": (max(x_div - ov_x, 0), max(y_div - ov_y, 0), w, h),
                }
            elif layout == "2_arqueros_lado_a_lado":
                x_div = diag["x_div"] or (w // 2)
                if tipo_pagina == "eliminatoria":
                    cuadrantes_coords = {
                        "Puesto_1": (0, 0, min(x_div + ov_x, w), h),
                        "Puesto_2": (max(x_div - ov_x, 0), 0, w, h),
                    }
                else:
                    cuadrantes_coords = {
                        "Pos_A": (0, 0, min(x_div + ov_x, w), h),
                        "Pos_B": (max(x_div - ov_x, 0), 0, w, h),
                    }
            elif layout == "2_arqueros_arriba_abajo":
                y_div = diag["y_div"] or (h // 2)
                cuadrantes_coords = {
                    "Pos_A": (0, 0, w, min(y_div + ov_y, h)),
                    "Pos_B": (0, max(y_div - ov_y, 0), w, h),
                }
            else:  # 1_arquero
                cuadrantes_coords = {"Individual": (0, 0, w, h)}

            for pos_id in posiciones_activas:
                if pos_id not in cuadrantes_coords:
                    continue
                coords = cuadrantes_coords[pos_id]
                crop_img = img.crop(coords)
                crop_filename = f"pag_{num_pag}_crop_{pos_id}.png"
                crop_path = os.path.join(self.output_dir, crop_filename)
                crop_img.save(crop_path, "PNG")

                manifiesto["tareas_agente2"].append({
                    "pagina": num_pag,
                    "posicion_slot": pos_id,
                    "tipo_juego": tipo_pagina,
                    "layout": layout,
                    "ruta_recorte": crop_path,
                    "x_divisoria_detectada": diag.get("x_div"),
                    "y_divisoria_detectada": diag.get("y_div"),
                })

        tipos_unicos = {p["tipo"] for p in manifiesto["tipos_pagina"]}
        manifiesto["entrada_mixta"] = len(tipos_unicos) > 1

        return manifiesto