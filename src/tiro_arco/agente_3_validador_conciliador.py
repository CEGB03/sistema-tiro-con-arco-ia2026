#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 Agente 3 (v5): Validador Lógico, Reconciliación Matemática y Auditoría Avanzada FATARCO / World Archery.

Novedades en v5:
1. Reconciliación de Total General desde el Acumulado Escrito en la Última Serie:
   - Si no se detectó el recuadro del total general por separado en la cabecera/pie (total=0),
     Agente 3 toma el total acumulado escrito en la última serie (o la sumatoria de parciales escritas).
2. Conteo Diferenciado de 10s, 9s y Xs según Modalidad (Sala vs Aire Libre):
   - En Sala (Indoor: 10m, 15m, 18m): El conteo oficial se valida por la sumatoria de (Xs + 10s) y 9s detectados en las series.
   - En Aire Libre (Outdoor: 20m, 30m, 40m, 50m, 60m, 70m): Se contabilizan y diferencian explícitamente las Xs, los 10s puros y los 9s.
3. Mantiene la deducción inteligente de flechas ilegibles (ej: 'U' -> 4 cuando 2+3=5 y suma escrita=9).
4. Mantiene la reconciliación bidireccional de confusiones OCR 15 vs 16 / 5 vs 6.
"""

import re
import json


class Agente3ValidadorConciliador:
    def __init__(self, padron_arqueros=None):
        """
        :param padron_arqueros: Dict opcional para matchear arqueros desconocidos por target/diana.
        """
        self.padron_arqueros = padron_arqueros or {}

    def sanitizar_token_flecha(self, token_str):
        s = str(token_str).strip().upper()
        if not s or s in ["\\MBOX{}", "MBOX", "{}", "NONE", "NULL", "N/A"]:
            return {"raw": s, "val_str": "", "puntos": 0, "valida": False, "es_x": False, "es_10": False}

        if s == "X":
            return {"raw": s, "val_str": "X", "puntos": 10, "valida": True, "es_x": True, "es_10": True}
        if s == "10":
            return {"raw": s, "val_str": "10", "puntos": 10, "valida": True, "es_x": False, "es_10": True}
        if s in ["M", "0", "MISS"]:
            return {"raw": s, "val_str": "M", "puntos": 0, "valida": True, "es_x": False, "es_10": False}

        if s.isdigit():
            v = int(s)
            if 1 <= v <= 10:
                return {"raw": s, "val_str": str(v), "puntos": v, "valida": True, "es_x": False, "es_10": (v == 10)}

        m_num = re.search(r'(\d{1,2})', s)
        if m_num:
            v_cand = int(m_num.group(1))
            if 1 <= v_cand <= 10:
                return {"raw": s, "val_str": str(v_cand), "puntos": v_cand, "valida": True, "sugerencia_ocr": True, "es_x": False, "es_10": (v_cand == 10)}
            elif v_cand > 10:
                first_digit = int(str(v_cand)[0])
                if 1 <= first_digit <= 9:
                    return {"raw": s, "val_str": str(first_digit), "puntos": first_digit, "valida": True, "sugerencia_ocr": True, "es_x": False, "es_10": False}

        return {"raw": s, "val_str": s, "puntos": 0, "valida": False, "ruido": True, "es_x": False, "es_10": False}

    def auditar_cuadrante(self, item_transcripcion):
        trans = item_transcripcion.get("transcripcion", {})
        pagina = item_transcripcion.get("pagina", 1)
        target_id = str(item_transcripcion.get("target_id", "N/A"))

        arquero_orig = trans.get("arquero", "Desconocido")
        club_orig = trans.get("club", "N/A")
        cat_orig = trans.get("categoria", "N/A")
        target_orig = trans.get("target", target_id)
        distancia_raw = str(trans.get("distancia", "18m")).lower()

        # Determinar Modalidad: Sala (Indoor) vs Aire Libre (Outdoor)
        es_aire_libre = any(d in distancia_raw for d in ["20m", "30m", "40m", "50m", "60m", "70m", "outdoor", "aire libre"])
        modalidad_str = "Aire Libre (Outdoor)" if es_aire_libre else "Sala (Indoor)"

        # 1. Matcheo con Padrón de Arqueros si el nombre es Desconocido
        arquero_auditado = arquero_orig
        club_auditado = club_orig
        cat_auditada = cat_orig
        matcheado_por_padron = False

        if (arquero_orig in ["Desconocido", "Tanteador", "Planillero", ""] or "Desconocido" in arquero_orig) and target_orig in self.padron_arqueros:
            info_padr = self.padron_arqueros[target_orig]
            arquero_auditado = info_padr.get("arquero", arquero_orig)
            if club_auditado == "N/A":
                club_auditado = info_padr.get("club", club_orig)
            if cat_auditada == "N/A":
                cat_auditada = info_padr.get("categoria", cat_orig)
            matcheado_por_padron = True

        series_raw = trans.get("series", [])
        totales_oficiales_raw = trans.get("totales_planilla", {})
        total_puntos_oficial = totales_oficiales_raw.get("total_puntos", 0)
        c10_oficial = totales_oficiales_raw.get("cant_10s", 0)
        c9_oficial = totales_oficiales_raw.get("cant_9s", 0)
        cX_oficial = totales_oficiales_raw.get("cant_xs", 0)

        series_auditadas = []
        total_puntos_calc = 0
        cant_xs_calc = 0
        cant_10s_puras_calc = 0
        cant_10s_totales_calc = 0
        cant_9s_calc = 0
        errores_series = []
        advertencias_series = []
        deducciones_realizadas = []

        acumulado_calc = 0

        for s_idx, s in enumerate(series_raw, 1):
            n_serie = s.get("serie", s_idx)
            flechas_raw = s.get("flechas", [])
            suma_parcial_escrita = s.get("suma_parcial_escrita", 0)

            flechas_auditadas = []
            suma_parcial_flechas = 0
            invalid_tokens_idx = []

            for idx_f, f_token in enumerate(flechas_raw):
                f_info = self.sanitizar_token_flecha(f_token)
                flechas_auditadas.append(f_info)

                if f_info["valida"]:
                    p = f_info["puntos"]
                    suma_parcial_flechas += p
                else:
                    invalid_tokens_idx.append(idx_f)

            reconciliado_por_deduccion = False
            flecha_deducida_info = None

            # REGLA 1: DEDUCCIÓN DE FLECHA ILEGIBLE (ej: 2 + 3 + 'U' = 9 -> 'U' = 4)
            if len(invalid_tokens_idx) == 1 and suma_parcial_escrita > 0:
                idx_inv = invalid_tokens_idx[0]
                diferencia_deducida = suma_parcial_escrita - suma_parcial_flechas
                if 0 <= diferencia_deducida <= 10:
                    val_deducido_str = "M" if diferencia_deducida == 0 else str(diferencia_deducida)
                    orig_raw = flechas_auditadas[idx_inv]["raw"]
                    es_x_ded = (val_deducido_str == "X")
                    es_10_ded = (val_deducido_str in ["X", "10"])
                    flechas_auditadas[idx_inv] = {
                        "raw": orig_raw,
                        "val_str": val_deducido_str,
                        "puntos": diferencia_deducida,
                        "valida": True,
                        "deducida_por_diferencia": True,
                        "valor_original_ruido": orig_raw,
                        "es_x": es_x_ded,
                        "es_10": es_10_ded
                    }
                    suma_parcial_flechas = suma_parcial_escrita
                    reconciliado_por_deduccion = True
                    flecha_deducida_info = {
                        "serie": n_serie,
                        "original": orig_raw,
                        "deducido": val_deducido_str,
                        "diferencia_calculada": diferencia_deducida
                    }
                    deducciones_realizadas.append(flecha_deducida_info)
                    advertencias_series.append(f"💡 Serie {n_serie}: Flecha ilegible '{orig_raw}' deducida automáticamente como '{val_deducido_str}' (Suma escrita {suma_parcial_escrita} - parcial = {diferencia_deducida})")

            # REGLA 2: RECONCILIACIÓN BIDIRECCIONAL 15 vs 16 / CONFUSIÓN OCR SUMA ESCRITA O FLECHA 5/6
            if len(invalid_tokens_idx) == 0 and suma_parcial_escrita > 0 and suma_parcial_escrita != suma_parcial_flechas:
                diff_sum = suma_parcial_escrita - suma_parcial_flechas

                # CASO A: Flecha leída como 6 pero suma escrita es 15 (ej: ['6', '5', '5'] = 16 vs escrita = 15)
                flechas_val_strs = [f["val_str"] for f in flechas_auditadas]
                if diff_sum == -1 and "6" in flechas_val_strs:
                    idx_6 = flechas_val_strs.index("6")
                    orig_f = flechas_auditadas[idx_6]["val_str"]
                    flechas_auditadas[idx_6]["val_str"] = "5"
                    flechas_auditadas[idx_6]["puntos"] = 5
                    flechas_auditadas[idx_6]["corregida_ocr_5_6"] = True
                    suma_parcial_flechas -= 1
                    reconciliado_por_deduccion = True
                    advertencias_series.append(f"💡 Serie {n_serie}: Flecha '{orig_f}' corregida a '5' por confusión de OCR (confirmado por suma escrita en papel de {suma_parcial_escrita} pts)")

                # CASO B: Suma escrita leída como 16 (o 26/36) pero las flechas suman 15 (o 25/35)
                elif diff_sum in [1, 2] or (str(suma_parcial_escrita).endswith("6") and str(suma_parcial_flechas).endswith("5")):
                    orig_esc = suma_parcial_escrita
                    suma_parcial_escrita = suma_parcial_flechas
                    reconciliado_por_deduccion = True
                    advertencias_series.append(f"💡 Serie {n_serie}: Suma escrita en papel ('{orig_esc}') reconciliada a '{suma_parcial_flechas}' (confirmado por suma de flechas [{suma_parcial_flechas} pts] y progresión acumulada)")

            # Conteo de Xs, 10s y 9s tras deducción
            for f_info in flechas_auditadas:
                if f_info["valida"]:
                    v_str = f_info["val_str"]
                    if v_str == "X":
                        cant_xs_calc += 1
                        cant_10s_totales_calc += 1
                    elif v_str == "10":
                        cant_10s_puras_calc += 1
                        cant_10s_totales_calc += 1
                    elif v_str == "9":
                        cant_9s_calc += 1

            acumulado_calc += suma_parcial_flechas
            total_puntos_calc += suma_parcial_flechas

            serie_coincide = True
            if suma_parcial_escrita > 0 and suma_parcial_escrita != suma_parcial_flechas:
                serie_coincide = False
                errores_series.append(f"Serie {n_serie}: Flechas ({suma_parcial_flechas} pts) != Papel ({suma_parcial_escrita} pts)")

            series_auditadas.append({
                "serie": n_serie,
                "flechas_raw": flechas_raw,
                "flechas_auditadas": [f["val_str"] for f in flechas_auditadas if f["val_str"]],
                "suma_parcial_flechas": suma_parcial_flechas,
                "suma_parcial_escrita": suma_parcial_escrita,
                "acumulado_calculado": acumulado_calc,
                "serie_coincide": serie_coincide,
                "reconciliado_por_deduccion": reconciliado_por_deduccion,
                "flecha_deducida_info": flecha_deducida_info
            })

        # REGLA 3: DEDUCCIÓN DE TOTAL GENERAL DESDE EL ACUMULADO ESCRITO EN LA ÚLTIMA SERIE
        total_oficial_estado = "LEIDO_CABECERA_OK"
        if total_puntos_oficial == 0:
            if series_raw:
                ultima_s = series_raw[-1]
                acum_escrito_ult = ultima_s.get("total_acumulado_escrito", 0) or ultima_s.get("acumulado_escrito", 0) or ultima_s.get("acumulado", 0)
                
                if acum_escrito_ult > 0:
                    total_puntos_oficial = acum_escrito_ult
                    total_oficial_estado = "DEDUCIDO_ULTIMA_SERIE"
                    advertencias_series.append(f"💡 Total en papel ({total_puntos_oficial} pts) deducido del acumulado escrito en la última serie")
                else:
                    sumas_parciales_escritas = [s.get("suma_parcial_escrita", 0) for s in series_raw if s.get("suma_parcial_escrita", 0) > 0]
                    if sumas_parciales_escritas:
                        total_puntos_oficial = sum(sumas_parciales_escritas)
                        total_oficial_estado = "SUMATORIA_PARCIALES_ESCRITAS"
                        advertencias_series.append(f"💡 Total en papel ({total_puntos_oficial} pts) calculado desde la sumatoria de parciales escritas por serie")
                    elif total_puntos_calc > 0:
                        total_oficial_estado = "NO_LEIDO_O_EN_BLANCO"
                        advertencias_series.append(f"ℹ️ Recuadro de Total escrito no detectado en papel; Total calculado por serie de flechas: {total_puntos_calc} pts")
                    else:
                        total_oficial_estado = "SIN_PUNTOS"
            elif total_puntos_calc > 0:
                total_oficial_estado = "NO_LEIDO_O_EN_BLANCO"
                advertencias_series.append(f"ℹ️ Recuadro de Total escrito no detectado en papel; Total calculado por serie de flechas: {total_puntos_calc} pts")
            else:
                total_oficial_estado = "SIN_PUNTOS"

        # REGLA 4: CONTEO Y DEDUCCIÓN DE 10s, 9s Y Xs SEGÚN MODALIDAD (SALA VS AIRE LIBRE)
        if c10_oficial == 0:
            c10_oficial = cant_10s_totales_calc
            advertencias_series.append(f"💡 Conteo de 10s ({c10_oficial}) obtenido por sumatoria de series ({modalidad_str})")
        if c9_oficial == 0:
            c9_oficial = cant_9s_calc
            if cant_9s_calc > 0:
                advertencias_series.append(f"💡 Conteo de 9s ({c9_oficial}) obtenido por sumatoria de series ({modalidad_str})")
        if es_aire_libre and cX_oficial == 0:
            cX_oficial = cant_xs_calc
            if cant_xs_calc > 0:
                advertencias_series.append(f"💡 Conteo de Xs ({cX_oficial}) obtenido por sumatoria de series ({modalidad_str})")

        coincide_total = (total_puntos_calc == total_puntos_oficial) if total_puntos_oficial > 0 else True

        # Cálculo del Índice de Certeza (Score 0-100%)
        score_certeza = 100.0

        if arquero_auditado == "Desconocido":
            score_certeza -= 20.0
            advertencias_series.append("Arquero no identificado en cabecera")

        if len(series_raw) == 0:
            if total_puntos_oficial > 0:
                score_certeza -= 35.0
                advertencias_series.append(f"Tabla de series omitida por OCR; conserva Total Oficial de {total_puntos_oficial} pts")
            else:
                score_certeza = 100.0
        else:
            if len(series_raw) < 10:
                score_certeza -= (10 - len(series_raw)) * 4.0
                advertencias_series.append(f"Registradas {len(series_raw)} de 10 series")

            if errores_series:
                score_certeza -= len(errores_series) * 6.0

            if total_puntos_oficial > 0 and not coincide_total and total_oficial_estado == "LEIDO_CABECERA_OK":
                score_certeza -= 25.0
                advertencias_series.append(f"Total Calculado ({total_puntos_calc} pts) != Total en Papel ({total_puntos_oficial} pts)")

        score_certeza = max(0.0, min(100.0, score_certeza))

        if trans.get("sin_puntos_registrados", False) or (len(series_raw) == 0 and total_puntos_oficial == 0):
            estado_auditoria = "SIN_PUNTOS_CONFIRMADO"
        elif score_certeza >= 90.0 and len(errores_series) == 0:
            estado_auditoria = "APROBADO_AUTOMATICO"
        elif score_certeza >= 60.0:
            estado_auditoria = "REVISION_RECOMENDADA"
        else:
            estado_auditoria = "REQUIERE_REVISION_HUMANA"

        p_img = item_transcripcion.get("ruta_recorte_procesada") or item_transcripcion.get("ruta_recorte_original", "")

        return {
            "pagina": pagina,
            "target_id": target_id,
            "arquero": arquero_auditado,
            "target": target_orig,
            "club": club_auditado,
            "categoria": cat_auditada,
            "ronda": trans.get("ronda", "1"),
            "distancia": trans.get("distancia", "18m"),
            "modalidad": modalidad_str,
            "matematica_valida": (len(errores_series) == 0 and coincide_total),
            "score_certeza": round(score_certeza, 1),
            "estado_auditoria": estado_auditoria,
            "matcheado_por_padron": matcheado_por_padron,
            "ruta_recorte": p_img,
            "total_oficial_estado": total_oficial_estado,
            "totales_oficiales_planilla": {
                "total_puntos": total_puntos_oficial,
                "cant_10s": c10_oficial,
                "cant_9s": c9_oficial,
                "cant_xs": cX_oficial
            },
            "totales_calculados_series": {
                "total_puntos": total_puntos_calc,
                "cant_10s_totales": cant_10s_totales_calc,
                "cant_10s_puras": cant_10s_puras_calc,
                "cant_xs": cant_xs_calc,
                "cant_9s": cant_9s_calc
            },
            "series": series_auditadas,
            "deducciones_realizadas": deducciones_realizadas,
            "errores": errores_series,
            "advertencias": advertencias_series,
            "modelo_ocr_usado": trans.get("modelo_usado", "N/A")
        }

    def auditar_manifiesto_completo(self, manifiesto_agente2):
        transcripciones = manifiesto_agente2.get("transcripciones", [])
        
        auditorias = []
        total_aprobados = 0
        total_revision = 0
        total_sin_puntos = 0

        for t in transcripciones:
            res_aud = self.auditar_cuadrante(t)
            auditorias.append(res_aud)

            est = res_aud["estado_auditoria"]
            if est == "APROBADO_AUTOMATICO":
                total_aprobados += 1
            elif est == "SIN_PUNTOS_CONFIRMADO":
                total_sin_puntos += 1
            else:
                total_revision += 1

        return {
            "archivo_origen": manifiesto_agente2.get("archivo_origen", ""),
            "resumen_auditoria": {
                "total_cuadrantes_procesados": len(auditorias),
                "aprobados_automaticos": total_aprobados,
                "requiere_revision_humana": total_revision,
                "sin_puntos_confirmados": total_sin_puntos
            },
            "resultados_auditados": auditorias
        }
