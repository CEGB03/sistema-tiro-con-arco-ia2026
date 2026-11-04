#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Agente 2: Preprocesador de Imagen y Extractor OCR Multimodal / Document Parser (NVIDIA NIM).

Versión v6:
- Soporte optimizado para 'nvidia/nemotron-3.5-parse' y modelos multimodales de visión.
- Pipeline de PDI (CLAHE, Bilateral Filter, Deskew, Sharpening).
- Timeout ampliado (90s) y cadena de resiliencia con fallback a Tesseract OCR.
- Detección automática y recursiva de NVIDIA_API_KEY desde .env local.
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


class ImageEnhancer:
    """
    Pipeline de Preprocesamiento Digital de Imagen (PDI) con OpenCV.
    Mejora contraste de trazos manuscritos (lápiz/tinta) y remueve ruido.
    """
    @staticmethod
    def mejorar_imagen(ruta_imagen, output_dir=None):
        if not os.path.exists(ruta_imagen):
            return ruta_imagen

        img_pil = Image.open(ruta_imagen)
        img_np = np.array(img_pil.convert('RGB'))
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        # 1. CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced_gray = clahe.apply(gray)

        # 2. Filtro Bilateral para suavizar ruido sin perder bordes de trazado
        denoised = cv2.bilateralFilter(enhanced_gray, d=7, sigmaColor=50, sigmaSpace=50)

        # 3. Corrección de Inclinación (Deskew horizontal)
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

        # 4. Normalización de alto contraste y Nitidez
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
    """
    Agente 2: Orquestador de Extracción OCR Multimodal e Inferencia.
    """
    def __init__(self, api_key=None, output_dir=None):
        self.api_key = api_key or self._obtener_nvidia_api_key()
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="archery_agent2_")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        # Cadena de modelos NIM optimizados para visión y parsing de planillas
        self.model_chain = [
            "nvidia/nemotron-3.5-parse",
            "meta/llama-3.2-90b-vision-instruct",
            "meta/llama-3.2-11b-vision-instruct",
            "nvidia/nemotron-3.5-super-vl-120b-a12b",
            "mistralai/mistral-large-4-1t-a52b",
            "minimaxai/minimax-m3.1-flash"
        ]

    def _obtener_nvidia_api_key(self):
        key = os.environ.get("NVIDIA_API_KEY", "").strip()
        if key:
            return key
        
        curr = os.getcwd()
        for _ in range(5):
            env_path = os.path.join(curr, ".env")
            if os.path.exists(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                if k.strip() == "NVIDIA_API_KEY":
                                    val = v.strip().strip('"').strip("'")
                                    os.environ["NVIDIA_API_KEY"] = val
                                    return val
                except Exception:
                    pass
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent
        return ""

    def _encode_image_b64(self, ruta_imagen):
        with open(ruta_imagen, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _consultar_nvidia_nim(self, ruta_imagen, tipo_juego):
        if not self.api_key:
            print("[Agente 2] ⚠️ NVIDIA_API_KEY no detectada en .env o variables.")
            return None

        b64_img = self._encode_image_b64(ruta_imagen)
        img_prefix = "data:image/png;base64,"

        prompt_clasificacion = """
        Eres un experto transcriptor de planillas de Tiro con Arco.
        Analiza la imagen recortada de la planilla de CLASIFICACIÓN y extrae todos los números y textos visibles en este formato JSON exacto:
        {
          "valido": true,
          "arquero": "Nombre y Apellido",
          "target": "Número y Letra de diana ej 1A o 8B",
          "club": "Club o Federación",
          "categoria": "Categoría ej Recurvo Senior",
          "series": [
            {"serie": 1, "flechas": [10, 9, 8], "suma_parcial": 27, "total_acumulado": 27},
            {"serie": 2, "flechas": [10, 10, 9], "suma_parcial": 29, "total_acumulado": 56}
          ],
          "totales_planilla": {"total_puntos": 540, "cant_10s": 12, "cant_9s": 18}
        }
        Si la imagen NO contiene una planilla válida, responde: {"valido": false}
        Devuelve ÚNICAMENTE el objeto JSON sin texto introductorio ni bloques de código adicionales.
        """

        prompt_eliminatoria = """
        Eres un experto transcriptor de planillas de Tiro con Arco.
        Analiza la imagen recortada de la planilla de ELIMINATORIA (Duelo de Sets) y extrae todos los datos en este formato JSON exacto:
        {
          "valido": true,
          "arquero": "Nombre y Apellido",
          "posicion": "Posición en el bracket ej Posición 1",
          "club": "Club",
          "sets": [
            {"set": 1, "flechas": [10, 9, 9], "puntos_set": 2},
            {"set": 2, "flechas": [9, 8, 8], "puntos_set": 0}
          ],
          "total_set_points": 6,
          "ganador": true,
          "shoot_off": null
        }
        Si la imagen NO contiene un duelo válido, responde: {"valido": false}
        Devuelve ÚNICAMENTE el objeto JSON.
        """

        prompt = prompt_eliminatoria if tipo_juego == "eliminatoria" else prompt_clasificacion
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        for model in self.model_chain:
            print(f"[Agente 2] 🚀 Consultando modelo NVIDIA NIM: {model}...")

            # Soporte dual: Endpoint Nemotron Parse y Chat Completions estándar
            if "parse" in model.lower():
                url = "https://integrate.api.nvidia.com/v1/chat/completions"
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
            else:
                url = "https://integrate.api.nvidia.com/v1/chat/completions"
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

            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=90)
                if resp.status_code == 200:
                    print(f"[Agente 2] ✅ Respuesta exitosa recibida de {model}")
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(0))
                        parsed["modelo_usado"] = model
                        return parsed
                else:
                    print(f"[Agente 2] ⚠️ {model} devolvió estado HTTP {resp.status_code}: {resp.text[:150]}")
            except Exception as e:
                print(f"[Agente 2] ⚠️ Excepción al consultar {model}: {e}")
                continue

        print("[Agente 2] ❌ Ningún modelo de NVIDIA NIM respondió con éxito. Recurriendo a OCR Local.")
        return None

    def _fallback_tesseract_ocr(self, ruta_imagen, tipo_juego):
        if not OCR_SUPPORT or not os.path.exists(ruta_imagen):
            diagnostico = "Tesseract no instalado" if not OCR_SUPPORT else f"Imagen no encontrada: {ruta_imagen}"
            return {
                "valido": True,
                "arquero": f"Desconocido ({diagnostico})",
                "target": "N/A",
                "series": [],
                "totales_planilla": {"total_puntos": 0, "cant_10s": 0, "cant_9s": 0},
                "texto_raw_ocr": "",
                "modelo_usado": "N/A"
            }

        try:
            img_pil = Image.open(ruta_imagen)
            text_raw = pytesseract.image_to_string(img_pil, lang="spa+eng")
        except Exception as e:
            text_raw = ""

        numeros = re.findall(r'\d+', text_raw)
        dianas = re.findall(r'\d+[A-Da-d]', text_raw)

        lineas = [l.strip() for l in text_raw.splitlines() if len(l.strip()) > 3]
        nombre = lineas[0] if lineas else "Arquero Detectado"
        target_str = dianas[0].upper() if dianas else "N/A"

        return {
            "valido": True,
            "arquero": nombre,
            "target": target_str,
            "club": "Detectado por OCR Local",
            "series": [
                {
                    "serie": i + 1,
                    "flechas": [int(n) for n in numeros[i*3:(i+1)*3]],
                    "suma_parcial": sum([int(n) for n in numeros[i*3:(i+1)*3]]) if len(numeros[i*3:(i+1)*3]) == 3 else 0,
                    "total_acumulado": 0
                }
                for i in range(min(10, len(numeros) // 3))
            ],
            "totales_planilla": {
                "total_puntos": sum([int(n) for n in numeros if int(n) <= 10]) if numeros else 0,
                "cant_10s": text_raw.lower().count("10"),
                "cant_9s": text_raw.lower().count("9")
            },
            "texto_raw_ocr": text_raw,
            "modelo_usado": "Tesseract-OCR-Local (Fallback)"
        }

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
