#!/usr/bin/env python3
"""Extrae precios de frutas y verduras de Jumbo, Lider, Santa Isabel, Unimarc y Tottus.

Lo ejecuta GitHub Actions cada lunes (.github/workflows/precios.yml) y escribe precios.json.

Cómo lee cada tienda (verificado el 6 de noviembre de 2026):
  Jumbo y Santa Isabel  búsqueda por producto; la página trae una ficha estándar (JSON-LD)
                        con nombre y enlace, y en cada tarjeta el precio por kg o por unidad.
  Unimarc               categoría completa de frutas y verduras; la página trae los datos
                        de cada producto (precio de lista, oferta y precio por kg).
  Tottus                búsqueda por producto; datos en __NEXT_DATA__.
  Lider                 búsqueda por producto con navegador automático (bloquea descargas
                        directas); datos en __NEXT_DATA__.
En cada tienda se elige el formato fresco más barato por kg (o por unidad). Si una tienda
falla, se conservan sus precios anteriores y queda marcado en "estado".
"""
import json
import pathlib
import re
import time
import unicodedata
import urllib.parse
from datetime import datetime, timezone

import requests

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "precios.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
CABECERAS = {"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9",
             "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}

# id, búsqueda, unidad de comparación, debe contener, no debe contener (texto sin tildes, minúsculas)
PRODUCTOS = [
    ("palta", "palta hass", "kg", r"palta hass", r"organic|aceite|mayonesa|aderezo|salsa|guacamole"),
    ("platano", "platano", "kg", r"platano", r"frito|chips|deshid|barraganet|organic|bebe|snack|harina|nectar|jugo|yogur|compota"),
    ("manzana", "manzana", "kg", r"manzana", r"verde|granny|organic|jugo|compota|deshid|chips|nectar|vinagre|cidra|snack|yogur|\bte\b|mix|bebida|galleta|pure|barra"),
    ("naranja", "naranja", "kg", r"naranja", r"jugo|nectar|organic|kiwi|mix|pina|bebida|mermelada|helado|\bte\b|yogur|tangelo|mandarina"),
    ("limon", "limon", "kg", r"limon", r"sutil|coctel|cocktail|organic|jugo|limonada|mayonesa|aderezo|\bte\b|galleta|sal |bebida|helado|pica|soda|agua|yogur|salsa"),
    ("frutilla", "frutilla", "kg", r"frutilla", r"mix|liofiliz|congel|blanca|jugo|yogur|mermelada|helado|nectar|bebida|leche|galleta|chocolate|deshid|kiwi|mango|arandano|pina|gomita|alfajor|cereal|barra|\bte\b|isoton"),
    ("cereza", "cerezas", "kg", r"cereza", r"carozo|almibar|marrasquino|conserva|mix|jugo|nectar|helado|yogur|mermelada|chocolate|tomate"),
    ("kiwi", "kiwi", "kg", r"kiwi", r"mix|pina|naranja|nectar|jugo|yogur|bebida|isoton|frutilla|mango|kumquat"),
    ("tomate", "tomate", "kg", r"tomate", r"coctel|cocktail|cherry|romanita|pasta|salsa|triturado|pelado|deshid|seco|ketchup|hidropon|jugo|sopa|organic|perita|pure|cubos|natural en|lata|caja"),
    ("lechuga", "lechuga", "un", r"lechuga", r"mix|ensalada|hojas|baby|bolsa \d|selecta|gourmet"),
    ("cebolla", "cebolla", "kg", r"cebolla", r"morada|perla|empanada|frita|crispy|deshid|polvo|caramel|cebollin|verdeo|escabeche|encurt|sopa|pluma|organic"),
    ("papa", "papa", "kg", r"\bpapas?\b", r"frita|chips|prefrita|pre frita|duquesa|noisette|hash|camote|nativa|soufl|cocktail|organic|lays|pringles|pure|bastones|rustica|gajo|cubos|hilo|congel|corte"),
    ("zanahoria", "zanahoria", "kg", r"zanahoria", r"baston|rallada|baby|jugo|mix|organic|julian|picada|cubos"),
    ("zapallo", "zapallo italiano", "un", r"zapallo italiano", r"relleno|picado|organic|bandeja|mix"),
    ("pepino", "pepino", "un", r"pepino", r"alaska|dill|encurt|conserva|pickle|snack|aguas|gin|agua"),
    ("brocoli", "brocoli", "un", r"brocoli", r"congel|florete|mix|organic|picado|bandeja|ramitos"),
]
PRECIO_MIN, PRECIO_MAX = 150, 40000
sesion = requests.Session()
sesion.headers.update(CABECERAS)


def norm(t):
    t = unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t.lower())


