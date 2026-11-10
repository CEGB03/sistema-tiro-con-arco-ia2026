#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Agente 1 (v28): Clasificador y Segmentador Semántico con Renderizado PDF Ultra-HD 300 DPI y Pre-OCR:
- Renderiza PDFs a resolución Ultra-HD de 300 DPI (scale=4.1667) para eliminar borrosidad en tablas y números manuscritos.
- Resetea caches de páginas y recortes al cargar nuevos documentos.
- Pre-OCR de página completa para filtrado infalible de descartes (Portadas / Eliminatorias).
- Mejora de calidad individual de páginas y recortes con opción de Deshacer (Undo).
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

    def extraer_paginas_pdf_o_imagen(self, ruta_archivo):
        """ Convierte PDF o Imagen en páginas independientes en Ultra-HD (300 DPI). """
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
                # ULTRA HIGH DEFINITION: Renderizado a 300 DPI (scale=4.1667 => 72*4.1667 = 300 DPI)
                bitmap = page.render(scale=4.1667)
                pil_img = bitmap.to_pil()
                img_orig_path = os.path.join(self.output_dir, f"pagina_{i+1}_orig.png")
                img_act_path = os.path.join(self.output_dir, f"pagina_{i+1}_actual.png")
                pil_img.save(img_orig_path, "PNG", compress_level=0)
                pil_img.save(img_act_path, "PNG", compress_level=0)

                # Pre-OCR de página completa en alta resolución
                text_page_raw = ""
                if OCR_SUPPORT:
                    try:
                        text_page_raw = pytesseract.image_to_string(pil_img, lang="spa+eng")
                    except Exception:
                        pass

                pag_data = {
                    "numero_pagina": i + 1,
                    "ruta_original": img_orig_path,
                    "ruta_actual": img_act_path,
                    "es_mejorada": False,
                    "pre_ocr_texto": text_page_raw
                }
                self.paginas_cache[i + 1] = pag_data
                paginas_info.append(pag_data)
        else:
            img_orig_path = os.path.join(self.output_dir, "pagina_1_orig.png")
            img_act_path = os.path.join(self.output_dir, "pagina_1_actual.png")
            shutil.copy(ruta_archivo, img_orig_path)
            shutil.copy(ruta_archivo, img_act_path)

            text_page_raw = ""
            if OCR_SUPPORT:
                try:
                    pil_img = Image.open(ruta_archivo)
                    text_page_raw = pytesseract.image_to_string(pil_img, lang="spa+eng")
                except Exception:
                    pass

            pag_data = {
                "numero_pagina": 1,
                "ruta_original": img_orig_path,
                "ruta_actual": img_act_path,
                "es_mejorada": False,
                "pre_ocr_texto": text_page_raw
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
        return True, f"↩️ Se restauró la versión original para Página {num_pag}."

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

    @staticmethod
    def ejecutar_micro_ocr_cabecera(ruta_imagen, pre_ocr_texto=""):
        if not OCR_SUPPORT or not os.path.exists(ruta_imagen):
            return "indefinido", []

        try:
            if pre_ocr_texto and len(pre_ocr_texto) > 10:
                text_lower = pre_ocr_texto.lower()
            else:
                img = Image.open(ruta_imagen)
                w, h = img.size
                if max(w, h) > 1600:
                    scale = 1600.0 / float(max(w, h))
                    img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
                text_lower = pytesseract.image_to_string(img, lang="spa+eng").lower()

            hallazgos_clas = []
            hallazgos_elim = []

            pat_dist_clas = r'\b(?:10|15|18|20|30|40|50|60|70)\s*(?:m|mts|metros)?\s*[\-\_]?\s*[12]\b|\bturno\s*:?\s*[12]\b|\bronda\s*:?\s*[12]\b'
            m_clas = re.findall(pat_dist_clas, text_lower)
            if m_clas:
                hallazgos_clas.extend(m_clas)

            keywords_llaves_strict = [
                r'1/16\s*final', r'1/8\s*final', r'1/4\s*final', r'1/2\s*final', r'\boro\b', r'\bbronce\b',
                r'\bbronze\b', r'\bgold\b', r'semifinal', r'cuartos', r'octavos', r'16vos', r'8vos', r'4tos', r'final'
            ]
            keywords_sets_strict = [
                r'set\s*total', r'set\s*point', r'total\s*set\s*point', r'puntos\s*de\s*set',
                r'\bp\.s\.\b', r'\bs\.p\.\b', r'\bsets\b', r'sot\s*point'
            ]
            keywords_compuesto_elim = [
                r'\bdes\.\b', r'desempate', r'total\s*set', r'\bs\.o\.\b', r'\bso\b',
                r'puesto', r'ganador', r'duelo', r'eliminac', r'match'
            ]

            for pat in keywords_llaves_strict + keywords_sets_strict + keywords_compuesto_elim:
                if re.search(pat, text_lower):
                    hallazgos_elim.append(pat.replace(r'\b', '').replace(r'\s*', ' '))

            if hallazgos_clas and not hallazgos_elim:
                return "clasificacion", hallazgos_clas
            elif hallazgos_elim and not hallazgos_clas:
                return "eliminatoria", hallazgos_elim
            elif hallazgos_clas and hallazgos_elim:
                return "clasificacion", hallazgos_clas

            return "indefinido", []
        except Exception:
            return "indefinido", []

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

        keywords_eliminatoria_fn = ["puesto", "s.o.", "so", "ganador", "duelo", "eliminac", "1-8", "1-4", "1-2", "oro", "bronce"]
        if any(kw in filename for kw in keywords_eliminatoria_fn):
            return "eliminatoria", "2_arqueros"

        if any(p in filename for p in ["4-arqueros", "4arqueros"]):
            return "clasificacion", "4_arqueros"

        tipo_ocr, hallazgos = self.ejecutar_micro_ocr_cabecera(ruta_imagen, pre_ocr_texto=pre_ocr_texto)
        if tipo_ocr == "clasificacion":
            print(f"[Agente 1] 🎯 Clasificación detectada por marca de distancia/turno en '{os.path.basename(ruta_imagen)}' ({hallazgos})")
            pil_img = Image.open(ruta_imagen)
            w, h = pil_img.size
            if w > h * 1.15:
                return "clasificacion", "2_arqueros"
            return "clasificacion", "4_arqueros"
        elif tipo_ocr == "eliminatoria":
            print(f"[Agente 1] 🎯 Eliminatoria detectada por Micro-OCR en '{os.path.basename(ruta_imagen)}' ({hallazgos})")
            return "eliminatoria", "2_arqueros"

        pil_img = Image.open(ruta_imagen)
        w, h = pil_img.size

        if w > h * 1.15:
            return "eliminatoria", "2_arqueros"

        pattern_1_arquero = r'^(?:[0-9]{1,2}[a-d])[\_\-]|(?:crop|recorte|individual|1[-_]arquero|1arquero)'
        if re.search(pattern_1_arquero, filename):
            return "clasificacion", "1_arquero"

        if w < 750 and h < 850:
            return "clasificacion", "1_arquero"

        return "clasificacion", "4_arqueros"

    def procesar_documento(self, ruta_archivo, tipo_juego_manual=None, page_overrides=None):
        if not self.paginas_cache:
            self.extraer_paginas_pdf_o_imagen(ruta_archivo)

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

                task_key = f"Pág {num_pag} - {'Eliminatoria' if es_elim else 'Hoja de Información / Portada'}"
                crop_info = {
                    "pagina": num_pag,
                    "target_id": "Portada",
                    "tipo_juego": tipo_juego_pagina if es_elim else "informacion",
                    "layout": "portada",
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
        if label_recorte not in self.recortes_cache:
            return False, "Recorte no encontrado en caché."

        rec = self.recortes_cache[label_recorte]
        exito = ImageEnhancer.aplicar_mejora_calidad(rec["ruta_recorte_original"], rec["ruta_recorte"])
        if exito:
            rec["es_mejorado"] = True
            return True, f"✨ Calidad mejorada con éxito para recorte '{label_recorte}'."
        return False, f"⚠️ Error al procesar la mejora para '{label_recorte}'."

    def deshacer_mejora_recorte(self, label_recorte):
        """ Restaura la versión original del recorte de cuadrante sin filtros. """
        if label_recorte not in self.recortes_cache:
            return False, "Recorte no encontrado en caché."

        rec = self.recortes_cache[label_recorte]
        shutil.copy(rec["ruta_recorte_original"], rec["ruta_recorte"])
        rec["es_mejorado"] = False
        return True, f"↩️ Se restauró la versión original para '{label_recorte}'."
