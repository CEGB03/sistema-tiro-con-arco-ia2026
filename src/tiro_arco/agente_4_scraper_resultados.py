# -*- coding: utf-8 -*-
"""
Agente 4 v13 — Scraper Arqueros Online.
Terminología FATARCO unificada:
- 'Serie' (1..10): tanda de 3 flechas dentro de una planilla (Agentes 2 y 3).
- 'Turno' (Turno 1 / Turno 2): cada planilla completa de 30 flechas (columnas T1 y T2 en Arqueros Online).
"""

import os
import re
import html as html_lib
import time
import hashlib
import tempfile
import unicodedata
import logging
import urllib.parse

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False


# ================= LOGGER =================
def _setup_logger():
    logger = logging.getLogger("agente4")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[Agente4] %(levelname)-5s | %(message)s")
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    try:
        fh = logging.FileHandler(
            os.path.join(tempfile.gettempdir(), "agente4_scraper.log"),
            mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    logger.propagate = False
    return logger


LOG = _setup_logger()

DEFAULT_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/124.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8',
}


# ================= Cookies Antibot & Proof-of-Work =================
def _resolver_pow_sha256(d_val, bits=12, tope=200000):
    prefix = f"{d_val}:".encode("utf-8")
    for n in range(tope):
        digest = hashlib.sha256(prefix + str(n).encode("ascii")).digest()
        b_rem, i, ok = bits, 0, True
        while b_rem >= 8:
            if digest[i] != 0:
                ok = False
                break
            i += 1
            b_rem -= 8
        if ok and (b_rem == 0 or (digest[i] >> (8 - b_rem)) == 0):
            return f"{d_val}.{n}"
    return None


def _aplicar_cookies_js(session, html_text, domain):
    if not session or not html_text:
        return

    m_nav = re.search(
        r"aol_nav='\s*\+\s*'([^']+)'\.split\(''\)\.reverse\(\)\.join\(''\)",
        html_text
    )
    if m_nav:
        val_nav = m_nav.group(1)[::-1]
        session.cookies.set('aol_nav', val_nav, domain=domain, path='/')
        LOG.debug(f"Cookie JS aplicada: aol_nav={val_nav}")

    m_pow = re.search(
        r"var\s+NOMBRE\s*=\s*'([^']+)'\s*;\s*"
        r"var\s+D\s*=\s*'([^']+)'\s*;\s*"
        r"var\s+BITS\s*=\s*(\d+)\s*;\s*"
        r"var\s+TOPE\s*=\s*(\d+)",
        html_text
    )
    if m_pow:
        nombre, d_val, bits, tope = (
            m_pow.group(1),
            m_pow.group(2),
            int(m_pow.group(3)),
            int(m_pow.group(4)),
        )
        t0 = time.time()
        sol = _resolver_pow_sha256(d_val, bits=bits, tope=tope)
        if sol:
            session.cookies.set(nombre, sol, domain=domain, path='/')
            LOG.debug(f"PoW resuelto en {round((time.time()-t0)*1000, 1)}ms: {nombre}={sol}")


