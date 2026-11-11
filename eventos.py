#!/usr/bin/env python3
"""Arma la cartelera (eventos.json) con funciones reales y fechas en Santiago.

Lo ejecuta GitHub Actions cada mañana (.github/workflows/diario.yml).

Fuentes:
  Teatro Municipal de Santiago  lista de espectáculos por su API pública de WordPress
                                (/wp-json/wp/v2/shows) y las fechas desde la sección
                                "FECHAS" de cada página ("Martes 17 de noviembre – 18:00 horas").
  Puntoticket                   categorías /musica y /teatro; cada tarjeta trae lugar,
                                género, título y fechas en formato AAAA-MM-DD.
Se priorizan gustos de los papás (música clásica, ópera, boleros, rock clásico, pop latino,
teatro) y se descartan fiestas electrónicas, urbano, infantil y deportes.
"""
import html
import json
import pathlib
import re
import time
from datetime import date, datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "eventos.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9"})

HOY = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
HORIZONTE = HOY + timedelta(days=100)
MESES = {m: i + 1 for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                                          "agosto", "septiembre", "octubre", "noviembre", "diciembre"])}
COMUNAS_RM = re.compile(r"santiago|las condes|vitacura|providencia|ñuñoa|nunoa|la reina|lo barnechea|pudahuel|"
                        r"huechuraba|estaci[oó]n central|recoleta|independencia|macul|pe[ñn]alol[eé]n|la florida|"
                        r"maip[uú]|san miguel|quinta normal|cerrillos|san joaqu[ií]n|conchal[ií]|renca|quilicura|"
                        r"la cisterna|san bernardo|puente alto|colina|lampa|[ñn]u[ñn]oa", re.I)
DESCARTAR = re.compile(r"electr[oó]nic|reggaet|trap|urbano|metal|punk|hip.?hop|\brap\b|fiesta|after|"
                       r"stand.?up|infantil|niñ|familia|f[uú]tbol|corrida|deporte|e-?sport|anime|k-?pop", re.I)
CLASICA = re.compile(r"cl[aá]sic|[oó]pera|l[ií]ric|sinf[oó]n|orquesta|piano|coro|c[aá]mara|barroc", re.I)


def get(url):
    r = S.get(url, timeout=40)
    r.raise_for_status()
    return r


def limpiar(t):
    t = html.unescape(re.sub(r"<[^>]+>", "", t or ""))
    return re.sub(r"\s+", " ", t).strip()


# ---------- Teatro Municipal ----------
TIPO_MUNICIPAL = {"ópera": "opera", "ballet y danza": "ballet", "conciertos y recitales": "concierto",
                  "grandes estrellas": "concierto", "pianistas": "concierto", "sonatas beethoven": "concierto",
                  "musical": "teatro", "radioteatro": "teatro"}
RE_FECHA = re.compile(
    r"(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+(\d{1,2})\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
    r"(?:\s+(?:de\s+)?(\d{4}))?(?:\s*[–—\-,]\s*(\d{1,2})[:.](\d{2}))?", re.I)


def fechas_de_texto(texto):
    out = set()
    for m in RE_FECHA.finditer(texto):
        dia, mes = int(m.group(2)), MESES[m.group(3).lower()]
        anio = int(m.group(4)) if m.group(4) else HOY.year
        if not m.group(4) and mes < HOY.month - 2:
            anio += 1
        try:
            d = date(anio, mes, dia)
        except ValueError:
            continue
        if HOY <= d <= HORIZONTE:
            out.add(d.isoformat() + (f"T{int(m.group(5)):02d}:{m.group(6)}" if m.group(5) else ""))
    # si una fecha aparece con y sin hora, se deja la versión con hora
    con_hora = {f[:10] for f in out if len(f) > 10}
    return sorted(f for f in out if len(f) > 10 or f not in con_hora)


