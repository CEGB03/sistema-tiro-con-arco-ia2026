#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 Agente 3 (v3): Validador Lógico y Reconciliación con Clarificación de Totales No Leídos (Papel 0 vs Calc X).

Mejoras en v3:
1. Reconciliación Inteligente de Totales:
   Si total_puntos_oficial es 0 (porque la casilla del total impreso/manuscrito en papel no fue leída por el OCR o estaba en blanco),
   NO genera un falso error de discrepancia "Papel: 0 != Calc: 212".
   En su lugar, marca el total de papel como "NO_LEIDO_O_EN_BLANCO", valida la coherencia matemática de las series calculadas (e.g. 212 pts)
   y no aplica la penalización de 25% al índice de certeza.

2. Conserva la deducción inteligente de flechas ilegibles (ej: "U" -> 4 cuando 2+3=5 y suma escrita=9).
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
            return {"raw": s, "val_str": "", "puntos": 0, "valida": False}

        if s in ["X", "10"]:
            return {"raw": s, "val_str": s, "puntos": 10, "valida": True, "es_10_o_x": True}
        if s in ["M", "0", "MISS"]:
            return {"raw": s, "val_str": "M", "puntos": 0, "valida": True, "es_10_o_x": False}

        if s.isdigit():
            v = int(s)
            if 1 <= v <= 10:
                return {"raw": s, "val_str": str(v), "puntos": v, "valida": True, "es_10_o_x": (v == 10)}

        m_num = re.search(r'(\d{1,2})', s)
        if m_num:
            v_cand = int(m_num.group(1))
            if 1 <= v_cand <= 10:
                return {"raw": s, "val_str": str(v_cand), "puntos": v_cand, "valida": True, "sugerencia_ocr": True}
            elif v_cand > 10:
                first_digit = int(str(v_cand)[0])
                if 1 <= first_digit <= 9:
                    return {"raw": s, "val_str": str(first_digit), "puntos": first_digit, "valida": True, "sugerencia_ocr": True}

        return {"raw": s, "val_str": s, "puntos": 0, "valida": False, "ruido": True}

    def auditar_cuadrante(self, item_transcripcion):
        trans = item_transcripcion.get("transcripcion", {})
        pagina = item_transcripcion.get("pagina", 1)
        target_id = str(item_transcripcion.get("target_id", "N/A"))

        arquero_orig = trans.get("arquero", "Desconocido")
        club_orig = trans.get("club", "N/A")
        cat_orig = trans.get("categoria", "N/A")
        target_orig = trans.get("target", target_id)

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

        series_auditadas = []
        total_puntos_calc = 0
        cant_10s_calc = 0
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

            if len(invalid_tokens_idx) == 1 and suma_parcial_escrita > 0:
                idx_inv = invalid_tokens_idx[0]
                diferencia_deducida = suma_parcial_escrita - suma_parcial_flechas
                if 0 <= diferencia_deducida <= 10:
                    val_deducido_str = "M" if diferencia_deducida == 0 else str(diferencia_deducida)
                    orig_raw = flechas_auditadas[idx_inv]["raw"]
                    flechas_auditadas[idx_inv] = {
                        "raw": orig_raw,
                        "val_str": val_deducido_str,
                        "puntos": diferencia_deducida,
                        "valida": True,
                        "deducida_por_diferencia": True,
                        "valor_original_ruido": orig_raw
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

            for f_info in flechas_auditadas:
                if f_info["valida"]:
                    if f_info["val_str"] in ["X", "10"]:
                        cant_10s_calc += 1
                    elif f_info["val_str"] == "9":
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

        # Cotejo Inteligente de Totales Finales:
        # Si total_puntos_oficial es 0 (recuadro de total en papel en blanco o no leído por OCR),
        # NO se trata como un choque falso de matemáticas.
        if total_puntos_oficial > 0:
            coincide_total = (total_puntos_calc == total_puntos_oficial)
            total_oficial_estado = "LEIDO"
        else:
            coincide_total = True
            total_oficial_estado = "NO_LEIDO_O_EN_BLANCO"
            if total_puntos_calc > 0:
                advertencias_series.append(f"ℹ️ Recuadro de Total escrito no detectado en papel; Total calculado por serie de flechas: {total_puntos_calc} pts")

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

            if total_puntos_oficial > 0 and not coincide_total:
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
            "matematica_valida": (len(errores_series) == 0 and coincide_total),
            "score_certeza": round(score_certeza, 1),
            "estado_auditoria": estado_auditoria,
            "matcheado_por_padron": matcheado_por_padron,
            "ruta_recorte": p_img,
            "total_oficial_estado": total_oficial_estado,
            "totales_oficiales_planilla": {
                "total_puntos": total_puntos_oficial,
                "cant_10s": c10_oficial,
                "cant_9s": c9_oficial
            },
            "totales_calculados_series": {
                "total_puntos": total_puntos_calc,
                "cant_10s": cant_10s_calc,
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
