#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Agente 2: Preprocesador de Imagen y Extractor OCR Multimodal (NVIDIA NIM & OpenCV).

Responsabilidades:
1. Recibir el manifiesto JSON generado por el Agente 1 (tareas_agente2).
2. Omitir páginas clasificadas como 'portada' / 'sin_modo'.
3. Aplicar preprocesamiento digital de imagen (CLAHE, Denoising, Deskew, Binarización) con OpenCV/Pillow.
4. Consultar modelos multimodales de NVIDIA NIM (con cadena de fallback masiva de 6 niveles).
5. Extraer metadatos (Arquero, Club/Siglas, Categoría, Diana/Puesto), 10 series de flechas, sumas parciales escritas y calculadas, 10s, 9s y Xs.
6. Manejo especial de tiros: 'X' (10 puntos, centro del 10) y 'M' (0 puntos, Miss/Fallo).
7. Triangulación y cotejo aritmético automático por serie y total general.
"""

import os
import re
import json
import base64
import tempfile
import requests
from PIL import Image
import numpy as np
import cv2

try:
    import pytesseract
    OCR_SUPPORT = True
except ImportError:
    OCR_SUPPORT = False


def _obtener_nvidia_api_key():
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if key:
        return key
    curr_dir = os.getcwd()
    for _ in range(5):
        env_path = os.path.join(curr_dir, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == "NVIDIA_API_KEY":
                            val = v.strip().strip('"').strip("'")
                            os.environ["NVIDIA_API_KEY"] = val
                            return val
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent
    return ""


class ImageEnhancer:
    @staticmethod
    def mejorar_imagen(ruta_imagen, output_dir=None):
        if not os.path.exists(ruta_imagen):
            return ruta_imagen

        img_pil = Image.open(ruta_imagen)
        img_np = np.array(img_pil.convert('RGB'))
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced_gray = clahe.apply(gray)
        denoised = cv2.bilateralFilter(enhanced_gray, d=7, sigmaColor=50, sigmaSpace=50)

        coords = np.column_stack(np.where(denoised < 180))
        angle = 0.0
        if len(coords) > 50:
            rect = cv2.minAreaRect(coords)
            angle = rect[-1]
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle

        (h, w) = denoised.shape
        if abs(angle) > 0.5 and abs(angle) < 15.0:
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            rotated = cv2.warpAffine(denoised, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        else:
            rotated = denoised

        kernel_sharpen = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(rotated, -1, kernel_sharpen)

        result_rgb = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2RGB)
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
    def __init__(self, api_key=None, output_dir=None):
        self.api_key = api_key or _obtener_nvidia_api_key()
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="archery_agent2_")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        self.model_chain = [
            "nvidia/nemotron-3.5-parse",
            "meta/llama-3.2-90b-vision-instruct",
            "meta/llama-3.2-11b-vision-instruct",
            "nvidia/nemotron-3.5-super-vl-120b-a12b",
            "mistralai/mistral-large-4-1t-a52b",
            "minimaxai/minimax-m3.1-flash"
        ]

    def _encode_image_b64(self, ruta_imagen):
        with open(ruta_imagen, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _consultar_nvidia_nim(self, ruta_imagen, tipo_juego):
        if not self.api_key:
            print("[Agente 2] ⚠️ NVIDIA_API_KEY no detectada. Usando fallback de OCR Local.")
            return None

        b64_img = self._encode_image_b64(ruta_imagen)

        prompt_clasificacion = """
        Eres un experto transcriptor de planillas de Tiro con Arco (FATARCO / World Archery).
        Analiza el recorte de la planilla de CLASIFICACIÓN y extrae todos los datos en este formato JSON exacto:
        {
          "valido": true,
          "arquero": "Nombre y Apellido completo",
          "target": "Número y Letra de diana ej 1A, 1B",
          "club": "Sigla y Nombre del Club ej TCAP - Tiro con Arco Paraná A.D.",
          "categoria": "Categoría exacta escrita en el recuadro ej R M, C M, B M, Recurvo Senior",
          "series": [
            {
              "serie": 1,
              "flechas": ["X", 10, 9],
              "suma_parcial_escrita": 29,
              "total_acumulado_escrito": 29
            }
          ],
          "totales_planilla_escritos": {
            "total_puntos": 540,
            "cant_10s": 12,
            "cant_9s": 18
          }
        }
        REGLAS CRÍTICAS DE TRANSCRIPCIÓN:
        1. Las flechas válidas son números (1 al 10), la letra 'X' (centro del 10, vale 10 puntos) y la letra 'M' (Miss/Fallo, vale 0 puntos).
        2. NO confundir jamás la letra 'M' con un '9'. Si la planilla indica 'M', escribe "M".
        3. NO confundir la letra 'X' con un número inválido. La 'X' ES TOTALMENTE VÁLIDA y representa un 10. Consérvala como "X".
        4. Extrae la suma parcial y total acumulado tal cual están escritos en el papel por el planillero.
        5. Devuelve ÚNICAMENTE el JSON estricto.
        """

        prompt_eliminatoria = """
        Eres un experto transcriptor de planillas de Tiro con Arco.
        Analiza el recorte de la planilla de ELIMINATORIA (Duelo de Sets) y extrae todos los datos en este JSON exacto:
        {
          "valido": true,
          "arquero": "Nombre y Apellido",
          "posicion": "Posición en la llave ej Posición 1",
          "club": "Sigla y Nombre del Club",
          "categoria": "Categoría ej R M, B M",
          "sets": [
            {"set": 1, "flechas": ["X", 9, "M"], "puntos_set_escritos": 2}
          ],
          "total_set_points_escritos": 6,
          "ganador": true
        }
        REGLAS:
        1. Preservar 'X' (vale 10 puntos) y 'M' (vale 0 puntos) como cadenas.
        2. Devuelve ÚNICAMENTE el JSON estricto.
        """

        prompt = prompt_eliminatoria if tipo_juego == "eliminatoria" else prompt_clasificacion
        img_prefix = "data:image/png;base64,"
        url = "https://integrate.api.nvidia.com/v1/chat/completions"

        for model in self.model_chain:
            try:
                print(f"[Agente 2] 🚀 Consultando modelo NVIDIA NIM: {model}...")
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": img_prefix + b64_img}}
                            ]
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024
                }

                resp = requests.post(url, headers=headers, json=payload, timeout=90)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(0))
                        parsed["modelo_usado"] = model
                        print(f"[Agente 2] ✅ Respuesta exitosa de {model}")
                        return parsed
                else:
                    print(f"[Agente 2] ⚠️ Modelo {model} respondió con HTTP {resp.status_code}")
            except Exception as e:
                print(f"[Agente 2] ⚠️ Excepción al consultar {model}: {e}")
                continue

        print("[Agente 2] ❌ Ningún modelo de NVIDIA NIM respondió con éxito. Recurriendo a OCR Local.")
        return None

    def _calcular_totales_y_cotejar(self, resultado):
        """
        Calcula matemáticamente los totales reales (donde X=10 y M=0)
        y los coteja contra los valores escritos en la planilla.
        """
        if not resultado or not resultado.get("valido", True):
            return resultado

        series = resultado.get("series", [])
        total_puntos_calc = 0
        cant_10s_calc = 0
        cant_9s_calc = 0

        for s in series:
            flechas = s.get("flechas", [])
            suma_parcial_calc = 0
            for f in flechas:
                f_str = str(f).strip().upper()
                if f_str == "X":
                    suma_parcial_calc += 10
                    cant_10s_calc += 1
                elif f_str == "M":
                    suma_parcial_calc += 0
                elif f_str == "10":
                    suma_parcial_calc += 10
                    cant_10s_calc += 1
                elif f_str == "9":
                    suma_parcial_calc += 9
                    cant_9s_calc += 1
                elif f_str.isdigit():
                    val = int(f_str)
                    suma_parcial_calc += val
                    if val == 10:
                        cant_10s_calc += 1
                    elif val == 9:
                        cant_9s_calc += 1

            total_puntos_calc += suma_parcial_calc
            s["suma_parcial_calculada"] = suma_parcial_calc
            s["total_acumulado_calculado"] = total_puntos_calc

            escrita = s.get("suma_parcial_escrita")
            if escrita is not None:
                try:
                    s["cotejo_serie_coincide"] = (int(escrita) == suma_parcial_calc)
                except ValueError:
                    s["cotejo_serie_coincide"] = False
            else:
                s["cotejo_serie_coincide"] = True

        resultado["totales_planilla_calculados"] = {
            "total_puntos": total_puntos_calc,
            "cant_10s": cant_10s_calc,
            "cant_9s": cant_9s_calc
        }

        escrito_total = resultado.get("totales_planilla_escritos", {}).get("total_puntos")
        if escrito_total is not None:
            try:
                resultado["cotejo_total_coincide"] = (int(escrito_total) == total_puntos_calc)
            except ValueError:
                resultado["cotejo_total_coincide"] = False
        else:
            resultado["cotejo_total_coincide"] = True

        return resultado

    def _fallback_tesseract_ocr(self, ruta_imagen, tipo_juego):
        if not OCR_SUPPORT or not os.path.exists(ruta_imagen):
            res = {
                "valido": True,
                "arquero": "Desconocido (OCR Offline)",
                "target": "N/A",
                "club": "Detectado por OCR Local",
                "categoria": "N/A",
                "series": [],
                "totales_planilla_escritos": {"total_puntos": 0, "cant_10s": 0, "cant_9s": 0},
                "texto_raw_ocr": "",
                "modelo_usado": "Tesseract-OCR-Local (Fallback)"
            }
            return self._calcular_totales_y_cotejar(res)

        img_pil = Image.open(ruta_imagen)
        text_raw = pytesseract.image_to_string(img_pil, lang="spa+eng")

        numeros = re.findall(r'\d+', text_raw)
        dianas = re.findall(r'\d+[A-Da-d]', text_raw)
        lineas = [l.strip() for l in text_raw.splitlines() if len(l.strip()) > 3]

        nombre = lineas[0] if lineas else "Arquero Detectado"
        target_str = dianas[0].upper() if dianas else "N/A"

        res = {
            "valido": True,
            "arquero": nombre,
            "target": target_str,
            "club": "Detectado por OCR Local",
            "categoria": "N/A",
            "series": [
                {
                    "serie": i + 1,
                    "flechas": [int(n) for n in numeros[i*3:(i+1)*3]],
                    "suma_parcial_escrita": sum([int(n) for n in numeros[i*3:(i+1)*3]]) if len(numeros[i*3:(i+1)*3]) == 3 else 0,
                    "total_acumulado_escrito": 0
                }
                for i in range(min(10, len(numeros) // 3))
            ],
            "totales_planilla_escritos": {
                "total_puntos": sum([int(n) for n in numeros if int(n) <= 10]) if numeros else 0,
                "cant_10s": text_raw.lower().count("10") + text_raw.upper().count("X"),
                "cant_9s": text_raw.lower().count("9")
            },
            "texto_raw_ocr": text_raw,
            "modelo_usado": "Tesseract-OCR-Local (Fallback)"
        }
        return self._calcular_totales_y_cotejar(res)

    def procesar_manifiesto_agente1(self, manifiesto_agente1):
        tareas = manifiesto_agente1.get("tareas_agente2", [])

        manifiesto_agente2 = {
            "archivo_origen": manifiesto_agente1.get("archivo_origen", ""),
            "total_tareas_recibidas": len(tareas),
            "transcripciones": []
        }

        for tarea in tareas:
            layout = tarea.get("layout", "")
            tipo_juego = tarea.get("tipo_juego", "")
            ruta_recorte = tarea.get("ruta_recorte", "")

            if layout == "portada" or tipo_juego == "sin_modo":
                continue

            ruta_procesada = ImageEnhancer.mejorar_imagen(ruta_recorte, output_dir=self.output_dir)

            resultado_ocr = self._consultar_nvidia_nim(ruta_procesada, tipo_juego)
            if not resultado_ocr or not resultado_ocr.get("valido", True):
                resultado_ocr = self._fallback_tesseract_ocr(ruta_procesada, tipo_juego)
            else:
                resultado_ocr = self._calcular_totales_y_cotejar(resultado_ocr)

            item_transcripcion = {
                "pagina": tarea.get("pagina"),
                "target_id": tarea.get("target_id"),
                "tipo_juego": tipo_juego,
                "layout": layout,
                "ruta_recorte_original": ruta_recorte,
                "ruta_recorte_procesada": ruta_procesada,
                "transcripcion": resultado_ocr
            }

            manifiesto_agente2["transcripciones"].append(item_transcripcion)

        return manifiesto_agente2