def municipal():
    base = "https://municipal.cl"
    cats = {c["id"]: c["name"] for c in get(f"{base}/wp-json/wp/v2/category_show?per_page=100").json()}
    eventos = []
    for pagina in range(1, 5):
        r = S.get(f"{base}/wp-json/wp/v2/shows?per_page=50&page={pagina}&orderby=modified&order=desc", timeout=40)
        if r.status_code != 200:
            break
        lista = r.json()
        if not lista:
            break
        for show in lista:
            nombres = [cats.get(i, "").lower() for i in show.get("category_show", [])]
            tipo = next((TIPO_MUNICIPAL[n] for n in nombres if n in TIPO_MUNICIPAL), None)
            if not tipo:
                continue  # visitas guiadas, cartelera digital, familiar
            try:
                pagina_html = get(show["link"]).text
            except Exception:
                continue
            sopa = BeautifulSoup(pagina_html, "html.parser")
            for n in sopa(["script", "style", "noscript"]):
                n.decompose()
            fechas = fechas_de_texto(sopa.get_text(" "))
            if not fechas:
                continue
            eventos.append({"titulo": limpiar(show["title"]["rendered"]), "tipo": tipo,
                            "genero": next((cats.get(i) for i in show.get("category_show", [])), ""),
                            "lugar": "Teatro Municipal de Santiago", "fechas": fechas,
                            "url": show["link"], "fuente": "Teatro Municipal"})
            time.sleep(0.5)
    return eventos


# ---------- Puntoticket ----------
def puntoticket():
    base = "https://www.puntoticket.com"
    eventos = []
    for categoria in ("musica", "teatro"):
        sopa = BeautifulSoup(get(f"{base}/{categoria}").text, "html.parser")
        for a in sopa.select("a[href]"):
            h3, f, d = a.find("h3"), a.select_one("p.fecha"), a.select_one("p.descripcion")
            if not (h3 and f and d):
                continue
            fechas = re.findall(r"\d{4}-\d{2}-\d{2}", f.get("v-html", "") + " " + f.get_text(" "))
            if not fechas:
                continue
            lugar_completo = limpiar(d.strong.get_text() if d.strong else d.get_text().split("/")[0])
            genero = limpiar(d.get_text().split("/", 1)[1]) if "/" in d.get_text() else ""
            titulo = limpiar(h3.get("title") or h3.get_text())
            if titulo.isupper():
                titulo = titulo.capitalize()
            if not COMUNAS_RM.search(lugar_completo) or DESCARTAR.search(genero + " " + titulo):
                continue
            if categoria == "teatro":
                tipo = "teatro"
            elif CLASICA.search(genero + " " + titulo):
                tipo = "concierto"
            else:
                tipo = "musica"
            desde, hasta = fechas[0], fechas[1] if len(fechas) > 1 else fechas[0]
            if hasta < HOY.isoformat() or desde > HORIZONTE.isoformat():
                continue
            href = a["href"]
            ev = {"titulo": titulo, "tipo": tipo, "genero": genero,
                  "lugar": lugar_completo.replace(" - ", ", "), "url": href if href.startswith("http") else base + href,
                  "fuente": "Puntoticket"}
            # rango largo (temporada de teatro) o fechas puntuales
            d1, d2 = date.fromisoformat(desde), date.fromisoformat(hasta)
            if (d2 - d1).days > 3:
                ev.update({"fechas": [max(desde, HOY.isoformat())], "desde": desde, "hasta": hasta})
            else:
                ev["fechas"] = [(d1 + timedelta(days=k)).isoformat() for k in range((d2 - d1).days + 1)]
            eventos.append(ev)
        time.sleep(1)
    return eventos


def main():
    previo = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {"eventos": []}
    eventos, fuentes_ok = [], 0
    for nombre, f in (("Teatro Municipal", municipal), ("Puntoticket", puntoticket)):
        try:
            nuevos = f()
            fuentes_ok += 1
            print(f"{nombre}: {len(nuevos)} eventos")
        except Exception as e:
            print(f"{nombre}: ERROR {e.__class__.__name__}: {e}; se conservan sus eventos anteriores")
            nuevos = [e for e in previo.get("eventos", []) if e.get("fuente") == nombre]
        eventos += nuevos
    if not fuentes_ok:
        raise SystemExit("Ninguna fuente respondió; no se modifica eventos.json.")
    vistos, unicos = set(), []
    for e in sorted(eventos, key=lambda e: e["fechas"][0]):
        clave = (e["titulo"].lower(), e["fechas"][0])
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(e)
    SALIDA.write_text(json.dumps({"actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "eventos": unicos}, ensure_ascii=False, indent=1), encoding="utf-8")
    for e in unicos[:40]:
        print(f"  {e['fechas'][0]}  {e['tipo']:9} {e['titulo'][:60]}")


if __name__ == "__main__":
    main()