def num(t):
    d = re.sub(r"[^\d]", "", str(t or ""))
    return int(d) if d else None


def get(url):
    r = sesion.get(url, timeout=40)
    r.raise_for_status()
    return r.text


def reg(nombre, precio, unidad, url):
    return {"nombre": (nombre or "").strip(), "precio": precio, "unidad": unidad, "url": url}


def elegir(registros):
    """Para cada producto, el registro fresco más barato en la unidad de comparación."""
    salida = {}
    for pid, _, unidad, incluye, excluye in PRODUCTOS:
        c = [r for r in registros
             if r["precio"] and r["unidad"] == unidad
             and PRECIO_MIN <= r["precio"] <= PRECIO_MAX
             and re.search(incluye, norm(r["nombre"])) and not re.search(excluye, norm(r["nombre"]))]
        if c:
            salida[pid] = min(c, key=lambda r: r["precio"])
    return salida


# ---------- Jumbo y Santa Isabel ----------
def cencosud(base):
    regs = []
    for _, q, *_ in PRODUCTOS:
        h = get(f"{base}/busqueda?ft={urllib.parse.quote(q)}")
        for bloque in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', h, re.S):
            try:
                datos = json.loads(bloque)
            except ValueError:
                continue
            for o in datos if isinstance(datos, list) else [datos]:
                if o.get("@type") != "ItemList":
                    continue
                for e in o.get("itemListElement", []):
                    it = e.get("item") or {}
                    if not re.search(r"frutas y verduras", ((it.get("brand") or {}).get("name") or ""), re.I):
                        continue
                    ruta = urllib.parse.urlparse(it.get("url", "")).path
                    i = h.find(f'href="{ruta}"')
                    if i < 0:
                        continue
                    m = re.search(r"\$([\d.]+) x (kg|un)", h[i:i + 5000])
                    if m:
                        regs.append(reg(it.get("name"), num(m.group(1)), m.group(2), base + ruta))
        time.sleep(1)
    return regs


# ---------- Unimarc ----------
def unimarc():
    regs, vistos = [], set()
    for pagina in range(1, 15):
        h = get(f"https://www.unimarc.cl/category/frutas-y-verduras?page={pagina}")
        bloques = h.split('"itemId":"')[1:]
        nuevos = 0
        for b in bloques:
            def campo(k):
                m = re.search(r'"%s":"([^"]*)"' % k, b)
                return m.group(1) if m else None
            nombre = campo("nameComplete")
            if not nombre or nombre in vistos:
                continue
            vistos.add(nombre)
            nuevos += 1
            ppum = (campo("discountPrice") and campo("discountPpumPrice")) or campo("ppumListPrice")
            m = re.search(r"\$([\d.]+)\s*x\s*(\w+)", ppum or "", re.I)
            if not m:
                continue
            ruta = (campo("detailUrl") or "").removesuffix("/p")
            regs.append(reg(nombre, num(m.group(1)), "kg" if m.group(2).lower() == "kg" else "un",
                            "https://www.unimarc.cl/product" + ruta))
        if not nuevos:
            break
        time.sleep(1)
    return regs


