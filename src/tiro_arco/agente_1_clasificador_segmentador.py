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
        """
        Regla de negocio ajustada:
        1. Palabras clave de eliminatoria: "Puesto", "S.O." / "SO", "Ganador", "Duelo", "Eliminacion".
        2. De no estar estas palabras clave de eliminatoria, se clasifica por defecto como "clasificacion".
        3. El descarte de hojas de información o sin tablas se realiza posteriormente en el Agente 2 (OCR / OpenCV).
        """
        filename = os.path.basename(ruta_imagen).lower()

        # 1. Selección manual
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

        # 2. Detección de Eliminatoria por Palabras Clave de Negocio (Puesto, S.O., Ganador, Duelo, Eliminatoria)
        keywords_eliminatoria = ["puesto", "s.o.", "so", "ganador", "duelo", "eliminac"]
        if any(kw in filename for kw in keywords_eliminatoria):
            return "eliminatoria", "2_arqueros"

        # 3. Detección por Nombre de Archivo para 4 arqueros
        if any(p in filename for p in ["4-arqueros", "4arqueros"]):
            return "clasificacion", "4_arqueros"

        # 4. Detección por Nombre de Archivo para Recortes Individuales
        pattern_1_arquero = r'^(?:[0-9]{1,2}[a-d])[\_\-]|(?:crop|recorte|individual|1[-_]arquero|1arquero)'
        if re.search(pattern_1_arquero, filename):
            return "clasificacion", "1_arquero"

        # 5. Clasificación por Geometría (Por Defecto Clasificatoria)
        pil_img = Image.open(ruta_imagen)
        w, h = pil_img.size

        # Si es un recorte pequeño (<750x850px)
        if w < 750 and h < 850:
            return "clasificacion", "1_arquero"

        # Si es formato apaisado mediano (w > h * 1.2)
        if w > h * 1.2:
            return "clasificacion", "2_arqueros"

        # Por defecto 4 arqueros (Clasificatoria)
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
                    "A": (0, 0, w // 2, h // 2),
                    "B": (w // 2, 0, w, h // 2),
                    "C": (0, h // 2, w // 2, h),
                    "D": (w // 2, h // 2, w, h)
                }
            elif layout == "2_arqueros":
                cuadrantes_coords = {
                    "A": (0, 0, w // 2, h),
                    "B": (w // 2, 0, w, h)
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

        print(f"[Agente 1] ✂️ Completada la clasificación y segmentación de {len(paginas_imagenes)} página(s). Se generaron {len(manifiesto['tareas_agente2'])} recortes de dianas en total.")
        return manifiesto
