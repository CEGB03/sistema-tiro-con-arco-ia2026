#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Agente 2 (v61): Extractor OCR con Homogeneidad Documental, Descarte de Hoja Completa,
Matching Robusto de Recortes Seleccionados y Refactorización Secundaria vía LLM.
"""

import os
import re
import json
import base64
import tempfile
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import numpy as np
import cv2
import threading

class RateLimiter:
    """ Controlador de Tasa (35 RPM para prevenir HTTP 429 en API Key de NVIDIA NIM) """
    def __init__(self, requests_per_minute=35):
        self.interval = 60.0 / requests_per_minute
        self.last_request_time = 0.0
        self.lock = threading.Lock()

    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.interval:
                sleep_time = self.interval - elapsed
                time.sleep(sleep_time)
            self.last_request_time = time.time()

global_rate_limiter = RateLimiter(requests_per_minute=35)

try:
    import pytesseract
    OCR_SUPPORT = True
except ImportError:
    OCR_SUPPORT = False


def _obtener_nvidia_api_key():
    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if api_key:
        return api_key

    directorio_actual = os.getcwd()
    for _ in range(5):
        posible_env = os.path.join(directorio_actual, ".env")
        if os.path.exists(posible_env):
            try:
                with open(posible_env, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() in ["NVIDIA_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"]:
                                val = v.strip().strip("'").strip('"')
                                os.environ["NVIDIA_API_KEY"] = val
                                return val
            except Exception:
                pass
        padre = os.path.dirname(directorio_actual)
        if padre == directorio_actual:
            break
        directorio_actual = padre
    return ""



def extraer_datos_cabecera_robusta(text_raw, target_id_default="N/A"):
    cleaned = re.sub(r'<x_[0-9\.]+>', '', text_raw)
    cleaned = re.sub(r'<y_[0-9\.]+>', '', cleaned)
    cleaned = re.sub(r'<class_[^>]+>', '', cleaned)
    cleaned = re.sub(r'[\*\#\_]', '', cleaned).strip()

    cat_codes = [
        r'\b(?:R|C|B|T|I|E|L)\s*(?:M|W|F|50M|60M|70M|U[0-9]+[A-Z0-9]*|E[0-9]+)\b',
        r'\b(?:RM|RW|CM|CW|BM|BW|TM|TW|IM|IW)\b'
    ]

    # 1. Target
    target = target_id_default
    m_tgt = re.search(r'\b([0-9]{1,2}\s*[A-D])\b', cleaned, re.IGNORECASE)
    if m_tgt:
        target = re.sub(r'\s+', '', m_tgt.group(1)).upper()

    # 2. Categoría
    cat = "N/A"
    m_cat_lbl = re.search(r'(?:Cat(?:egor[ií]a)?|Categor\:\s*)\s*:?\s*([^\n<]+)', cleaned, re.IGNORECASE)
    if m_cat_lbl:
        cand_cat = m_cat_lbl.group(1).strip()
        cand_cat = re.sub(r'\b[0-9]{1,2}\s*[A-D]\b.*$', '', cand_cat, flags=re.IGNORECASE).strip()
        if len(cand_cat) > 1:
            cat = cand_cat

    if cat == "N/A" or len(cat) > 25:
        for pat in cat_codes:
            m_c = re.search(pat, cleaned, re.IGNORECASE)
            if m_c:
                cat = m_c.group(0).strip().upper()
                break

    # Limpiar categoría del texto para extraer el club sin contaminación
    cleaned_no_cat = cleaned
    if cat != "N/A":
        cleaned_no_cat = re.sub(re.escape(cat), '', cleaned_no_cat, flags=re.IGNORECASE)
    for pat in cat_codes:
        cleaned_no_cat = re.sub(pat, '', cleaned_no_cat, flags=re.IGNORECASE)

    # 3. Club
    club = "N/A"
    m_club = re.search(r'\b(?:P/A/C|P/F/C|PIAIC|Club)\b\s*:?\s*([^\n<]+)', cleaned_no_cat, re.IGNORECASE)
    if m_club:
        cand_club = m_club.group(1).strip()
        cand_club = re.sub(r'\b[0-9]{1,2}\s*[A-D]\b.*$', '', cand_club, flags=re.IGNORECASE).strip()
        if len(cand_club) > 1:
            club = cand_club

    # 4. Arquero
    arquero = "Desconocido"
    
    # 4a. Intento por etiqueta estricta ('Arquero:', 'Archer:', 'Athlete:', 'Nombre:')
    m_arq = re.search(r'\b(?:Arquero|Archer|Athlete|Nombre)\b[\s\:\-\_]*([^\n\<]+)', cleaned, re.IGNORECASE)
    if m_arq:
        cand = m_arq.group(1).strip()
        cand = re.sub(r'\b[0-9]{1,2}\s*[A-D]\b.*$', '', cand, flags=re.IGNORECASE).strip()
        cand = re.sub(r'(?:P/A/C|P/F/C|PIAIC|Club).*$', '', cand, flags=re.IGNORECASE).strip()
        words = cand.lower().split()
        if cand and not any(w in ['tanteador', 'planillero', 'juez', 'firma', 'signature', 'detectado', 'desconocido', 'null', 'none'] for w in words):
            if len(cand) > 2 and not cand.isdigit():
                arquero = cand

    # 4b. Intento por posición si no hubo etiqueta o dio Desconocido
    if arquero == "Desconocido":
        m_before = re.search(r'([A-Za-zÁÉÍÓÚáéíóúÑñ0-9\s\.\,\-]{3,60}?)\s+\b(?:P/A/C|P/F/C|PIAIC|Club)\b\s*:', cleaned, re.IGNORECASE)
        if m_before:
            cand_b = m_before.group(1).strip()
            cand_b = re.sub(r'\b[0-9]{1,2}\s*[A-D]\b', '', cand_b, flags=re.IGNORECASE).strip()
            if '\n' in cand_b:
                lines = [l.strip() for l in cand_b.split('\n') if l.strip()]
                valid_lines = [l for l in lines if not any(w in l.lower() for w in ['torneo', 'copa', 'asociacion', 'asociación', 'federacion', 'federación', 'archery', 'world', 'ronda', 'turno'])]
                if valid_lines:
                    cand_b = valid_lines[-1]
            words_b = cand_b.lower().split()
            if cand_b and not any(w in ['torneo', 'copa', 'asociacion', 'asociación', 'federacion', 'federación', 'archery', 'world', 'tanteador', 'planillero', 'juez', 'detectado', 'desconocido'] for w in words_b):
                if len(cand_b) > 2 and not cand_b.isdigit():
                    arquero = cand_b

    return {"arquero": arquero, "target": target, "club": club, "categoria": cat}


def extraer_cabecera_tesseract(text_raw, target_id_default="N/A"):
    return extraer_datos_cabecera_robusta(text_raw, target_id_default=target_id_default)


class ImageEnhancer:
    @staticmethod
    def redimensionar_suave(ruta_imagen, output_dir=None, max_dim=1280):
        if not os.path.exists(ruta_imagen):
            return ruta_imagen

        img_pil = Image.open(ruta_imagen).convert('RGB')
        w, h = img_pil.size

        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            new_w, new_h = int(w * scale), int(h * scale)
            img_pil = img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            base_name = os.path.basename(ruta_imagen)
            out_path = os.path.join(output_dir, f"clean_{base_name}")
        else:
            out_path = ruta_imagen.replace(".png", "_clean.png")

        img_pil.save(out_path, "PNG")
        return out_path

    @staticmethod
    def mejorar_imagen(ruta_imagen, output_dir=None, max_dim=1280):
        if not os.path.exists(ruta_imagen):
            return ruta_imagen

        img_pil = Image.open(ruta_imagen)
        w, h = img_pil.size

        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            new_w, new_h = int(w * scale), int(h * scale)
            img_pil = img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)

        img_np = np.array(img_pil.convert('RGB'))
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced_gray = clahe.apply(gray)
        denoised = cv2.bilateralFilter(enhanced_gray, d=5, sigmaColor=35, sigmaSpace=35)

        result_rgb = cv2.cvtColor(denoised, cv2.COLOR_GRAY2RGB)
        result_pil = Image.fromarray(result_rgb)

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            base_name = os.path.basename(ruta_imagen)
            out_path = os.path.join(output_dir, f"proc_{base_name}")
        else:
            out_path = ruta_imagen.replace(".png", "_proc.png")

        result_pil.save(out_path, "PNG")
        return out_path

    @staticmethod
    def detectar_tabla_vacia(ruta_imagen):
        if not os.path.exists(ruta_imagen):
            return False

        img = cv2.imread(ruta_imagen, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return False

        h, w = img.shape
        table_crop = img[int(h * 0.20):int(h * 0.95), int(w * 0.05):int(w * 0.95)]
        if table_crop.size == 0:
            return False

        dark_ink = (table_crop < 130).astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        ink_only = cv2.morphologyEx(dark_ink, cv2.MORPH_OPEN, kernel)

        ink_count = int(np.sum(ink_only))
        ratio = ink_count / float(table_crop.shape[0] * table_crop.shape[1])

        return (ratio < 0.0003) or (ink_count < 25)


class Agente2OCRExtractor:

    def _generar_archivo_auditoria(self, manifiesto_agente2):
        auditoria_list = []
        for item in manifiesto_agente2.get("transcripciones", []):
            trans = item.get("transcripcion", {})
            auditoria_list.append({
                "pagina": item.get("pagina"),
                "target_id": item.get("target_id"),
                "tipo_juego": item.get("tipo_juego"),
                "arquero": trans.get("arquero", "Desconocido"),
                "target_leido": trans.get("target", "N/A"),
                "modelo_usado": trans.get("modelo_usado", "N/A"),
                "tiempo_inferencia_seg": trans.get("tiempo_inferencia_seg", 0),
                "nemotron_raw_output": trans.get("texto_raw_ocr", ""),
                "refactored_parsed_json": trans
            })

        ruta_auditoria_json = os.path.join(self.output_dir, "auditoria_nemotron_raw_vs_refactorizado.json")
        try:
            with open(ruta_auditoria_json, "w", encoding="utf-8") as f_aud:
                json.dump(auditoria_list, f_aud, indent=2, ensure_ascii=False)
        except Exception:
            pass

        manifiesto_agente2["ruta_archivo_auditoria_json"] = ruta_auditoria_json
        manifiesto_agente2["auditoria_nemotron"] = auditoria_list
        return manifiesto_agente2

    def _parsear_salida_nemotron(self, content_text, target_id_default="N/A", tipo_juego="clasificacion"):
        cleaned = re.sub(r'<x_[0-9\.]+>', '', content_text)
        cleaned = re.sub(r'<y_[0-9\.]+>', '', cleaned)
        cleaned = re.sub(r'<class_[^>]+>', '', cleaned)

        info_cab = extraer_datos_cabecera_robusta(content_text, target_id_default=target_id_default)
        arquero = info_cab["arquero"]
        target = info_cab["target"]
        club = info_cab["club"]
        cat = info_cab["categoria"]
        arquero_desconocido = (arquero == "Desconocido" or arquero.lower() in ["tanteador", "planillero", "desconocido"])

        # NOTA: Solo se consideran las modalidades de Sala (10m, 15m, 18m) y Aire Libre (15m, 20m, 30m, 40m, 50m, 60m, 70m) de momento.
        # 5. Ronda / Turno y Distancia (Regla de Oro de Clasificación: Distancia -1 / -2)
        ronda = "1"
        m_ronda_dist = re.search(r'\b(?:10|15|18|20|30|40|50|60|70)\s*(?:m|mts)?\s*[\-\_]?\s*([12])\b', cleaned, re.IGNORECASE)
        if m_ronda_dist:
            ronda = m_ronda_dist.group(1)
        else:
            m_turno = re.search(r'Turno:\s*([0-9]+)', cleaned, re.IGNORECASE)
            if m_turno:
                ronda = m_turno.group(1)

        distancia = "18m"
        m_dist = re.search(r'\b((?:10|15|18|20|30|40|50|60|70)\s*(?:m|mts)?)\b', cleaned, re.IGNORECASE)
        if m_dist:
            distancia = re.sub(r'\s+', '', m_dist.group(1)).lower()

        # 5b. Totales en texto crudo
        totales_raw = {"total_puntos": 0, "cant_10s": 0, "cant_9s": 0}
        m_tot = re.search(r"\\multicolumn\{.*?\}\{.*?(?:Total|\*\*Total\*\*).*?\}\s*&\s*([0-9]{1,3})\s*&\s*([0-9]{1,2})?\s*&\s*([0-9]{1,2})?", content_text, re.IGNORECASE)
        if not m_tot:
            m_tot = re.search(r'\*\*Total\*\*\s*([0-9]{1,3})\s*([0-9]{1,2})?\s*([0-9]{1,2})?', cleaned, re.IGNORECASE)
        if not m_tot:
            m_tot = re.search(r'\bTotal\b\s*:?\s*([0-9]{1,3})\s*([0-9]{1,2})?\s*([0-9]{1,2})?', cleaned, re.IGNORECASE)
        if m_tot:
            try:
                tot_val = int(m_tot.group(1))
                c10_val = int(m_tot.group(2)) if m_tot.group(2) else 0
                c9_val = int(m_tot.group(3)) if m_tot.group(3) else 0
                totales_raw = {"total_puntos": tot_val, "cant_10s": c10_val, "cant_9s": c9_val}
            except ValueError:
                pass

        # 6. Tablas \begin{tabular} o Markdown
        series_extraidas = []
        cleaned_norm = content_text.replace("\x08", "\\b").replace("\\bend", "\\end")
        pat = re.escape(r'\begin{tabular}') + r'(.*?)' + re.escape(r'\end{tabular}')
        m_table = re.search(pat, cleaned_norm, re.DOTALL)
        if not m_table:
            m_table = re.search(pat, content_text, re.DOTALL)

        if m_table:
            table_body = m_table.group(1)
            table_body = re.sub(r'^\s*\{[^\}]*\}', '', table_body).strip()
            lines = re.split(r'\\\\|\n', table_body)
            for line in lines:
                line_str = line.strip()
                if not line_str or '18m' in line_str or 'Turno:' in line_str or 'Total' in line_str or 'Sum' in line_str or 'Suma' in line_str:
                    continue
                cells = [c.strip() for c in line_str.split('&')]
                cells = [re.sub(r'\\[a-zA-Z]+\\{.*?\}|\\[a-zA-Z]+|\{|\}|\*', '', c).strip() for c in cells]
                if cells:
                    cells[0] = re.sub(r'^[^\d]*', '', cells[0]).strip()
                if len(cells) >= 4 and cells[0].isdigit():
                    try:
                        s_num = int(cells[0])
                        max_s = 5 if tipo_juego == 'eliminatoria' else 10
                        if 1 <= s_num <= max_s:
                            flechas = []
                            for cell_val in cells[1:4]:
                                val_str = cell_val.strip().upper()
                                if val_str and val_str not in ['\\MBOX{}', 'MBOX', '{}']:
                                    flechas.append(val_str)
                            written_val = int(cells[4]) if len(cells) >= 5 and cells[4].isdigit() else 0
                            series_extraidas.append({
                                    "serie": s_num,
                                    "flechas": flechas,
                                    "suma_parcial_escrita": written_val
                                })
                    except ValueError:
                        continue

        if not series_extraidas:
            md_lines = cleaned.split('\n')
            for line in md_lines:
                if '|' in line:
                    parts = [p.strip() for p in line.split('|') if p.strip()]
                    if len(parts) >= 4 and parts[0].isdigit():
                        try:
                            s_num = int(parts[0])
                            max_s = 5 if tipo_juego == 'eliminatoria' else 10
                            if 1 <= s_num <= max_s:
                                flechas = []
                                for cell_val in parts[1:4]:
                                    val_str = cell_val.upper()
                                    if val_str in ['X', '10', '9', '8', '7', '6', '5', '4', '3', '2', '1', 'M']:
                                        flechas.append(val_str)
                                    elif val_str.isdigit():
                                        flechas.append(val_str)
                                written_val = int(parts[4]) if len(parts) >= 5 and parts[4].isdigit() else 0
                                series_extraidas.append({
                                        "serie": s_num,
                                        "flechas": flechas,
                                        "suma_parcial_escrita": written_val
                                    })
                        except ValueError:
                            pass

        has_points = (len(series_extraidas) > 0) or (totales_raw["total_puntos"] > 0)
        sin_puntos = not has_points

        obs = "Transcripción Exitosa" if not sin_puntos else "Sin Puntos Registrados"
        if sin_puntos and arquero_desconocido:
            obs = "Sin Puntos Registrados (⚠️ Arquero no reconocido - pendiente Agente 3)"
        elif not sin_puntos and len(series_extraidas) == 0:
            obs += f" (Total Leído: {totales_raw['total_puntos']} pts - Tabla de series omitida por Nemotron)"
        elif arquero_desconocido:
            obs += " (⚠️ Arquero no reconocido - pendiente Agente 3)"

        return {
            "valido": True,
            "arquero": arquero,
            "target": target,
            "club": club,
            "categoria": cat,
            "ronda": ronda,
            "distancia": distancia,
            "sin_puntos_registrados": sin_puntos,
            "observacion": obs,
            "series": series_extraidas,
            "totales_planilla": totales_raw,
            "texto_raw_ocr": content_text,
            "modelo_usado": "nvidia:nemotron-3.5-parse"
        }

    def __init__(self, api_key=None, output_dir=None, max_workers=4, http_timeout=120):
        self.api_key = api_key or _obtener_nvidia_api_key()
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="archery_agent2_")
        self.max_workers = max_workers
        self.http_timeout = http_timeout
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        env_ollama_host = os.environ.get("OLLAMA_HOST", "archery-ollama") if "archery-ollama" in os.environ.get("OLLAMA_URL", "") else os.environ.get("OLLAMA_HOST", "localhost")
        self.ollama_url = f"http://{env_ollama_host}:11434/v1/chat/completions"
        self.ollama_tags_url = os.environ.get("OLLAMA_URL", "").split("/v1")[0].rstrip("/") + "/api/tags" if os.environ.get("OLLAMA_URL") else f"http://{env_ollama_host}:11434/api/tags"
        self.nvidia_url = "https://integrate.api.nvidia.com/v1/chat/completions"

        self.ollama_modelos_disponibles = self._obtener_modelos_ollama_locales()
        self.model_chain = self._construir_cadena_modelos()
        self.rate_limiter = global_rate_limiter

    def _obtener_modelos_ollama_locales(self):
        try:
            r = requests.get(self.ollama_tags_url, timeout=1.5)
            if r.status_code == 200:
                models = [m.get("name", "").lower() for m in r.json().get("models", [])]
                print(f"[Agente 2] 🟢 Ollama detectado con modelos: {models}")
                return models
        except Exception:
            pass
        print("[Agente 2] 🟡 Ollama local no disponible o inaccesible.")
        return []

    def _construir_cadena_modelos(self):
        chain = []
        for m_name in ["qwen3-vl", "qwen2.5-vl", "qwen2-vl", "qwen2-vl:latest", "qwen2-vl:7b", "qwen2-vl:2b", "deepseek-ocr", "deepseek-ocr:latest", "llama3.2-vision"]:
            if any(m_name in m for m in self.ollama_modelos_disponibles):
                chain.append(("ollama", m_name))

        if self.api_key:
            chain.append(("nvidia_parse", "nvidia/nemotron-3.5-parse"))

        if not chain:
            print("[Agente 2] ⚠️ Sin API Key de NVIDIA NIM ni modelos visuales en Ollama. Fallback a Tesseract OCR.")
        return chain

    def _encode_image_b64(self, ruta_imagen):
        with open(ruta_imagen, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _calcular_totales_y_cotejar(self, datos, es_grilla_vacia=False):
        series = datos.get("series", [])
        
        total_puntos_calc = 0
        cant_10s_calc = 0
        cant_9s_calc = 0
        total_flechas_validas = 0
        series_limpias = []

        for s in series:
            flechas = s.get("flechas", [])
            suma_parcial = 0
            flechas_normalizadas = []

            for f in flechas:
                s_str = str(f).strip().upper()
                if s_str in ["X", "10"]:
                    flechas_normalizadas.append("X" if s_str == "X" else "10")
                    suma_parcial += 10
                    cant_10s_calc += 1
                    total_flechas_validas += 1
                elif s_str == "9":
                    flechas_normalizadas.append("9")
                    suma_parcial += 9
                    cant_9s_calc += 1
                    total_flechas_validas += 1
                elif s_str in ["M", "0", "MISS"]:
                    flechas_normalizadas.append("M")
                    suma_parcial += 0
                    total_flechas_validas += 1
                else:
                    if s_str not in ["", "NONE", "N/A", "NULL"]:
                        flechas_normalizadas.append(s_str)
                        try:
                            v = int(s_str)
                            if 0 <= v <= 10:
                                suma_parcial += v
                                total_flechas_validas += 1
                                if v == 10:
                                    cant_10s_calc += 1
                                elif v == 9:
                                    cant_9s_calc += 1
                        except ValueError:
                            pass

            s["flechas"] = flechas_normalizadas
            s["suma_parcial_calculada"] = suma_parcial
            total_puntos_calc += suma_parcial
            s["total_acumulado_calculado"] = total_puntos_calc
            
            written = s.get("suma_parcial", s.get("suma_parcial_escrita", 0))
            s["cotejo_serie_coincide"] = (written == suma_parcial)
            series_limpias.append(s)

        totales_escritos = datos.get("totales_planilla", {})
        written_total = totales_escritos.get("total_puntos", 0)
        written_sums = [s.get("suma_parcial", s.get("suma_parcial_escrita", 0)) for s in series]
        has_written_scores = any(w > 0 for w in written_sums)

        has_points = (total_flechas_validas > 0) or (total_puntos_calc > 0) or has_written_scores or (written_total > 0)

        if not has_points:
            sin_puntos = True
            series_limpias = []
            total_puntos_calc = 0
            cant_10s_calc = 0
            cant_9s_calc = 0
        else:
            sin_puntos = False

        datos["series"] = series_limpias
        datos["sin_puntos_registrados"] = sin_puntos
        
        if sin_puntos:
            datos["observacion"] = "Sin Puntos Registrados"
        else:
            if "Desconocido" in datos.get("arquero", ""):
                datos["observacion"] = "Transcripción Exitosa (⚠️ Arquero no reconocido - pendiente Agente 3)"
            elif len(series) == 0 and written_total > 0:
                datos["observacion"] = f"Transcripción Exitosa (Total Leído: {written_total} pts - Tabla de series omitida por Nemotron)"
            else:
                datos["observacion"] = "Transcripción Exitosa"

        datos["totales_planilla_calculados"] = {
            "total_puntos": total_puntos_calc if not sin_puntos else 0,
            "cant_10s": cant_10s_calc if not sin_puntos else 0,
            "cant_9s": cant_9s_calc if not sin_puntos else 0
        }
        
        if sin_puntos:
            datos["cotejo_total_coincide"] = True
        elif written_total > 0:
            datos["cotejo_total_coincide"] = (total_puntos_calc == written_total)
        else:
            datos["cotejo_total_coincide"] = True
            
        return datos

    def _refactorizar_nemotron_con_llm(self, content_text, tipo_juego="clasificacion", target_id_default="N/A"):
        if not self.api_key or not content_text:
            return None

        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        prompt_refactor = f"""
        Eres un estructurador JSON experto en Tiro con Arco (World Archery / FATARCO).
        Toma el siguiente texto crudo (LaTeX/Markdown) devuelto por Nemotron 3.5 Parse y conviértelo al formato JSON exacto necesario para el MVP:

        TEXTO CRUDO DE NEMOTRON:
        ```markdown
        {content_text}
        ```

        ESTRUCTURA JSON REQUERIDA:
        {{
          "valido": true,
          "arquero": "Nombre y Apellido leídos o Desconocido",
          "target": "{target_id_default}",
          "club": "Club o Siglas o N/A",
          "categoria": "Categoría o N/A",
          "ronda": "1",
          "distancia": "18m",
          "sin_puntos_registrados": false,
          "series": [
            {{
              "serie": 1,
              "flechas": ["X", "10", "9"],
              "suma_parcial_escrita": 29
            }}
          ],
          "totales_planilla": {{
            "total_puntos": 290,
            "cant_10s": 15,
            "cant_9s": 10
          }}
        }}

        Reglas:
        - Si tipo_juego es eliminatoria, extrae un máximo de 5 series. Si es clasificación, hasta 10 series.
        - Conserva las letras 'X' y 'M' (Miss, 0 pts) en flechas como strings en mayúsculas.
        - Devuelve ÚNICAMENTE el JSON entre llaves {{ ... }} sin explicaciones adicionales.
        """

        payload = {
            "model": "meta/llama-3.1-70b-instruct",
            "messages": [
                {"role": "user", "content": prompt_refactor}
            ],
            "temperature": 0.0,
            "max_tokens": 1500
        }

        try:
            self.rate_limiter.wait_if_needed()
            print(f"[Agente 2] 🧠 Ejecutando refactorización secundaria vía LLM NVIDIA NIM (llama-3.1-70b-instruct)...")
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(0))
                        parsed["modelo_usado"] = "nvidia:nemotron-3.5-parse + llm-refactorer:llama-3.1-70b"
                        parsed["texto_raw_ocr"] = content_text
                        print(f"[Agente 2] ✅ Refactorización LLM exitosa (Arquero: {parsed.get('arquero')})")
                        return self._calcular_totales_y_cotejar(parsed)
        except Exception as e:
            print(f"[Agente 2] ⚠️ Excepción en refactorización LLM: {e}")

        return None

    def _consultar_nemotron_parse(self, ruta_imagen, tipo_juego, es_grilla_vacia=False, target_id_default="N/A", ruta_fallback_procesada=None):
        if not self.api_key:
            return None

        url = "https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-parse/parse"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }

        filename = os.path.basename(ruta_imagen)
        mime_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"

        with open(ruta_imagen, "rb") as f_img:
            image_bytes = f_img.read()

        files_data = lambda: {
            "document": (filename, image_bytes, mime_type),
            "options": (None, json.dumps({"decoding": {"max_output_tokens": 4096}}), "application/json")
        }

        max_retries = 3
        for intento in range(1, max_retries + 1):
            try:
                self.rate_limiter.wait_if_needed()
                t0 = time.time()
                print(f"[Agente 2] 🚀 Consultando Nemotron 3.5 Parse via Retrieval API ({filename}) [Intento {intento}/{max_retries}]...")
                resp = requests.post(url, headers=headers, files=files_data(), timeout=self.http_timeout)
                elapsed = time.time() - t0

                if resp.status_code == 429:
                    wait_backoff = 4 * intento
                    print(f"[Agente 2] ⚠️ HTTP 429 Rate Limit alcanzado en NVIDIA NIM. Pausando {wait_backoff}s antes de reintentar ({intento}/{max_retries})...")
                    time.sleep(wait_backoff)
                    continue

                if resp.status_code == 200:
                    res_json = resp.json()
                    content_text = res_json.get("content", "")
                    if content_text and isinstance(content_text, str):

                        parsed_nemotron = self._parsear_salida_nemotron(content_text, target_id_default=target_id_default, tipo_juego=tipo_juego)
                        
                        if len(parsed_nemotron.get("series", [])) == 0 and ("\\begin{tabular}" in content_text or "|" in content_text):
                            parsed_llm = self._refactorizar_nemotron_con_llm(content_text, tipo_juego=tipo_juego, target_id_default=target_id_default)
                            if parsed_llm and len(parsed_llm.get("series", [])) > 0:
                                parsed_nemotron = parsed_llm

                        if parsed_nemotron.get("arquero") == "Desconocido":
                            cab_fallback = extraer_cabecera_tesseract(content_text, target_id_default=target_id_default)
                            if cab_fallback.get("arquero") != "Desconocido":
                                parsed_nemotron["arquero"] = cab_fallback["arquero"]
                            if cab_fallback.get("target") != "N/A" and parsed_nemotron.get("target") == "N/A":
                                parsed_nemotron["target"] = cab_fallback["target"]
                            if cab_fallback.get("club") != "N/A" and parsed_nemotron.get("club") == "N/A":
                                parsed_nemotron["club"] = cab_fallback["club"]

                        if parsed_nemotron.get("totales_planilla", {}).get("total_puntos", 0) > 0 and len(parsed_nemotron.get("series", [])) == 0:
                            ruta_proc = ruta_fallback_procesada or ruta_imagen
                            res_fallback = self._fallback_tesseract_ocr(ruta_proc, tipo_juego, es_grilla_vacia=False, target_id_default=target_id_default)
                            if res_fallback.get("series"):
                                parsed_nemotron["series"] = res_fallback["series"]
                                parsed_nemotron["observacion"] = f"Transcripción Híbrida (Nemotron Cabecera/Total + Tesseract Tabla: {len(res_fallback['series'])} series)"

                        parsed_nemotron["tiempo_inferencia_seg"] = round(elapsed, 2)
                        print(f"[Agente 2] ✅ Nemotron 3.5 Parse retornó texto en {round(elapsed, 2)}s (Arquero: {parsed_nemotron.get('arquero')})")
                        return self._calcular_totales_y_cotejar(parsed_nemotron, es_grilla_vacia=es_grilla_vacia)
                else:
                    print(f"[Agente 2] ⚠️ HTTP {resp.status_code} desde Nemotron Parse: {resp.text[:150]}")
            except Exception as e:
                print(f"[Agente 2] ⚠️ Excepción consultando Nemotron 3.5 Parse: {e}")

        return None

    def _consultar_vlm(self, ruta_imagen, tipo_juego, es_grilla_vacia=False, target_id_default="N/A", ruta_fallback_procesada=None):
        b64_img = self._encode_image_b64(ruta_imagen)

        prompt_clasificacion = """
        Eres un experto transcriptor de planillas de Tiro con Arco (World Archery / FATARCO).
        Analiza la imagen del cuadrante/planilla del arquero y extrae los datos en formato JSON exacto.

        REGLAS DE NEGOCIO Y DESCARTE DE HOJAS SIN TABLA:
        1. HOJA SIN TABLA O GRILLA EN BLANCO EN LA SECCIÓN DE TIROS:
           - Si el recorte es de una hoja informativa o la grilla de tiros está completamente vacía/sin números anotados:
           - DEBES responder obligatoriamente con:
             {
               "valido": true,
               "arquero": "Nombre y Apellido leídos o N/A",
               "target": "Número de Contención y Letra escritos ej 14C o N/A",
               "club": "Club o Siglas",
               "categoria": "Categoría",
               "sin_puntos_registrados": true,
               "observacion": "Sin Puntos Registrados",
               "series": [],
               "totales_planilla": {"total_puntos": 0, "cant_10s": 0, "cant_9s": 0}
             }
           - NUNCA inventes o alucines números para casillas vacías en blanco.

        2. PLANILLA CON PUNTOS ANOTADOS:
           - Si la planilla contiene puntajes o tiros anotados en las casillas, extrae los datos con la siguiente estructura:
             {
               "valido": true,
               "arquero": "Nombre y Apellido",
               "target": "Número de Contención y Letra escritos ej 14A, 3B, 25C",
               "club": "Siglas y Nombre del Club ej TCAP - Tiro con Arco Parana A.D.",
               "categoria": "Categoría escrita ej R M, C M, B M",
               "sin_puntos_registrados": false,
               "series": [
                 {
                   "serie": 1,
                   "flechas": ["X", "10", "9"],
                   "suma_parcial_escrita": 29,
                   "total_acumulado_escrito": 29
                 }
               ],
               "totales_planilla": {"total_puntos": 290, "cant_10s": 15, "cant_9s": 10}
             }

        REGLAS DE PRESERVACIÓN ESTRICTA DE LETRAS Y NÚMEROS:
        - LETRA 'X' (Centro del 10): DEBES incluir la letra "X" en la lista 'flechas'. NO la conviertas a 10 ni la omitas. Ej: ["X", "10", "9"].
        - LETRA 'M' (Miss / Tiro Fallado, 0 puntos): DEBES incluir la letra "M" en la lista 'flechas'. NO la conviertas a 0 ni a 9. Ej: ["9", "9", "M"].
        - FORMATO DE FLECHAS: Todos los elementos de 'flechas' DEBEN ser STRINGS en mayúsculas (ej: ["X", "10", "9"], ["9", "9", "M"]).
        - NÚMERO DE CONTENCIÓN Y LETRA (TARGET): Extrae el número de contención real y letra escritos en el blanco (ej: "14A", "3B", "25C").
        - CATEGORÍA Y CLUB: 'categoria' (ej: "R M", "C M"), 'club' (ej: "TCAP").
        - Si la planilla no pertenece a un arquero o no es válida, responde: {"valido": false}

        Devuelve ÚNICAMENTE el JSON sin formato Markdown ni explicaciones.
        """

        img_prefix = "data:image/png;base64,"

        for provider, model_name in self.model_chain:
            if provider == "nvidia_parse" or "nemotron-3.5-parse" in model_name:
                res_parse = self._consultar_nemotron_parse(ruta_imagen, tipo_juego, es_grilla_vacia=es_grilla_vacia, target_id_default=target_id_default, ruta_fallback_procesada=ruta_fallback_procesada)
                if res_parse and res_parse.get("valido", True):
                    return res_parse
                continue
            try:
                t0 = time.time()
                if provider == "ollama":
                    url = self.ollama_url
                    headers = {"Content-Type": "application/json"}
                else:
                    if not self.api_key:
                        continue
                    url = self.nvidia_url
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }

                payload = {
                    "model": model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_clasificacion},
                                {"type": "image_url", "image_url": {"url": img_prefix + b64_img}}
                            ]
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024
                }

                print(f"[Agente 2] 🚀 Consultando {provider} ({model_name})...")
                resp = requests.post(url, headers=headers, json=payload, timeout=self.http_timeout)
                elapsed = time.time() - t0
                
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content")
                        if content and isinstance(content, str):
                            match = re.search(r'\{.*\}', content, re.DOTALL)
                            if match:
                                parsed = json.loads(match.group(0))
                                parsed["modelo_usado"] = f"{provider}:{model_name}"
                                parsed["tiempo_inferencia_seg"] = round(elapsed, 2)
                                print(f"[Agente 2] ✅ Éxito con {model_name} en {round(elapsed, 2)}s")
                                return self._calcular_totales_y_cotejar(parsed, es_grilla_vacia=es_grilla_vacia)
                else:
                    print(f"[Agente 2] ⚠️ HTTP {resp.status_code} desde {provider} ({model_name}) en {round(elapsed, 2)}s")
            except requests.exceptions.Timeout:
                print(f"[Agente 2] ⏱️ Timeout ({self.http_timeout}s alcanzado) para {provider} ({model_name})")
                continue
            except Exception as e:
                print(f"[Agente 2] ⚠️ Excepción con {model_name}: {e}")
                continue

        return None

    def _fallback_tesseract_ocr(self, ruta_imagen, tipo_juego, es_grilla_vacia=False, target_id_default="N/A"):
        if not OCR_SUPPORT or not os.path.exists(ruta_imagen) or es_grilla_vacia:
            return {
                "valido": True,
                "arquero": "Arquero Detectado",
                "target": target_id_default,
                "club": "Detectado por OCR Local",
                "categoria": "N/A",
                "sin_puntos_registrados": True,
                "observacion": "Sin Puntos Registrados",
                "series": [],
                "totales_planilla": {"total_puntos": 0, "cant_10s": 0, "cant_9s": 0},
                "texto_raw_ocr": "",
                "modelo_usado": "Tesseract-OCR-Local (Fallback)"
            }

        img_pil = Image.open(ruta_imagen)
        text_raw = pytesseract.image_to_string(img_pil, lang="spa+eng")
        cabecera = extraer_cabecera_tesseract(text_raw, target_id_default=target_id_default)

        series_extraidas = []
        lines = text_raw.split("\n")
        s_num = 1
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            tokens = re.findall(r'\b(X|10|[0-9]|M|MISS)\b', line_str, re.IGNORECASE)
            if len(tokens) >= 3:
                flechas = []
                for t in tokens[:3]:
                    t_up = t.upper()
                    if t_up in ["MISS", "0"]:
                        flechas.append("M")
                    else:
                        flechas.append(t_up)
                
                written_val = None
                if len(tokens) >= 4:
                    try:
                        written_val = int(tokens[3])
                    except ValueError:
                        pass
                series_extraidas.append({
                    "serie": s_num,
                    "flechas": flechas,
                    "suma_parcial_escrita": written_val if written_val is not None else 0
                })
                s_num += 1
                if s_num > 10:
                    break

        res = {
            "valido": True,
            "arquero": cabecera.get("arquero", "Arquero Detectado"),
            "target": cabecera.get("target", target_id_default),
            "club": cabecera.get("club", "OCR Local Tesseract"),
            "categoria": cabecera.get("categoria", "N/A"),
            "series": series_extraidas,
            "totales_planilla": {"total_puntos": 0, "cant_10s": 0, "cant_9s": 0},
            "texto_raw_ocr": text_raw,
            "modelo_usado": "Tesseract-OCR-Local (Fallback Parser)"
        }
        return self._calcular_totales_y_cotejar(res, es_grilla_vacia=es_grilla_vacia)

    def _procesar_tarea_individual(self, tarea):
        layout = tarea.get("layout", "")
        tipo_juego = tarea.get("tipo_juego", "")
        ruta_recorte = tarea.get("ruta_recorte", "")
        target_id_default = str(tarea.get("target_id", "N/A"))

        # Si Agente 1 marcó la hoja completa como información o portada, se omite OCR
        if layout in ["portada"] or tipo_juego in ["sin_modo", "info", "informacion", "eliminatoria"] or tarea.get("es_pagina_informacion", False):
            print(f"[Agente 2] ⏭️ Omitiendo OCR para {tarea.get('label', target_id_default)} (Hoja de Información / Portada)")
            is_elim = (tipo_juego == "eliminatoria")
            return {
                "pagina": tarea.get("pagina"),
                "target_id": tarea.get("target_id"),
                "tipo_juego": "eliminatoria" if is_elim else "informacion",
                "layout": layout,
                "ruta_recorte_original": ruta_recorte,
                "ruta_recorte_procesada": ruta_recorte,
                "transcripcion": {
                    "valido": True,
                    "arquero": "N/A (Eliminatoria - Fuera de Alcance)" if is_elim else "N/A (Hoja Informativa)",
                    "target": target_id_default,
                    "club": "N/A",
                    "categoria": "N/A",
                    "sin_puntos_registrados": True,
                    "observacion": "Planilla de Eliminatoria (Fuera de Alcance para Ranking)" if is_elim else "Hoja de Información / Portada (Descartada)",
                    "series": [],
                    "totales_planilla": {"total_puntos": 0, "cant_10s": 0, "cant_9s": 0},
                    "texto_raw_ocr": "(Omitido por Planilla de Eliminatoria)" if is_elim else "(Omitido por Hoja de Información / Portada)",
                    "modelo_usado": "Descartado (Sin OCR)",
                    "tipo_juego": "eliminatoria" if is_elim else "informacion"
                }
            }

        ruta_original_resized = ImageEnhancer.redimensionar_suave(ruta_recorte, output_dir=self.output_dir, max_dim=1280)
        ruta_procesada = ImageEnhancer.mejorar_imagen(ruta_recorte, output_dir=self.output_dir, max_dim=1280)
        es_grilla_vacia = tarea.get("es_cuadrante_vacio", False) or ImageEnhancer.detectar_tabla_vacia(ruta_procesada)

        resultado_ocr = self._consultar_vlm(
            ruta_imagen=ruta_original_resized, 
            tipo_juego=tipo_juego, 
            es_grilla_vacia=es_grilla_vacia, 
            target_id_default=target_id_default,
            ruta_fallback_procesada=ruta_procesada
        )

        if not resultado_ocr or not resultado_ocr.get("valido", True):
            resultado_ocr = self._fallback_tesseract_ocr(ruta_procesada, tipo_juego, es_grilla_vacia=es_grilla_vacia, target_id_default=target_id_default)

        # Mantiene tipo_juego inmutable recibido desde Agente 1 (clasificacion o eliminatoria)
        resultado_ocr["tipo_juego"] = tipo_juego

        return {
            "pagina": tarea.get("pagina"),
            "target_id": tarea.get("target_id"),
            "tipo_juego": tipo_juego,
            "layout": layout,
            "ruta_recorte_original": ruta_recorte,
            "ruta_recorte_procesada": ruta_procesada,
            "transcripcion": resultado_ocr
        }

    def procesar_manifiesto_agente1(self, manifiesto_agente1):
        tareas = manifiesto_agente1.get("tareas_agente2", [])
        
        manifiesto_agente2 = {
            "archivo_origen": manifiesto_agente1.get("archivo_origen", ""),
            "total_tareas_recibidas": len(tareas),
            "transcripciones": []
        }

        tareas_a_procesar = [t for t in tareas if not t.get("es_pagina_informacion") and t.get("tipo_juego") not in ["info", "informacion", "portada", "eliminatoria"]]
        tareas_omitidas = [t for t in tareas if t not in tareas_a_procesar]

        for t in tareas_omitidas:
            res_om = self._procesar_tarea_individual(t)
            if res_om:
                manifiesto_agente2["transcripciones"].append(res_om)

        print(f"[Agente 2] 👁️ Procesando OCR para {len(tareas_a_procesar)} recorte(s) de planillas ({len(tareas_omitidas)} hojas de información/portadas omitidas)...")

        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(tareas_a_procesar) if tareas_a_procesar else 1))) as executor:
            future_to_tarea = {
                executor.submit(self._procesar_tarea_individual, t): t for t in tareas_a_procesar
            }
            for future in as_completed(future_to_tarea):
                res = future.result()
                if res is not None:
                    manifiesto_agente2["transcripciones"].append(res)

        manifiesto_agente2["transcripciones"].sort(key=lambda x: (x.get("pagina", 1), str(x.get("target_id", ""))))
        return self._generar_archivo_auditoria(manifiesto_agente2)

    def reintentar_tareas_especificas(self, manifiesto_agente1, manifiesto_agente2_previo, identificadores_a_reintentar):
        if not identificadores_a_reintentar:
            return manifiesto_agente2_previo

        tareas_todas = manifiesto_agente1.get("tareas_agente2", [])
        tareas_filtradas = []

        for t in tareas_todas:
            pag = str(t.get('pagina'))
            target_pos = str(t.get('target_id'))
            lbl = str(t.get('label', ''))

            match = False
            for sel in identificadores_a_reintentar:
                sel_str = str(sel)
                # Coincidencia exacta o parcial de etiqueta de recorte
                if lbl and (lbl == sel_str or lbl in sel_str or sel_str in lbl):
                    match = True
                    break
                # Coincidencia flexible por número de página y diana/posición
                if f"Pág {pag}" in sel_str or f"Página {pag}" in sel_str:
                    if target_pos in sel_str or f"Pos {target_pos}" in sel_str or f"Posición {target_pos}" in sel_str or target_pos == "Portada":
                        match = True
                        break

            if match:
                t_copy = dict(t)
                t_copy["es_pagina_informacion"] = False
                if t_copy.get("tipo_juego") == "informacion":
                    t_copy["tipo_juego"] = "clasificacion"
                tareas_filtradas.append(t_copy)

        if not tareas_filtradas:
            print(f"[Agente 2] ⚠️ No se encontraron tareas coincidentes para los identificadores: {identificadores_a_reintentar}")
            return manifiesto_agente2_previo

        print(f"[Agente 2] 🔄 Ejecutando OCR exclusivamente para {len(tareas_filtradas)} diana(s) seleccionada(s): {[t.get('label') for t in tareas_filtradas]}")

        nuevos_resultados = {}
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(tareas_filtradas)))) as executor:
            future_to_tarea = {
                executor.submit(self._procesar_tarea_individual, t): t for t in tareas_filtradas
            }
            for future in as_completed(future_to_tarea):
                res = future.result()
                if res is not None:
                    key = f"Pág {res.get('pagina')}_{res.get('target_id')}"
                    nuevos_resultados[key] = res

        transcripciones_map = {}
        prev = manifiesto_agente2_previo.get("transcripciones", []) if isinstance(manifiesto_agente2_previo, dict) else []
        for t in prev:
            key = f"Pág {t.get('pagina')}_{t.get('target_id')}"
            transcripciones_map[key] = t

        for key, res in nuevos_resultados.items():
            transcripciones_map[key] = res

        transcripciones_actualizadas = list(transcripciones_map.values())
        transcripciones_actualizadas.sort(key=lambda x: (x.get("pagina", 1), str(x.get("target_id", ""))))
        
        if not isinstance(manifiesto_agente2_previo, dict):
            manifiesto_agente2_previo = {}
        manifiesto_agente2_previo["transcripciones"] = transcripciones_actualizadas
        return self._generar_archivo_auditoria(manifiesto_agente2_previo)