# ---------- Tottus ----------
def tottus():
    regs = []
    for _, q, *_ in PRODUCTOS:
        h = get(f"https://www.tottus.cl/tottus-cl/buscar?Ntt={urllib.parse.quote(q)}")
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
        if not m:
            continue
        for p in json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("results") or []:
            if not str(p.get("merchantCategoryId", "")).startswith("J0401"):  # frutas y verduras
                continue
            precios = p.get("prices") or []
            pr = next((x for x in precios if x.get("type") == "internetPrice"), None) or \
                 next((x for x in precios if x.get("type") == "normalPrice"), None)
            if not pr:
                continue
            if pr.get("pum"):
                valor, unidad = num(pr["pum"]["price"][0]), ("kg" if norm(pr["pum"].get("label")) == "kg" else "un")
            elif "granel" in norm(p.get("displayName")):
                valor, unidad = num(pr["price"][0]), "kg"
            else:
                valor, unidad = num(pr["price"][0]), "un"
            regs.append(reg(p.get("displayName"), valor, unidad, p.get("url")))
        time.sleep(1)
    return regs


# ---------- Lider (navegador automático) ----------
def productos_next(o, out, profundidad=0):
    if profundidad > 20:
        return
    if isinstance(o, dict):
        if o.get("__typename") == "Product" and o.get("name") and o.get("priceInfo"):
            out.append(o)
            return
        for v in o.values():
            productos_next(v, out, profundidad + 1)
    elif isinstance(o, list):
        for v in o:
            productos_next(v, out, profundidad + 1)


def lider():
    from playwright.sync_api import sync_playwright
    regs = []
    with sync_playwright() as pw:
        nav = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = nav.new_context(user_agent=UA, locale="es-CL", viewport={"width": 1366, "height": 900})
        pg = ctx.new_page()
        pg.goto("https://super.lider.cl/", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(4000)
        for _, q, *_ in PRODUCTOS:
            try:
                pg.goto(f"https://super.lider.cl/search?q={urllib.parse.quote(q)}", wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_selector("#__NEXT_DATA__", state="attached", timeout=25000)
                datos = json.loads(pg.eval_on_selector("#__NEXT_DATA__", "e => e.textContent"))
            except Exception as e:
                print(f"  lider/{q}: sin datos ({e.__class__.__name__})")
                continue
            prods = []
            productos_next(datos, prods)
            for p in prods:
                url = p.get("canonicalUrl") or ""
                if not re.search(r"/ip/(frutas|verduras)/", url, re.I):
                    continue
                pi = p.get("priceInfo") or {}
                m = re.search(r"\$([\d.]+)\s*x\s*(kg|un)", str(pi.get("unitPrice") or ""), re.I)
                if m:
                    valor, unidad = num(m.group(1)), m.group(2).lower()
                else:
                    linea = str(pi.get("linePrice") or pi.get("itemPrice") or "")
                    valor, unidad = num(linea), ("kg" if re.search(r"/\s*kg", linea, re.I) else "un")
                regs.append(reg(p.get("name"), valor, unidad, "https://super.lider.cl" + url))
            pg.wait_for_timeout(2500)
        nav.close()
    return regs


TIENDAS = {
    "jumbo": lambda: cencosud("https://www.jumbo.cl"),
    "lider": lider,
    "santa": lambda: cencosud("https://www.santaisabel.cl"),
    "unimarc": unimarc,
    "tottus": tottus,
}


def main():
    previo = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    precios = previo.get("precios", {})
    estado = {}
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for tienda, extraer in TIENDAS.items():
        try:
            elegidos = elegir(extraer())
        except Exception as e:
            print(f"{tienda}: ERROR {e.__class__.__name__}: {e}")
            elegidos = {}
        ok = len(elegidos) >= 6
        estado[tienda] = {"ok": ok, "encontrados": len(elegidos)}
        print(f"\n{tienda}: {len(elegidos)} productos {'OK' if ok else '(se conservan los anteriores)'}")
        if not ok:
            continue
        for pid, r in elegidos.items():
            precios.setdefault(pid, {})[tienda] = {"precio": r["precio"], "nombre": r["nombre"], "url": r["url"], "fecha": ahora}
            print(f"  {pid:10} ${r['precio']:>7,}  {r['nombre'][:55]}".replace(",", "."))
        # lo que la tienda ya no vende online se quita
        for pid, fila in precios.items():
            if tienda in fila and pid not in elegidos:
                del fila[tienda]

    if not any(e["ok"] for e in estado.values()):
        raise SystemExit("Ninguna tienda respondió; no se modifica precios.json.")
    SALIDA.write_text(json.dumps({"actualizado": ahora, "estado": estado, "precios": precios},
                                 ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