# ================= HTTP =================
def _http_get(url, timeout=15, etiqueta="", session=None, extra_headers=None, domain="arquerosonline.com.ar"):
    headers = dict(DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    pref = f"[{etiqueta}] " if etiqueta else ""
    LOG.info(f"{pref}GET → {url}")
    t0 = time.time()

    if REQUESTS_OK:
        try:
            getter = session.get if session is not None else requests.get
            r = getter(url, headers=headers, timeout=timeout, allow_redirects=True)
            LOG.info(f"{pref}← HTTP {r.status_code} | {len(r.text)} bytes | "
                     f"{round(time.time()-t0, 2)}s | final_url={r.url}")
            if session is not None and r.status_code == 200 and r.text:
                _aplicar_cookies_js(session, r.text, domain)
            return r.status_code, r.text, r.url, dict(r.headers)
        except Exception as e:
            LOG.error(f"{pref}✗ requests: {e}")
            return None, str(e), url, {}

    import urllib.request
    import urllib.error
    import gzip
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get('Content-Encoding') == 'gzip':
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            text = raw.decode('utf-8', errors='replace')
            LOG.info(f"{pref}← HTTP {resp.status} | {len(text)} bytes | "
                     f"{round(time.time()-t0, 2)}s | final_url={resp.geturl()}")
            return resp.status, text, resp.geturl(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        LOG.error(f"{pref}✗ HTTP {e.code}")
        return e.code, '', url, dict(e.headers or {})
    except Exception as e:
        LOG.error(f"{pref}✗ urllib: {e}")
        return None, str(e), url, {}


# ================= Normalización / similitud =================
def _norm(s):
    if not s:
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'[^\w\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def _sim_nombres(a, b):
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    pa = set(w for w in na.split() if len(w) >= 3)
    pb = set(w for w in nb.split() if len(w) >= 3)
    if not pa or not pb:
        return False
    return len(pa & pb) >= 2


def _tokens_categoria(cat_str):
    """Expande siglas FATARCO (ej: 'C E60' -> {'compuesto', 'escuela', '60'})."""
    s = _norm(cat_str)
    if not s or s in ('n a', 'general'):
        return set()

    s = re.sub(r'([a-z]+)(\d+)', r'\1 \2', s)
    s = re.sub(r'(\d+)([a-z]+)', r'\1 \2', s)

    mapa_siglas = {
        'r': 'recurvo',
        'c': 'compuesto',
        'b': 'barebow',
        'l': 'longbow',
        't': 'tradicional',
        'e': 'escuela',
        'm': 'masculino',
        'w': 'femenino',
        'f': 'femenino',
        '50': 'master',
        'raso': 'barebow',
    }
    tokens = set()
    for tok in s.split():
        tokens.add(mapa_siglas.get(tok, tok))
    return tokens


def _es_texto_categoria(texto):
    t = re.sub(r'\s+', ' ', str(texto)).strip()
    if not t or len(t) < 5 or len(t) > 90:
        return False
    up = t.upper()
    # Ignorar sub-filas o insignias de ascenso ("Pasa a: Raso Masculino 50+")
    if 'PASA A' in up or re.search(r'\d+/\d+', up):
        return False
    if not any(k in up for k in CAT_KEYWORDS):
        return False
    nums = re.findall(r'\b\d{2,3}\b', up)
    return len(nums) <= 1


def _sim_cat(a, b):
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return True
    if not na or not nb or 'n a' in (na, nb) or 'general' in (na, nb):
        return na == nb
    ta = _tokens_categoria(a)
    tb = _tokens_categoria(b)
    if not ta or not tb:
        return False
    return ta.issubset(tb) or tb.issubset(ta) or len(ta & tb) >= 2


# ================= Parser: torneos del calendario =================
def _parse_torneos(html, base_url):
    torneos, seen = [], set()
    if BS4_OK:
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=re.compile(r'/resultado/\d+')):
            href = a.get('href', '')
            m = re.search(r'/resultado/(\d+)', href)
            if not m:
                continue
            tid = m.group(1)
            if tid in seen:
                continue
            seen.add(tid)
            full = href if href.startswith('http') else urllib.parse.urljoin(base_url, href)
            desc = _descripcion_card(a)
            torneos.append({'torneo_id': tid, 'url_resultado': full, 'descripcion': desc})
    else:
        for m in re.finditer(r'href=["\']([^"\']*?/resultado/(\d+))["\']', html):
            href, tid = m.group(1), m.group(2)
            if tid in seen:
                continue
            seen.add(tid)
            full = href if href.startswith('http') else urllib.parse.urljoin(base_url, href)
            torneos.append({'torneo_id': tid, 'url_resultado': full,
                            'descripcion': f'Torneo {tid}'})
    return torneos


def _descripcion_card(a):
    cur = a
    for _ in range(8):
        cont = cur.find_parent(['div', 'article', 'li', 'tr', 'section'])
        if not cont:
            break
        txt = re.sub(r'\s+', ' ', cont.get_text(separator=' ', strip=True)).strip()
        if 20 <= len(txt) <= 800:
            return txt[:400]
        cur = cont
    return a.get_text(strip=True)[:200] or 'Torneo'


# ================= Parser: resultados del torneo =================
CAT_KEYWORDS = (
    'RECURVO', 'COMPUESTO', 'COMPEUSTO', 'BAREBOW', 'RASO', 'LONG',
    'ESCUELA', 'SENIOR', 'MASTER', 'U18', 'U21', 'U15',
    'TRADICIONAL', 'INSTINTIVO', 'ADAPTADO', '50+'
)

def _parsear_token_puntaje(t):
    t = re.sub(r'\s+', '', str(t)).strip()
    m_slash = re.fullmatch(r'(\d{1,3})/(\d{1,3})(?:/(\d{1,3}))?', t)
    if m_slash:
        pts = int(m_slash.group(1))
        tb = int(m_slash.group(2))
        if pts <= 720:
            return pts, tb, True
        return None

    if re.fullmatch(r'\d{1,3}', t):
        pts = int(t)
        if pts <= 720:
            return pts, 0, False
    return None


def _extraer_arquero_de_textos(texts, cat_actual):
    puntajes_barra = []
    puntajes_todos = []
    palabras = []

    for raw_t in texts:
        t = re.sub(r'\s+', ' ', str(raw_t)).strip()
        if not t:
            continue
        if re.fullmatch(r'\d{1,3}[°ºo]', t):
            continue

        parsed_sc = _parsear_token_puntaje(t)
        if parsed_sc is not None:
            pts, _, es_barra = parsed_sc
            if es_barra:
                puntajes_barra.append(pts)
            puntajes_todos.append(pts)
            continue

        if len(t) >= 2 and re.search(r'[A-Za-zÁÉÍÓÚáéíóúÑñ]{2,}', t):
            palabras.append(t)

    if not palabras:
        return None

    t1 = t2 = tot = None
    if len(puntajes_barra) >= 3:
        t1, t2, tot = puntajes_barra[-3], puntajes_barra[-2], puntajes_barra[-1]
    elif len(puntajes_barra) == 2:
        t1, t2, tot = puntajes_barra[0], 0, puntajes_barra[1]
    elif len(puntajes_todos) >= 3:
        for i in range(len(puntajes_todos) - 2):
            a, b, c = puntajes_todos[i], puntajes_todos[i + 1], puntajes_todos[i + 2]
            if (a > 0 or b > 0) and a + b == c:
                t1, t2, tot = a, b, c
                break
        if tot is None:
            t1, t2, tot = puntajes_todos[-3], puntajes_todos[-2], puntajes_todos[-1]
    elif len(puntajes_todos) == 2:
        t1, t2, tot = puntajes_todos[0], 0, puntajes_todos[1]
    else:
        return None

    if t1 > 10 and t2 > 10 and abs(tot - (t1 + t2)) > 3:
        tot = t1 + t2

    return {
        'arquero_web': palabras[0],
        'club_web': palabras[1] if len(palabras) > 1 else 'N/A',
        'categoria_web': cat_actual,
        'turno1_web': t1,
        'turno2_web': t2,
        'total_web': tot,
        'huella_univoca': f'{t1}_{t2}_{tot}',
    }


def _parse_resultados(html):
    """Parser con detección limpia de encabezados de categoría y soporte '223/1'."""
    if not html:
        return []

    if BS4_OK:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            local, cat = [], 'GENERAL'
            for el in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'caption', 'div', 'p', 'tr']):
                if el.name != 'tr':
                    if el.find_parent('tr') is not None or el.find(['table', 'tr']):
                        continue
                    txt = el.get_text(" ", strip=True)
                    if _es_texto_categoria(txt):
                        cat = re.sub(r'\s+', ' ', txt).strip()
                    continue

                cells = el.find_all(['td', 'th'])
                if not cells:
                    continue
                texts = [c.get_text(" ", strip=True) for c in cells]
                joined = ' '.join(texts).strip()
                if 'PASA A' in joined.upper():
                    continue
                if len(cells) < 3 or _es_texto_categoria(joined):
                    if _es_texto_categoria(joined):
                        cat = joined
                    continue

                parsed = _extraer_arquero_de_textos(texts, cat)
                if parsed:
                    local.append(parsed)

            if local:
                LOG.info(f"Parser[1/3] bs4-dom: {len(local)} filas")
                return local
        except Exception as e:
            LOG.warning(f"Parser[1/3] bs4-dom error: {e}")

    try:
        local, cat = [], 'GENERAL'
        token_re = re.compile(
            r'<tr\b[^>]*>(.*?)</tr>|<(h[1-6]|caption|div|p)\b[^>]*>(.*?)</\2>',
            re.DOTALL | re.I
        )
        for m in token_re.finditer(html):
            if m.group(2):
                inner = m.group(3)
                if '<tr' in inner.lower() or '<table' in inner.lower():
                    continue
                txt = html_lib.unescape(re.sub(r'<[^>]+>', ' ', inner))
                txt = re.sub(r'\s+', ' ', txt).strip()
                if _es_texto_categoria(txt):
                    cat = txt
                continue

            block = m.group(1)
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', block, re.DOTALL | re.I)
            if not cells:
                continue
            texts = [
                re.sub(r'\s+', ' ', html_lib.unescape(re.sub(r'<[^>]+>', ' ', c))).strip()
                for c in cells
            ]
            joined = ' '.join(texts).strip()
            if 'PASA A' in joined.upper():
                continue
            if len(cells) < 3 or _es_texto_categoria(joined):
                if _es_texto_categoria(joined):
                    cat = joined
                continue

            parsed = _extraer_arquero_de_textos(texts, cat)
            if parsed:
                local.append(parsed)

        if local:
            LOG.info(f"Parser[2/3] regex-dom: {len(local)} filas")
            return local
    except Exception as e:
        LOG.warning(f"Parser[2/3] regex-dom error: {e}")

    try:
        limpio = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.I)
        limpio = re.sub(r'<style[^>]*>.*?</style>', ' ', limpio, flags=re.DOTALL | re.I)
        limpio = html_lib.unescape(re.sub(r'<[^>]+>', '\n', limpio))
        local, cat = [], 'GENERAL'
        for linea in limpio.split('\n'):
            linea = re.sub(r'\s+', ' ', linea).strip()
            if not linea or 'PASA A' in linea.upper():
                continue
            if _es_texto_categoria(linea):
                cat = linea
                continue
            if len(linea) < 12:
                continue
            m = re.match(
                r'^(?:\d{1,3}[°ºo]?\s+)?(.{4,80}?)\s+'
                r'(\d{1,3})(?:/\d+(?:/\d+)?)?\s+'
                r'(\d{1,3})(?:/\d+(?:/\d+)?)?\s+'
                r'(\d{1,3})(?:/\d+(?:/\d+)?)?\b',
                linea
            )
            if not m:
                continue
            nombre = m.group(1).strip()
            try:
                t1, t2, tot = int(m.group(2)), int(m.group(3)), int(m.group(4))
            except ValueError:
                continue
            if not (0 <= t1 <= 400 and 0 <= t2 <= 400 and 0 <= tot <= 720):
                continue
            if not re.search(r'[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}', nombre):
                continue
            local.append({
                'arquero_web': nombre, 'club_web': 'N/A',
                'categoria_web': cat,
                'turno1_web': t1, 'turno2_web': t2, 'total_web': tot,
                'huella_univoca': f'{t1}_{t2}_{tot}',
            })
        if local:
            LOG.info(f"Parser[3/3] regex-texto: {len(local)} filas")
            return local
    except Exception as e:
        LOG.warning(f"Parser[3/3] regex-texto error: {e}")

    LOG.error("Parser: las 3 estrategias fallaron. 0 filas.")
    return []


