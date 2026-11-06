#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Agente 2 (v19): Extractor OCR Multimodal y Reintento Selectivo Multi-Página.

Novedades v17:
1. Sincronización con Agente 1 (v9): Maneja posiciones espaciales 'A', 'B', 'C', 'D' por página y extrae el número de contención/diana real (ej: 14A, 3B, 25C) desde el encabezado leído por OCR.
2. Reintento selectivo por página y posición espacial (ej: Pág 1 - A, Pág 2 - C).
3. Preservación estricta de letras 'X' (10 inner), 'M' (Miss/0 pts), Target (número+letra), Categoría y Club.
4. Fast Healthcheck de Ollama + Fallback a NVIDIA NIM / Tesseract.
5. Triangulación y cotejo aritmético automático (flechas vs sumas parciales y totales acumulados).
"""

import os
import re
import json
import base64
import tempfile
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import numpy as np
import cv2

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


class ImageEnhancer:
    """
    Pipeline de Preprocesamiento Digital de Imagen (PDI) adaptativo.
    """
    @staticmethod
    def mejorar_imagen(ruta_imagen, output_dir=None):
        if not os.path.exists(ruta_imagen):
            return ruta_imagen

        img_pil = Image.open(ruta_imagen)
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


class Agente2OCRExtractor:
    """
    Agente 2 (v17): Extractor OCR con Reintento Selectivo y Desacoplamiento Página/Contención
    """
    def __init__(self, api_key=None, output_dir=None, max_workers=4):
        self.api_key = api_key or _obtener_nvidia_api_key()
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="archery_agent2_")
        self.max_workers = max_workers
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        self.ollama_url = "http://localhost:11434/v1/chat/completions"
        self.nvidia_url = "https://integrate.api.nvidia.com/v1/chat/completions"

        self.ollama_activo = self._verificar_ollama_local()
        self.model_chain = self._construir_cadena_modelos()

    def _verificar_ollama_local(self):
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=1.0)
            if r.status_code == 200:
                print("[Agente 2] 🟢 Servicio Ollama local detectado y activo.")
                return True
        except Exception:
            pass
        print("[Agente 2] 🟡 Ollama local no disponible. Se omiten consultas a localhost.")
        return False

    def _construir_cadena_modelos(self):
        chain = []
        if self.ollama_activo:
            chain.append(("ollama", "deepseek-ocr"))
        if self.api_key:
            chain.append(("nvidia", "nvidia/nemotron-3.5-parse"))
            chain.append(("nvidia", "meta/llama-3.2-90b-vision-instruct"))
            chain.append(("nvidia", "meta/llama-3.2-11b-vision-instruct"))
            chain.append(("nvidia", "nvidia/nemotron-3.5-super-vl-120b-a12b"))
        if not chain:
            print("[Agente 2] ⚠️ Sin API Key de NVIDIA NIM ni Ollama activo. Fallback a Tesseract OCR.")
        return chain

    def _encode_image_b64(self, ruta_imagen):
        with open(ruta_imagen, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _calcular_totales_y_cotejar(self, datos):
        series = datos.get("series", [])
        sin_puntos = datos.get("sin_puntos_registrados", False)
        if datos.get("observacion") == "Sin Puntos Registrados":
            sin_puntos = True

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

        if total_flechas_validas == 0 or sin_puntos:
            sin_puntos = True
            series_limpias = []
            total_puntos_calc = 0
            cant_10s_calc = 0
            cant_9s_calc = 0

        datos["series"] = series_limpias
        datos["sin_puntos_registrados"] = sin_puntos
        if sin_puntos:
            datos["observacion"] = "Sin Puntos Registrados"

        totales_escritos = datos.get("totales_planilla", {})
        written_total = totales_escritos.get("total_puntos", 0)

        datos["totales_planilla_calculados"] = {
            "total_puntos": total_puntos_calc if not sin_puntos else 0,
            "cant_10s": cant_10s_calc if not sin_puntos else 0,
            "cant_9s": cant_9s_calc if not sin_puntos else 0
        }
        datos["cotejo_total_coincide"] = (written_total == total_puntos_calc) if (written_total > 0 and not sin_puntos) else True
        return datos

    def _consultar_vlm(self, ruta_imagen, tipo_juego):
        b64_img = self._encode_image_b64(ruta_imagen)

        prompt_clasificacion = """
        Eres un experto transcriptor de planillas de Tiro con Arco (World Archery / FATARCO).
        Analiza la imagen de la planilla del arquero y extrae los datos en formato JSON exacto.

        REGLAS CRÍTICAS DE EVALUACIÓN:
        1. HOJA DE ARQUERO SIN PUNTOS ANOTADOS (HOJA DE PLANILLA EN BLANCO EN LA TABLA DE TIROS):
           - Si la planilla contiene Nombre/Datos del arquero pero las casillas de tiros o series están vacías, en blanco o sin números manuscritos:
           - DEBES responder obligatoriamente con:
             {
               "valido": true,
               "arquero": "Nombre y Apellido leídos",
               "target": "Número de Contención y Letra escritos ej 14C",
               "club": "Club o Siglas",
               "categoria": "Categoría",
               "sin_puntos_registrados": true,
               "observacion": "Sin Puntos Registrados",
               "series": [],
               "totales_planilla": {"total_puntos": 0, "cant_10s": 0, "cant_9s": 0}
             }
           - NUNCA alucines o inventes números para casillas vacías en blanco.

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
            try:
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
                resp = requests.post(url, headers=headers, json=payload, timeout=90)
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
                                return self._calcular_totales_y_cotejar(parsed)
            except Exception as e:
                print(f"[Agente 2] ⚠️ Excepción con {model_name}: {e}")
                continue

        return None

    def _fallback_tesseract_ocr(self, ruta_imagen, tipo_juego):
        if not OCR_SUPPORT or not os.path.exists(ruta_imagen):
            return {
                "valido": True,
                "arquero": "Desconocido (OCR Offline)",
                "target": "N/A",
                "club": "Detectado por OCR Local",
                "categoria": "N/A",
                "series": [],
                "totales_planilla": {"total_puntos": 0, "cant_10s": 0, "cant_9s": 0},
                "texto_raw_ocr": "",
                "modelo_usado": "Tesseract-OCR-Local (Fallback)"
            }

        img_pil = Image.open(ruta_imagen)
        text_raw = pytesseract.image_to_string(img_pil, lang="spa+eng")

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
            "arquero": "Arquero Detectado (Fallback OCR)",
            "target": "N/A",
            "club": "OCR Local Tesseract",
            "categoria": "N/A",
            "series": series_extraidas,
            "totales_planilla": {"total_puntos": 0, "cant_10s": 0, "cant_9s": 0},
            "texto_raw_ocr": text_raw,
            "modelo_usado": "Tesseract-OCR-Local (Fallback Parser)"
        }
        return self._calcular_totales_y_cotejar(res)

    def _procesar_tarea_individual(self, tarea):
        layout = tarea.get("layout", "")
        tipo_juego = tarea.get("tipo_juego", "")
        ruta_recorte = tarea.get("ruta_recorte", "")

        if layout == "portada" or tipo_juego == "sin_modo":
            return None

        ruta_procesada = ImageEnhancer.mejorar_imagen(ruta_recorte, output_dir=self.output_dir)

        resultado_ocr = self._consultar_vlm(ruta_procesada, tipo_juego)
        if not resultado_ocr or not resultado_ocr.get("valido", True):
            resultado_ocr = self._fallback_tesseract_ocr(ruta_procesada, tipo_juego)

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

        print(f"[Agente 2] 👁️ Procesando OCR en paralelo para {len(tareas)} recorte(s) de diana...")

        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(tareas)))) as executor:
            future_to_tarea = {
                executor.submit(self._procesar_tarea_individual, t): t for t in tareas
            }
            for future in as_completed(future_to_tarea):
                res = future.result()
                if res is not None:
                    manifiesto_agente2["transcripciones"].append(res)

        manifiesto_agente2["transcripciones"].sort(key=lambda x: (x.get("pagina", 1), str(x.get("target_id", ""))))
        return manifiesto_agente2

    def reintentar_tareas_especificas(self, manifiesto_agente1, manifiesto_agente2_previo, identificadores_a_reintentar):
        if not identificadores_a_reintentar:
            return manifiesto_agente2_previo

        tareas_todas = manifiesto_agente1.get("tareas_agente2", [])
        tareas_filtradas = []

        for t in tareas_todas:
            pag = str(t.get('pagina'))
            target_pos = str(t.get('target_id'))
            key_full = f"Pág {pag} - Posición {target_pos}"
            key_short = f"Pág {pag} - {target_pos}"
            
            match = False
            for sel in identificadores_a_reintentar:
                if sel.startswith(key_full) or sel.startswith(key_short) or key_full in sel or key_short in sel:
                    match = True
                    break

            if match:
                tareas_filtradas.append(t)

        if not tareas_filtradas:
            return manifiesto_agente2_previo

        print(f"[Agente 2] 🔄 Reintentando OCR para {len(tareas_filtradas)} diana(s) seleccionada(s)...")

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

        transcripciones_actualizadas = []
        for t in manifiesto_agente2_previo.get("transcripciones", []):
            key = f"Pág {t.get('pagina')}_{t.get('target_id')}"

            if key in nuevos_resultados:
                transcripciones_actualizadas.append(nuevos_resultados[key])
            else:
                transcripciones_actualizadas.append(t)

        manifiesto_agente2_previo["transcripciones"] = transcripciones_actualizadas
        manifiesto_agente2_previo["transcripciones"].sort(key=lambda x: (x.get("pagina", 1), str(x.get("target_id", ""))))
        return manifiesto_agente2_previo
