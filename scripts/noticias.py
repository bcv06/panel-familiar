#!/usr/bin/env python3
"""Descarga los titulares internacionales del día y los guarda en noticias.json.

Lo ejecuta GitHub Actions cada mañana (.github/workflows/noticias.yml).
Solo usa la biblioteca estándar de Python.
"""
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "noticias.json"
UA = "Mozilla/5.0 (compatible; panel-familiar/1.0)"
POR_FUENTE = 10

FUENTES = {
    "bbc":  "https://feeds.bbci.co.uk/mundo/rss.xml",
    "dw":   "https://rss.dw.com/rdf/rss-sp-all",
    "f24":  "https://www.france24.com/es/rss",
    "pais": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada",
}


def etiqueta(el):
    return el.tag.rsplit("}", 1)[-1]


def hijo(el, *nombres):
    for c in el:
        if etiqueta(c) in nombres:
            return c
    return None


def a_iso(texto):
    if not texto:
        return None
    texto = texto.strip()
    try:
        return parsedate_to_datetime(texto).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def leer(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        raiz = ET.fromstring(r.read())
    items = []
    for el in raiz.iter():
        if etiqueta(el) not in ("item", "entry"):
            continue
        t = hijo(el, "title")
        l = hijo(el, "link")
        d = hijo(el, "pubDate", "updated", "published", "date")
        titulo = (t.text or "").strip() if t is not None else ""
        enlace = ""
        if l is not None:
            enlace = (l.text or "").strip() or l.get("href", "")
        if titulo and enlace:
            items.append({"t": titulo, "l": enlace, "d": a_iso(d.text if d is not None else None)})
        if len(items) >= POR_FUENTE:
            break
    return items


def main():
    anterior = {}
    if SALIDA.exists():
        try:
            anterior = json.loads(SALIDA.read_text(encoding="utf-8")).get("fuentes", {})
        except Exception:
            anterior = {}

    fuentes = {}
    for clave, url in FUENTES.items():
        try:
            fuentes[clave] = leer(url)
            print(f"{clave}: {len(fuentes[clave])} titulares")
        except Exception as e:
            fuentes[clave] = anterior.get(clave, [])
            print(f"{clave}: error ({e}); se mantienen los titulares anteriores")

    if not any(fuentes.values()):
        raise SystemExit("No se pudo leer ninguna fuente.")

    datos = {"actualizado": datetime.now(timezone.utc).isoformat(), "fuentes": fuentes}
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
