#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Agente 1 (v26): Clasificador y Segmentador Semántico con Pre-OCR de Página Completa y Renderizado en Alta Resolución.
- Renderizado de PDF a escala 3 (Alta Definición ~2500x3500px) para máxima nitidez de grillas y OCR.
- Pre-OCR de Página Completa ANTES de segmentar en cuadrantes: clasifica con máxima precisión eliminatorias y portadas descartables vs rondas de clasificación.
- Reseteo completo de cachés de páginas y recortes.
- Pipeline Interactivo: Inspección y mejora de calidad por página y por recorte individual con opción de Deshacer (Undo).
"""

import os
import re
import json
import shutil
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


def extract_target_from_filename(filename):
    m = re.search(r'(?:^|[^0-9a-zA-Z])([0-9]{1,2}[A-Da-d])(?:$|[^0-9a-zA-Z])', filename)
    if m:
        return m.group(1).upper()
    return None


class ImageEnhancer:
    @staticmethod
    def aplicar_mejora_calidad(ruta_entrada, ruta_salida):
        """ Aplica mejora de contraste CLAHE, desruido bilateral y nitidez/enfoque. """
        if not os.path.exists(ruta_entrada):
            return False

        img_np = cv2.imread(ruta_entrada)
        if img_np is None:
            return False

        gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)

        # 1. CLAHE Contrast Enhancement
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 2. Bilateral Filter Denoising
        denoised = cv2.bilateralFilter(enhanced, d=5, sigmaColor=30, sigmaSpace=30)

        # 3. Sharpening Filter
        kernel_sharp = np.array([[0, -0.5, 0], [-0.5, 3.0, -0.5], [0, -0.5, 0]], dtype=np.float32)
        sharpened = cv2.filter2D(denoised, -1, kernel_sharp)

        # Convert to 3-channel RGB
        result_rgb = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2RGB)
        cv2.imwrite(ruta_salida, cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR))
        return True


class AgenteClasificadorSegmentador:
    def __init__(self, output_dir=None):
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="archery_agent1_")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
        self.paginas_cache = {}
        self.recortes_cache = {}

    def reset_caches(self):
        """ Limpia el caché acumulado de páginas y recortes de sesiones anteriores. """
        self.paginas_cache = {}
        self.recortes_cache = {}

    def ejecutar_pre_ocr_pagina(self, img_path):
        """ Ejecuta un OCR completo a nivel de página sobre la imagen antes de recortar. """
        if not OCR_SUPPORT or not os.path.exists(img_path):
            return ""
        try:
            img = Image.open(img_path)
            w, h = img.size
            if max(w, h) < 1600:
                scale = 1600.0 / float(max(w, h))
                img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            return pytesseract.image_to_string(img, lang="spa+eng")
        except Exception:
            return ""

    def extraer_paginas_pdf_o_imagen(self, ruta_archivo):
        """ Convierte PDF o Imagen en páginas independientes en alta definición con Pre-OCR. """
        if not os.path.exists(ruta_archivo):
            raise FileNotFoundError(f"El archivo '{ruta_archivo}' no existe.")

        self.reset_caches()

        es_pdf = ruta_archivo.lower().endswith('.pdf')
        paginas_info = []

        if es_pdf:
            if not PDF_SUPPORT:
                raise ImportError("Se requiere 'pypdfium2' para procesar archivos PDF.")
            doc = pdfium.PdfDocument(ruta_archivo)
            for i, page in enumerate(doc):
                # Render at high resolution scale=3 for sharp text and table grid lines
                bitmap = page.render(scale=3)
                pil_img = bitmap.to_pil()
                img_orig_path = os.path.join(self.output_dir, f"pagina_{i+1}_orig.png")
                img_act_path = os.path.join(self.output_dir, f"pagina_{i+1}_actual.png")
                pil_img.save(img_orig_path, "PNG")
                pil_img.save(img_act_path, "PNG")

                ocr_texto = self.ejecutar_pre_ocr_pagina(img_act_path)

                pag_data = {
                    "numero_pagina": i + 1,
                    "ruta_original": img_orig_path,
                    "ruta_actual": img_act_path,
                    "pre_ocr_texto": ocr_texto,
                    "es_mejorada": False
                }
                self.paginas_cache[i + 1] = pag_data
                paginas_info.append(pag_data)
        else:
            img_orig_path = os.path.join(self.output_dir, "pagina_1_orig.png")
            img_act_path = os.path.join(self.output_dir, "pagina_1_actual.png")
            shutil.copy(ruta_archivo, img_orig_path)
            shutil.copy(ruta_archivo, img_act_path)

            ocr_texto = self.ejecutar_pre_ocr_pagina(img_act_path)

            pag_data = {
                "numero_pagina": 1,
                "ruta_original": img_orig_path,
                "ruta_actual": img_act_path,
                "pre_ocr_texto": ocr_texto,
                "es_mejorada": False
            }
            self.paginas_cache[1] = pag_data
            paginas_info.append(pag_data)

        return paginas_info

    def mejorar_calidad_pagina(self, num_pagina):
        """ Aplica filtro de mejora de calidad sobre la página especificada. """
        if not num_pagina:
            return False, "⚠️ Selecciona un número de página válido."

        num_pag = int(num_pagina)
        if num_pag not in self.paginas_cache:
            return False, f"⚠️ Página {num_pag} no encontrada en el documento actual."

        pag = self.paginas_cache[num_pag]
        exito = ImageEnhancer.aplicar_mejora_calidad(pag["ruta_original"], pag["ruta_actual"])
        if exito:
            pag["es_mejorada"] = True
            # Re-ejecutar Pre-OCR con la página mejorada
            pag["pre_ocr_texto"] = self.ejecutar_pre_ocr_pagina(pag["ruta_actual"])
            return True, f"✨ Calidad mejorada con éxito para Página {num_pag}."
        return False, f"⚠️ Error al procesar la mejora para Página {num_pag}."

    def deshacer_mejora_pagina(self, num_pagina):
        """ Restaura la versión original de la página sin filtros. """
        if not num_pagina:
            return False, "⚠️ Selecciona un número de página válido."

        num_pag = int(num_pagina)
        if num_pag not in self.paginas_cache:
            return False, f"⚠️ Página {num_pag} no encontrada en el documento actual."

        pag = self.paginas_cache[num_pag]
        shutil.copy(pag["ruta_original"], pag["ruta_actual"])
        pag["es_mejorada"] = False
        pag["pre_ocr_texto"] = self.ejecutar_pre_ocr_pagina(pag["ruta_actual"])
        return True, f"↩️ Se restauró la versión original para Página {num_pagina}."

    @staticmethod
    def tiene_tabla_de_tiros(ruta_imagen):
        if not os.path.exists(ruta_imagen):
            return False

        img = cv2.imread(ruta_imagen, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return False

        h, w = img.shape
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w // 25), 1))
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, h // 25)))

        thresh = cv2.adaptiveThreshold(~img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, -2)

        lines_h = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_h)
        lines_v = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_v)

        table_mask = cv2.add(lines_h, lines_v)
        table_pixels = np.sum(table_mask > 0)
        ratio = table_pixels / float(h * w)

        contours, _ = cv2.findContours(table_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rect_count = sum(1 for c in contours if cv2.boundingRect(c)[2] > 15 and cv2.boundingRect(c)[3] > 10 and (cv2.boundingRect(c)[2] * cv2.boundingRect(c)[3]) > 200)

        return (ratio > 0.005) and (rect_count >= 8)

    @staticmethod
    def evaluar_densidad_tinta_cuadrante(ruta_imagen, coords):
        if not os.path.exists(ruta_imagen):
            return True

        img = cv2.imread(ruta_imagen, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return True

        x1, y1, x2, y2 = coords
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            return True

        h_c, w_c = crop.shape
        table_crop = crop[int(h_c * 0.20):int(h_c * 0.95), int(w_c * 0.05):int(w_c * 0.95)]
        if table_crop.size == 0:
            return True

        dark_ink = (table_crop < 130).astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        ink_only = cv2.morphologyEx(dark_ink, cv2.MORPH_OPEN, kernel)

        ink_count = int(np.sum(ink_only))
        ratio = ink_count / float(table_crop.shape[0] * table_crop.shape[1])

        return (ratio < 0.0003) or (ink_count < 25)

    def analizar_layout(self, ruta_imagen, tipo_juego_manual=None, pre_ocr_texto=""):
        filename = os.path.basename(ruta_imagen).lower()

        if tipo_juego_manual and tipo_juego_manual != "Auto":
            m = str(tipo_juego_manual).lower()
            if "info" in m or "portada" in m:
                return "informacion", "portada"
            elif "eliminatoria" in m or "duelo" in m or "2" in m:
                return "eliminatoria", "2_arqueros"
            elif "clasificacion_1" in m or "1_arquero" in m or "individual" in m:
                return "clasificacion", "1_arquero"
            elif "clasificacion_2" in m:
                return "clasificacion", "2_arqueros"
            elif "clasificacion_4" in m or "4_arqueros" in m:
                return "clasificacion", "4_arqueros"

        # Pre-OCR de página si no viene suministrado
        text_raw = pre_ocr_texto or self.ejecutar_pre_ocr_pagina(ruta_imagen)
        text_lower = text_raw.lower()

        # 1. Detectar Eliminatorias (Descarte automático de rondas de duelos/eliminación)
        keywords_llaves_strict = [
            r'1/16\s*final', r'1/8\s*final', r'1/4\s*final', r'1/2\s*final', r'\boro\b', r'\bbronce\b',
            r'\bbronze\b', r'\bgold\b', r'semifinal', r'cuartos', r'octavos', r'16vos', r'8vos', r'4tos',
            r'set\s*total', r'set\s*point', r'total\s*set\s*point', r'puntos\s*de\s*set', r'sot\s*point',
            r'desempate', r'total\s*set', r'match', r'encuentro\s*final'
        ]
        keywords_fn_elim = ["duelo", "eliminac", "1-8", "1-4", "1-2", "oro", "bronce"]
        is_elim = any(re.search(pat, text_lower) for pat in keywords_llaves_strict) or any(kw in filename for kw in keywords_fn_elim)
        if is_elim:
            return "eliminatoria", "2_arqueros"

        # 2. Detectar Clasificación (Rondas de ranking de 10 series)
        pat_dist_clas = r'\b(?:10|15|18|20|30|40|50|60|70)\s*(?:m|mts|metros)?\s*[\-\_]?\s*[12]\b|\bturno\s*:?\s*[12]\b|\bronda\s*:?\s*[12]\b'
        is_clas = bool(re.search(pat_dist_clas, text_lower))

        # 3. Geometría y Aspect Ratio
        img_pil = Image.open(ruta_imagen)
        w, h = img_pil.size

        if "4-arqueros" in filename or "4arqueros" in filename:
            return "clasificacion", "4_arqueros"

        pattern_1_arquero = r'^(?:[0-9]{1,2}[a-d])[\_\-]|(?:crop|recorte|individual|1[-_]arquero|1arquero)'
        if re.search(pattern_1_arquero, filename) or (w < 750 and h < 850):
            return "clasificacion", "1_arquero"

        if is_clas:
            if w > h * 1.15:
                return "clasificacion", "2_arqueros"
            return "clasificacion", "4_arqueros"

        if w > h * 1.15:
            return "eliminatoria", "2_arqueros"

        return "clasificacion", "4_arqueros"

    def procesar_documento(self, ruta_archivo, tipo_juego_manual=None, page_overrides=None):
        """
        Segmenta el documento en recortes de cuadrantes basándose en las imágenes actuales de página.
        """
        if not self.paginas_cache:
            self.extraer_paginas_pdf_o_imagen(ruta_archivo)

        # RESETS RECORTES CACHE TO PREVENT ACCUMULATING STALE CROPS FROM PREVIOUS RUNS
        self.recortes_cache = {}

        manifiesto = {
            "archivo_origen": os.path.basename(ruta_archivo),
            "total_paginas": len(self.paginas_cache),
            "tareas_agente2": []
        }

        fn_global = os.path.basename(ruta_archivo)
        target_desde_nombre = extract_target_from_filename(fn_global)
        margin = 20

        for num_pag, pag_data in self.paginas_cache.items():
            img_path = pag_data["ruta_actual"]
            pre_ocr_txt = pag_data.get("pre_ocr_texto", "")
            modo_manual = tipo_juego_manual
            if page_overrides and isinstance(page_overrides, dict):
                modo_manual = page_overrides.get(str(num_pag), modo_manual)

            tipo_juego_pagina, layout = self.analizar_layout(img_path, tipo_juego_manual=modo_manual, pre_ocr_texto=pre_ocr_txt)
            img = Image.open(img_path)
            w, h = img.size

            tiene_tabla = self.tiene_tabla_de_tiros(img_path)
            es_elim = (tipo_juego_pagina == "eliminatoria")
            es_pagina_info_forzada = (layout == "portada" or tipo_juego_pagina in ["info", "informacion"] or es_elim)

            if layout == "4_arqueros":
                cuadrantes_coords_tentativos = {
                    "A": (0, 0, min(w, w // 2 + margin), min(h, h // 2 + margin)),
                    "B": (max(0, w // 2 - margin), 0, w, min(h, h // 2 + margin)),
                    "C": (0, max(0, h // 2 - margin), min(w, w // 2 + margin), h),
                    "D": (max(0, w // 2 - margin), max(0, h // 2 - margin), w, h)
                }
            elif layout == "2_arqueros":
                cuadrantes_coords_tentativos = {
                    "A": (0, 0, min(w, w // 2 + margin), h),
                    "B": (max(0, w // 2 - margin), 0, w, h)
                }
            else:
                tid = target_desde_nombre if target_desde_nombre else "1A"
                cuadrantes_coords_tentativos = {tid: (0, 0, w, h)}

            vacios_cuadrantes = {k: self.evaluar_densidad_tinta_cuadrante(img_path, c) for k, c in cuadrantes_coords_tentativos.items()}
            todos_cuadrantes_vacios = all(vacios_cuadrantes.values())

            if not tiene_tabla or es_pagina_info_forzada or todos_cuadrantes_vacios:
                crop_orig_path = os.path.join(self.output_dir, f"pag_{num_pag}_pos_Portada_orig.png")
                crop_act_path = os.path.join(self.output_dir, f"pag_{num_pag}_pos_Portada_actual.png")
                img.save(crop_orig_path, "PNG")
                img.save(crop_act_path, "PNG")

                if es_elim:
                    task_key = f"Pág {num_pag} - Eliminatoria"
                    tipo_j = "eliminatoria"
                else:
                    task_key = f"Pág {num_pag} - Hoja de Información / Portada"
                    tipo_j = "informacion"

                crop_info = {
                    "pagina": num_pag,
                    "target_id": "Portada",
                    "tipo_juego": tipo_j,
                    "layout": "portada" if not es_elim else "2_arqueros",
                    "ruta_recorte_original": crop_orig_path,
                    "ruta_recorte": crop_act_path,
                    "label": task_key,
                    "es_pagina_informacion": True,
                    "es_cuadrante_vacio": False,
                    "es_mejorado": False
                }
                self.recortes_cache[task_key] = crop_info
                manifiesto["tareas_agente2"].append(crop_info)
            else:
                for target_pos, coords in cuadrantes_coords_tentativos.items():
                    crop_img = img.crop(coords)
                    crop_orig_path = os.path.join(self.output_dir, f"pag_{num_pag}_pos_{target_pos}_orig.png")
                    crop_act_path = os.path.join(self.output_dir, f"pag_{num_pag}_pos_{target_pos}_actual.png")
                    crop_img.save(crop_orig_path, "PNG")
                    crop_img.save(crop_act_path, "PNG")

                    es_vacio = vacios_cuadrantes.get(target_pos, False)
                    lbl_tipo = tipo_juego_pagina.capitalize()
                    label_str = f"Pág {num_pag} - {lbl_tipo} (Pos {target_pos})"

                    crop_info = {
                        "pagina": num_pag,
                        "target_id": target_pos,
                        "tipo_juego": tipo_juego_pagina,
                        "layout": layout,
                        "ruta_recorte_original": crop_orig_path,
                        "ruta_recorte": crop_act_path,
                        "label": label_str,
                        "es_pagina_informacion": False,
                        "es_cuadrante_vacio": es_vacio,
                        "es_mejorado": False
                    }
                    self.recortes_cache[label_str] = crop_info
                    manifiesto["tareas_agente2"].append(crop_info)

        print(f"[Agente 1] ✂️ Completada la clasificación y segmentación de {len(self.paginas_cache)} página(s) aplicando descarte de hoja completa sin tabla.")
        return manifiesto

    def mejorar_calidad_recorte(self, label_recorte):
        """ Aplica filtro de mejora de calidad sobre un recorte de cuadrante específico. """
        if not label_recorte:
            return False, "⚠️ Selecciona un recorte válido."

        if label_recorte not in self.recortes_cache:
            return False, f"⚠️ Recorte '{label_recorte}' no encontrado en caché."

        rec = self.recortes_cache[label_recorte]
        exito = ImageEnhancer.aplicar_mejora_calidad(rec["ruta_recorte_original"], rec["ruta_recorte"])
        if exito:
            rec["es_mejorado"] = True
            return True, f"✨ Calidad mejorada con éxito para recorte '{label_recorte}'."
        return False, f"⚠️ Error al procesar la mejora para '{label_recorte}'."

    def deshacer_mejora_recorte(self, label_recorte):
        """ Restaura la versión original del recorte de cuadrante sin filtros. """
        if not label_recorte:
            return False, "⚠️ Selecciona un recorte válido."

        if label_recorte not in self.recortes_cache:
            return False, f"⚠️ Recorte '{label_recorte}' no encontrado en caché."

        rec = self.recortes_cache[label_recorte]
        shutil.copy(rec["ruta_recorte_original"], rec["ruta_recorte"])
        rec["es_mejorado"] = False
        return True, f"↩️ Se restauró la versión original para '{label_recorte}'."