# ================= Clase =================
class Agente4ScraperResultados:
    MAPEO_ANIOS = {2026: '14', 2025: '13', 2024: '12', 2023: '11'}

    def __init__(self, domain='arquerosonline.com.ar', anio_id='14'):
        self.domain = domain
        self.anio_id = str(anio_id)
        self.base_url = f'https://{domain}'
        self.last_telemetria = {}

    def _new_session(self):
        return requests.Session() if REQUESTS_OK else None

    def _candidatos_busqueda(self, club):
        if not club or not club.strip():
            return [""]
        c = club.strip()
        candidatos = [
            "Asociacion Familia Piemontesa",
            "Familia Piemontesa",
            "Familia",
            "Piemontesa",
        ]
        m = re.match(r'^([A-Z]{2,15})\b', c)
        if m:
            candidatos.append(m.group(1))
        candidatos.append(c)
        candidatos.append("")

        vistos, final = set(), []
        for x in candidatos:
            k = _norm(x)
            if k not in vistos:
                vistos.add(k)
                final.append(x)
        return final

    def _url_calendario(self, search, anio_id=None):
        anio = str(anio_id or self.anio_id)
        q = urllib.parse.quote(search or "", safe="")
        return (f'{self.base_url}/calendario/{anio}'
                f'?disciplina_id=0&perPage=15&search={q}'
                f'&zona_id=0&tipotorneo_id=0')

    def buscar_torneos_por_club(self, club_busqueda, anio_calendario=None):
        anio = str(anio_calendario or self.anio_id)
        candidatos = self._candidatos_busqueda(club_busqueda)
        LOG.info(f"=== Búsqueda === año={anio} club='{club_busqueda}'")

        session = self._new_session()
        telemetria = {
            'url_busqueda_calendario': None,
            'search_query_raw': club_busqueda,
            'anio_calendario': anio,
            'deps_http': 'requests' if REQUESTS_OK else 'urllib',
            'deps_html': 'bs4' if BS4_OK else 'regex',
            'error_conexion': None,
            'debug_html_path': None,
            'intentos': [],
            'torneos_encontrados': [],
        }

        for i, cand in enumerate(candidatos, 1):
            url = self._url_calendario(cand, anio)
            info = {'candidato': cand, 'url': url, 'http_status': None,
                    'n_torneos': 0, 'error': None, 'bytes_recibidos': 0}

            status, body, _, _ = _http_get(
                url, timeout=20, etiqueta=f"cal#{i}", session=session, domain=self.domain
            )
            info['http_status'] = status
            info['bytes_recibidos'] = len(body) if isinstance(body, str) else 0

            if status == 200 and body:
                torneos = _parse_torneos(body, self.base_url)
                info['n_torneos'] = len(torneos)
                if torneos:
                    telemetria['url_busqueda_calendario'] = url
                    telemetria['torneos_encontrados'] = torneos
                    self.last_telemetria = telemetria
                    return torneos
            else:
                info['error'] = body if isinstance(body, str) else f'HTTP {status}'

            telemetria['intentos'].append(info)

        if telemetria['intentos']:
            last = telemetria['intentos'][-1]
            telemetria['url_busqueda_calendario'] = last['url']
            telemetria['error_conexion'] = last['error'] or 'Sin torneos en ningún candidato'
        self.last_telemetria = telemetria
        return []

    def _extraer_url_lista_diferida(self, html_pagina, page_url):
        raw_attr = None
        if BS4_OK:
            try:
                soup = BeautifulSoup(html_pagina, 'html.parser')
                el = soup.select_one('[data-res-lista]')
                if el and el.get('data-res-lista'):
                    raw_attr = el.get('data-res-lista')
            except Exception:
                pass
        if not raw_attr:
            m = re.search(r'data-res-lista=["\']([^"\']+)["\']', html_pagina, re.I)
            if m:
                raw_attr = html_lib.unescape(m.group(1))
        if not raw_attr:
            return None
        return urllib.parse.urljoin(page_url, raw_attr.strip())

    def extraer_resultados_torneo_web(self, url_o_id):
        url = (f'{self.base_url}/resultado/{url_o_id}'
               if str(url_o_id).isdigit() else url_o_id)
        LOG.info(f"=== Resultados torneo id={url_o_id} ===")

        session = self._new_session()
        status, body, final_url, _ = _http_get(
            url, timeout=20, etiqueta="resultado_shell", session=session, domain=self.domain
        )
        if status != 200 or not body:
            return []

        html_objetivo = body
        url_lista = self._extraer_url_lista_diferida(body, final_url)

        if url_lista:
            ajax_headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'text/html, */*; q=0.01',
                'Referer': final_url,
            }
            st_l, body_l, _, resp_headers = _http_get(
                url_lista,
                timeout=20,
                etiqueta="resultado_ajax",
                session=session,
                extra_headers=ajax_headers,
                domain=self.domain
            )
            if st_l == 403:
                otra = next((v for k, v in resp_headers.items()
                             if k.lower() == 'x-lista-reintento'), None)
                if otra:
                    otra_url = urllib.parse.urljoin(final_url, otra)
                    st_l, body_l, _, _ = _http_get(
                        otra_url,
                        timeout=20,
                        etiqueta="resultado_ajax_retry",
                        session=session,
                        extra_headers=ajax_headers,
                        domain=self.domain
                    )
            if st_l == 200 and body_l:
                html_objetivo = body_l

        results = _parse_resultados(html_objetivo)
        LOG.info(f"Total filas extraídas: {len(results)}")
        return results

    def _fallback_local(self, csv_path=None):
        try:
            import pandas as pd
        except ImportError:
            return []
        for p in [csv_path,
                  "torneo_indoor_afapieco_cordoba_recortado.csv",
                  "/workspace/knowledge/torneo_indoor_afapieco_cordoba_recortado.csv",
                  "/app/torneo_indoor_afapieco_cordoba_recortado.csv"]:
            if p and os.path.exists(p):
                try:
                    df = pd.read_csv(p)
                    out = []
                    for _, r in df.iterrows():
                        tot = int(r.get('Total_Score', 0)) if pd.notnull(r.get('Total_Score')) else 0
                        out.append({
                            'arquero_web': str(r.get('Archer', '')).strip(),
                            'club_web': str(r.get('Club', 'AFPSF')).strip(),
                            'categoria_web': str(r.get('Category', '')).strip(),
                            'turno1_web': tot, 'turno2_web': 0, 'total_web': tot,
                            'huella_univoca': f'{tot}_0_{tot}',
                        })
                    return out
                except Exception as e:
                    LOG.error(f"CSV fallback error: {e}")
        return []

    # ---- helpers de puntaje por Turno (1 planilla = 10 series de 3 flechas = 1 Turno) ----
    @staticmethod
    def _fecha_de_archivo(archivo):
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(archivo or ''))
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

    @staticmethod
    def _puntaje_turno_planilla(item):
        """
        Una planilla local suma sus series de flechas (1..10) para obtener el puntaje
        de ese Turno (Turno 1 o Turno 2).
        """
        tot_calc = item.get('totales_calculados_series', {}).get('total_puntos', 0)
        if tot_calc and tot_calc > 0:
            return int(tot_calc)
        series = item.get('series', [])
        if series:
            return int(sum(s.get('suma_parcial_flechas', 0) for s in series))
        return int(item.get('totales_oficiales_planilla', {}).get('total_puntos', 0) or 0)

    def _agrupar_turnos_locales(self, auditados):
        """
        Agrupa por arquero normalizado para identificar si en el documento están
        cargados Turno 1, Turno 2 o ambos (el campo 'ronda' de Agente 2 indica el Turno).
        """
        por_arquero = {}
        for item in auditados:
            arq = _norm(item.get('arquero', ''))
            if not arq or arq == 'desconocido':
                continue
            turno = str(item.get('ronda', '1') or '1').strip()
            pts = self._puntaje_turno_planilla(item)
            if pts <= 0:
                continue
            por_arquero.setdefault(arq, {})[turno] = pts
        return por_arquero

    def _score_torneo(self, resultados, auditados):
        if not resultados:
            return 0
        turnos_locales = self._agrupar_turnos_locales(auditados)
        score = 0
        for item in auditados:
            arq = item.get('arquero', '')
            pts = self._puntaje_turno_planilla(item)
            turno = str(item.get('ronda', '1') or '1').strip()
            t_map = turnos_locales.get(_norm(arq), {})
            t1_loc = t_map.get('1', pts if turno == '1' else None)
            t2_loc = t_map.get('2', pts if turno == '2' else None)

            for r in resultados:
                if _sim_nombres(arq, r['arquero_web']):
                    score += 2
                    if t1_loc is not None and r['turno1_web'] == t1_loc:
                        score += 2
                    if t2_loc is not None and r['turno2_web'] == t2_loc:
                        score += 2
                    break
                elif pts > 0 and (r['turno1_web'] == pts or r['turno2_web'] == pts or r['total_web'] == pts):
                    score += 1
                    break
        return score

    # ---- contraste ----
    def contrastar_manifiesto_con_web(
        self,
        manifiesto_3,
        resultados_web_oficiales=None,
        club_filtro=None,
        torneo_id=None,
        anio_id=None,
    ):
        t0 = time.time()
        auditados = (manifiesto_3.get('resultados_auditados', [])
                     if isinstance(manifiesto_3, dict) else [])
        archivo_origen = (manifiesto_3.get('archivo_origen', '')
                          if isinstance(manifiesto_3, dict) else '')
        fecha_archivo = self._fecha_de_archivo(archivo_origen)

        LOG.info(f"=== CONTRASTAR === archivo='{archivo_origen}' "
                 f"fecha='{fecha_archivo}' cuadrantes={len(auditados)}")

        torneos, url_result, torneo_elegido = [], None, None
        modo, estado, error = "HTTP_LIVE", "🟢 ONLINE", None

        if not resultados_web_oficiales:
            torneos = self.buscar_torneos_por_club(club_filtro or "",
                                                   anio_calendario=anio_id)
            tel = getattr(self, 'last_telemetria', {})
            if tel.get('error_conexion') and not torneos:
                error = tel['error_conexion']
                estado = f"⚠️ SIN_DATOS_WEB ({error})"

            if torneos:
                if torneo_id:
                    torneo_elegido = next(
                        (t for t in torneos if t['torneo_id'] == str(torneo_id)), None)
                    if torneo_elegido:
                        url_result = torneo_elegido['url_resultado']
                        resultados_web_oficiales = self.extraer_resultados_torneo_web(
                            torneo_elegido['torneo_id'])
                else:
                    mejor = None
                    for t in torneos:
                        res = self.extraer_resultados_torneo_web(t['torneo_id'])
                        if not res:
                            continue
                        score = self._score_torneo(res, auditados)
                        if mejor is None or score > mejor[0]:
                            mejor = (score, res, t)
                    if mejor:
                        _, resultados_web_oficiales, torneo_elegido = mejor
                        url_result = torneo_elegido['url_resultado']

        if not resultados_web_oficiales:
            modo = "SIN_DATOS_WEB"
            if not error:
                estado = "ℹ️ SIN_RESULTADOS_WEB"
            resultados_web_oficiales = self._fallback_local()
            if resultados_web_oficiales:
                modo = "FALLBACK_LOCAL_CSV"

        if not url_result:
            url_result = f"{self.base_url}/resultado/{torneo_id or 'sin_torneo'}"

        stats = {
            'total_cuadrantes_locales': len(auditados),
            'total_registros_web': len(resultados_web_oficiales),
            'datos_web_disponibles': bool(resultados_web_oficiales),
            'matches_por_huella': 0,
            'matches_por_nombre': 0,
            'matches_limpios': 0,
            'discrepancia_nombre': 0,
            'discrepancia_club': 0,
            'discrepancia_categoria': 0,
            'discrepancia_turno1': 0,
            'discrepancia_turno2': 0,
            'discrepancia_total': 0,
            'no_localizados_web': 0,
            'ausencias_dns_confirmadas': 0,
            'alertas_planilla_omisa': 0,
        }

        turnos_locales = self._agrupar_turnos_locales(auditados)
        verificaciones, sugerencias = [], []

        for item in auditados:
            pag = item.get('pagina', 1)
            target = item.get('target_id', 'A')
            arq_local = item.get('arquero', 'Desconocido')
            club_local = item.get('club', 'N/A')
            cat_local = item.get('categoria', 'N/A')
            turno_local = str(item.get('ronda', '1') or '1').strip()
            img = item.get('ruta_recorte', '')

            pts_turno = self._puntaje_turno_planilla(item)
            series = item.get('series', [])
            sin_puntos = (len(series) == 0 and pts_turno == 0)

            t_map = turnos_locales.get(_norm(arq_local), {})
            tiene_ambos_turnos = ('1' in t_map and '2' in t_map)
            t1_local = t_map.get('1', pts_turno if turno_local == '1' else None)
            t2_local = t_map.get('2', pts_turno if turno_local == '2' else None)
            tot_local = (t1_local + t2_local) if tiene_ambos_turnos else pts_turno

            if not resultados_web_oficiales:
                stats['no_localizados_web'] += 1
                verificaciones.append({
                    'pagina': pag, 'target_id': target, 'arquero_local': arq_local,
                    'ruta_recorte': img, 'estado_web': '⚫ SIN_DATOS_WEB',
                    'diagnostico': f'Sin resultados web (Turno {turno_local}: {pts_turno} pts). Motivo: {error or "vacío"}.',
                    'sugerencias': [],
                })
                continue

            if sin_puntos:
                aparece = any(_sim_nombres(arq_local, w['arquero_web'])
                              for w in resultados_web_oficiales)
                if aparece:
                    stats['alertas_planilla_omisa'] += 1
                    verificaciones.append({
                        'pagina': pag, 'target_id': target, 'arquero_local': arq_local,
                        'ruta_recorte': img, 'estado_web': '🔴 ALERTA_PLANILLA_OMISA',
                        'diagnostico': 'Sin puntos local pero en web sí.',
                        'sugerencias': ['Revisar recorte: posible omisión OCR.'],
                    })
                else:
                    stats['ausencias_dns_confirmadas'] += 1
                    verificaciones.append({
                        'pagina': pag, 'target_id': target, 'arquero_local': arq_local,
                        'ruta_recorte': img, 'estado_web': '⚪ AUSENTE_CONFIRMADO_DNS',
                        'diagnostico': 'Sin puntos local y no figura en web (DNS).',
                        'sugerencias': [],
                    })
                continue

            match_web, metodo = None, None
            candidatos_nom = [w for w in resultados_web_oficiales
                              if _sim_nombres(arq_local, w['arquero_web'])]
            if candidatos_nom:
                if tiene_ambos_turnos:
                    match_web = min(candidatos_nom, key=lambda w: abs(w['total_web'] - tot_local))
                elif turno_local == '2':
                    match_web = min(candidatos_nom, key=lambda w: abs(w['turno2_web'] - pts_turno))
                else:
                    match_web = min(candidatos_nom, key=lambda w: min(
                        abs(w['turno1_web'] - pts_turno),
                        abs(w['turno2_web'] - pts_turno)
                    ))
                metodo = 'nombre'
                stats['matches_por_nombre'] += 1
            else:
                candidatos_pts = [
                    w for w in resultados_web_oficiales
                    if (tiene_ambos_turnos and w['turno1_web'] == t1_local and w['turno2_web'] == t2_local)
                    or (not tiene_ambos_turnos and (
                        w['turno1_web'] == pts_turno or w['turno2_web'] == pts_turno
                    ))
                ]
                if len(candidatos_pts) == 1:
                    match_web = candidatos_pts[0]
                    metodo = 'huella'
                    stats['matches_por_huella'] += 1

            if not match_web:
                stats['no_localizados_web'] += 1
                verificaciones.append({
                    'pagina': pag, 'target_id': target, 'arquero_local': arq_local,
                    'ruta_recorte': img, 'estado_web': '⚠️ NO_LOCALIZADO_EN_WEB',
                    'diagnostico': f'Sin match en web (Turno {turno_local}: {pts_turno} pts).',
                    'sugerencias': [],
                })
                continue

            sugs = []
            if not _sim_nombres(arq_local, match_web['arquero_web']):
                stats['discrepancia_nombre'] += 1
                sugs.append(f'Nombre web: <b>{match_web["arquero_web"]}</b> '
                            f'vs local: <i>{arq_local}</i>')
            if (club_local not in ('N/A', '') and match_web['club_web'] not in ('N/A', '')
                    and not _sim_nombres(club_local, match_web['club_web'])):
                stats['discrepancia_club'] += 1
                sugs.append(f'Club web: <b>{match_web["club_web"]}</b> '
                            f'vs local: <i>{club_local}</i>')
            if (cat_local not in ('N/A', '') and match_web['categoria_web'] not in ('N/A', 'GENERAL', '')
                    and not _sim_cat(cat_local, match_web['categoria_web'])):
                stats['discrepancia_categoria'] += 1
                sugs.append(f'Categoría web: <b>{match_web["categoria_web"]}</b> '
                            f'vs local: <i>{cat_local}</i>')

            turno_cotejado = turno_local
            if tiene_ambos_turnos:
                if match_web['turno1_web'] != t1_local:
                    stats['discrepancia_turno1'] += 1
                    sugs.append(f'Turno 1 web: <b>{match_web["turno1_web"]}</b> '
                                f'vs local: <b>{t1_local}</b>')
                if match_web['turno2_web'] != t2_local:
                    stats['discrepancia_turno2'] += 1
                    sugs.append(f'Turno 2 web: <b>{match_web["turno2_web"]}</b> '
                                f'vs local: <b>{t2_local}</b>')
                if match_web['total_web'] != tot_local:
                    stats['discrepancia_total'] += 1
                    sugs.append(f'Total web: <b>{match_web["total_web"]}</b> '
                                f'vs local (T1+T2): <b>{tot_local}</b>')
            else:
                if turno_local == '2':
                    if match_web['turno2_web'] != pts_turno:
                        stats['discrepancia_turno2'] += 1
                        sugs.append(f'Turno 2 web: <b>{match_web["turno2_web"]}</b> '
                                    f'vs local: <b>{pts_turno}</b>')
                else:
                    if match_web['turno1_web'] == pts_turno:
                        turno_cotejado = '1'
                    elif match_web['turno2_web'] == pts_turno:
                        turno_cotejado = '2'
                    else:
                        stats['discrepancia_turno1'] += 1
                        sugs.append(f'Turno 1 web: <b>{match_web["turno1_web"]}</b> '
                                    f'vs local: <b>{pts_turno}</b>')

            detalle_turno = (
                f'Turno 1={t1_local}, Turno 2={t2_local}, Total={tot_local}'
                if tiene_ambos_turnos
                else (
                    f'Turno {turno_cotejado} = {pts_turno} pts '
                    f'(Web: Turno 1={match_web["turno1_web"]}, '
                    f'Turno 2={match_web["turno2_web"]}, '
                    f'Total={match_web["total_web"]})'
                )
            )

            if sugs:
                sug = {
                    'pagina': pag, 'target_id': target, 'arquero_local': arq_local,
                    'arquero_web_sugerido': match_web['arquero_web'],
                    'club_web_sugerido': match_web['club_web'],
                    'categoria_web_sugerida': match_web['categoria_web'],
                    'total_web_sugerido': match_web['total_web'],
                    'metodo_match': metodo, 'ruta_recorte': img,
                    'estado_web': '🟡 DISCREPANCIA_CON_SUGERENCIA',
                    'diagnostico': f'Match por {metodo} ({detalle_turno}). Solo sugerencias.',
                    'sugerencias': sugs,
                }
                sugerencias.append(sug)
                verificaciones.append(sug)
            else:
                stats['matches_limpios'] += 1
                verificaciones.append({
                    'pagina': pag, 'target_id': target, 'arquero_local': arq_local,
                    'ruta_recorte': img, 'estado_web': '🟢 VALIDADO_OK_WEB',
                    'metodo_match': metodo,
                    'diagnostico': f'Match perfecto por {metodo} ({detalle_turno}).',
                    'sugerencias': [],
                })

        total_match = stats['matches_por_huella'] + stats['matches_por_nombre']
        stats['tasa_match_limpio_%'] = (
            round(100 * stats['matches_limpios'] / total_match, 1) if total_match else 0.0)
        for campo in ['nombre', 'club', 'categoria', 'turno1', 'turno2', 'total']:
            stats[f'tasa_discrepancia_{campo}_%'] = (
                round(100 * stats[f'discrepancia_{campo}'] / total_match, 1)
                if total_match else 0.0)

        t_elapsed = round(time.time() - t0, 2)
        telemetria = {
            'url_busqueda_calendario': getattr(self, 'last_telemetria', {}).get('url_busqueda_calendario'),
            'query_busqueda_club': club_filtro,
            'url_resultado_oficial': url_result,
            'torneo_elegido': torneo_elegido,
            'torneos_disponibles': torneos,
            'modo_ejecucion': modo,
            'estado_conexion_http': estado,
            'error_red_detalle': error,
            'total_registros_obtenidos': len(resultados_web_oficiales),
            'tiempo_ejecucion_seg': t_elapsed,
            'debug_html_calendario': getattr(self, 'last_telemetria', {}).get('debug_html_path'),
            'intentos_calendario': getattr(self, 'last_telemetria', {}).get('intentos', []),
            'deps_http': 'requests' if REQUESTS_OK else 'urllib',
            'deps_html': 'bs4' if BS4_OK else 'regex',
            'log_path': os.path.join(tempfile.gettempdir(), "agente4_scraper.log"),
        }

        return {
            'resumen_agente4': {
                'total_cuadrantes_cotejados': len(auditados),
                'validados_ok_web': stats['matches_limpios'],
                'ausencias_dns_confirmadas': stats['ausencias_dns_confirmadas'],
                'discrepancias_con_sugerencia': len(sugerencias),
                'no_localizados_web': stats['no_localizados_web'],
                'alertas_planilla_omisa': stats['alertas_planilla_omisa'],
                'tiempo_ejecucion_seg': t_elapsed,
            },
            'estadisticas_fallas': stats,
            'telemetria_scraping': telemetria,
            'resultados_web_oficiales': resultados_web_oficiales,
            'verificaciones_web': verificaciones,
            'sugerencias_correccion_humana': sugerencias,
        }


# ================= debug_url =================
def debug_url(url_o_id):
    ag = Agente4ScraperResultados()
    if str(url_o_id).isdigit() or '/resultado/' in str(url_o_id):
        res = ag.extraer_resultados_torneo_web(url_o_id)
        return {'target': url_o_id, 'total_filas': len(res), 'muestra': res[:5]}
    status, body, _, _ = _http_get(url_o_id, timeout=25, etiqueta="debug")
    if status != 200 or not isinstance(body, str):
        return {'url': url_o_id, 'http_status': status, 'error': body, 'torneos': []}
    torneos = _parse_torneos(body, 'https://arquerosonline.com.ar')
    return {'url': url_o_id, 'http_status': status, 'torneos': torneos}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(debug_url(sys.argv[1]))