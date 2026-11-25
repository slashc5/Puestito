"""Fuentes de búsqueda de lugares (OpenStreetMap, Google Places, demo) y enriquecimiento desde la web."""
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request

from .config import ruta
from .intenciones import LO_QUE_SEA, expandir
from .util import distancia_m, emails_validos, normalizar

UA = "PostuladorLocal/1.0 (busqueda personal de empleo)"


def _http(url, data=None, headers=None, timeout=25) -> str:
    h = {"User-Agent": UA, "Accept-Language": "es-AR,es;q=0.9"}
    h.update(headers or {})
    if isinstance(data, dict):
        data = json.dumps(data).encode()
    elif isinstance(data, str):
        data = data.encode()
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        return r.read(600_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")


# =====================================================================
#  Parámetros comunes
#    geo  = {"lat": .., "lon": .., "radio_m": ..}  (punto y radio elegidos en el mapa) o None
#    todo = True  -> modo "Lo que sea": comercios y empresas de cualquier rubro en la zona
# =====================================================================

# =====================================================================
#  DEMO (para probar sin internet)
# =====================================================================
def buscar_demo(rubro, zona, cfg_rubro, cfg, geo=None, todo=False):
    archivo = ruta("app/demo_lugares.json")
    if not archivo.exists():
        archivo = ruta("datos/demo_lugares.json")
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    z = normalizar(zona)
    consultas = cfg_rubro.get("consultas") or expandir(rubro).get("consultas", [])
    claves = [normalizar(rubro)] + [normalizar(q) for q in consultas]
    for l in datos:
        en_zona = not z or z in normalizar(l.get("zona", "")) or normalizar(l.get("zona", "")) in z
        if not en_zona:
            continue
        if todo or normalizar(l.get("rubro", "")) in claves or any(c and c in normalizar(l.get("rubro", "")) for c in claves):
            yield dict(l, fuente="demo", rubro=l.get("rubro") if todo else rubro)


# =====================================================================
#  OPENSTREETMAP (Nominatim + Overpass) — gratis, sin clave
# =====================================================================
def _geocodificar(zona):
    q = urllib.parse.urlencode({"q": f"{zona}, Argentina", "format": "json", "limit": 1})
    res = json.loads(_http(f"https://nominatim.openstreetmap.org/search?{q}"))
    if not res:
        raise RuntimeError(f"No encontré la zona '{zona}' en el mapa")
    return float(res[0]["lat"]), float(res[0]["lon"])


def _centro(zona, geo, cfg):
    if geo and geo.get("lat") is not None:
        return float(geo["lat"]), float(geo["lon"]), int(geo.get("radio_m") or 3000)
    lat, lon = _geocodificar(zona)
    return lat, lon, int(float(cfg["busqueda"].get("radio_km", 4)) * 1000)


def buscar_osm(rubro, zona, cfg_rubro, cfg, geo=None, todo=False):
    lat, lon, radio = _centro(zona, geo, cfg)
    filtros = []
    if todo:
        for k, patron in LO_QUE_SEA["osm_regex"]:
            filtros.append(f'nwr["{k}"~"{patron}"]["name"](around:{radio},{lat},{lon});')
    else:
        etiquetas = list(dict.fromkeys(cfg_rubro.get("osm", []) + expandir(rubro).get("osm", [])))
        for etiqueta in etiquetas:
            k, v = etiqueta.split("=", 1)
            filtros.append(f'nwr["{k}"="{v}"](around:{radio},{lat},{lon});')
        if not filtros:  # texto libre sin etiquetas conocidas: buscar por palabras en el nombre
            palabras = [p for p in normalizar(rubro).split() if len(p) > 3 and p not in ("locales", "tiendas", "empresas")]
            patron = "|".join(palabras) or normalizar(rubro)
            filtros.append(f'nwr["name"~"{patron}",i](around:{radio},{lat},{lon});')
    consulta = f'[out:json][timeout:60];({"".join(filtros)});out center tags 300;'
    res = json.loads(_http("https://overpass-api.de/api/interpreter",
                           data="data=" + urllib.parse.quote(consulta),
                           headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=90))
    elementos = res.get("elements", [])
    def dist(el):
        c = el.get("center") or el
        return distancia_m(lat, lon, c.get("lat", lat), c.get("lon", lon))
    for el in sorted(elementos, key=dist):    # los más cercanos primero
        t = el.get("tags", {})
        nombre = t.get("name")
        if not nombre:
            continue
        calle = " ".join(x for x in (t.get("addr:street", ""), t.get("addr:housenumber", "")) if x)
        localidad = t.get("addr:city") or t.get("addr:suburb") or zona
        tipo = t.get("shop") or t.get("amenity") or t.get("office") or t.get("craft") or ""
        c = el.get("center") or el
        yield {
            "nombre": nombre,
            "rubro": (tipo.replace("_", " ") if todo else rubro) or rubro,
            "direccion": ", ".join(x for x in (calle, localidad) if x),
            "zona": zona,
            "web": t.get("website") or t.get("contact:website") or t.get("url") or "",
            "email": t.get("email") or t.get("contact:email") or "",
            "telefono": t.get("phone") or t.get("contact:phone") or t.get("contact:mobile") or "",
            "whatsapp": t.get("contact:whatsapp") or "",
            "instagram": t.get("contact:instagram") or "",
            "facebook": t.get("contact:facebook") or "",
            "fuente": "osm",
            "fuente_id": f"osm:{el['type']}/{el['id']}",
            "lat": c.get("lat"), "lon": c.get("lon"),
        }


# =====================================================================
#  GOOGLE PLACES API (New) — Text Search (por intención) y Nearby Search ("lo que sea")
# =====================================================================
MASCARA = ("places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
           "places.internationalPhoneNumber,places.websiteUri,places.businessStatus,places.location,"
           "places.primaryTypeDisplayName")


def _google(endpoint, cuerpo, clave, mascara=MASCARA):
    return json.loads(_http(f"https://places.googleapis.com/v1/places:{endpoint}", data=cuerpo, headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": clave, "X-Goog-FieldMask": mascara}))


def _lugar_google(p, rubro, zona, todo):
    loc = p.get("location", {})
    tipo = (p.get("primaryTypeDisplayName") or {}).get("text", "")
    return {
        "nombre": p.get("displayName", {}).get("text", ""),
        "rubro": (tipo or rubro) if todo else rubro,
        "direccion": p.get("formattedAddress", ""),
        "zona": zona,
        "web": p.get("websiteUri", ""),
        "telefono": p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber", ""),
        "fuente": "google",
        "fuente_id": "google:" + p.get("id", ""),
        "lat": loc.get("latitude"), "lon": loc.get("longitude"),
    }


def buscar_google(rubro, zona, cfg_rubro, cfg, geo=None, todo=False):
    clave = (cfg.get("_secretos") or {}).get("GOOGLE_PLACES_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
    if not clave:
        raise RuntimeError("Falta la clave de Google Places: cargala en Configuración y CVs")
    vistos = set()
    if todo or geo:
        lat, lon, radio = _centro(zona, geo, cfg)
        radio = max(100, min(radio, 50000))
    if todo:
        for grupo in LO_QUE_SEA["grupos_google"]:
            try:
                res = _google("searchNearby", {
                    "includedTypes": grupo, "maxResultCount": 20, "rankPreference": "DISTANCE",
                    "languageCode": "es", "regionCode": "AR",
                    "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(radio)}},
                }, clave)
            except Exception as e:
                print(f"   ⚠️  Un grupo de rubros falló ({e}); sigo con el resto")
                continue
            for p in res.get("places", []):
                if p.get("businessStatus") == "CLOSED_PERMANENTLY" or p.get("id") in vistos:
                    continue
                vistos.add(p.get("id"))
                yield _lugar_google(p, rubro, zona, todo=True)
        return

    consultas = cfg_rubro.get("consultas") or expandir(rubro)["consultas"] or [rubro]
    print(f"   Búsquedas: {' · '.join(consultas)}")
    for consulta in consultas:
        cuerpo = {"textQuery": consulta if geo else (consulta if zona.lower() in consulta.lower() else f"{consulta} en {zona}"),
                  "languageCode": "es", "regionCode": "AR", "pageSize": 20}
        if geo:
            cuerpo["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(radio)}}
        try:
            res = _google("searchText", cuerpo, clave)
        except Exception as e:
            print(f"   ⚠️  «{consulta}» falló ({e})")
            continue
        for p in res.get("places", []):
            if p.get("businessStatus") == "CLOSED_PERMANENTLY" or p.get("id") in vistos:
                continue
            loc = p.get("location", {})
            if geo and loc and distancia_m(lat, lon, loc.get("latitude"), loc.get("longitude")) > radio * 1.15:
                continue   # el sesgo de ubicación no es un límite estricto: filtramos por el radio elegido
            vistos.add(p.get("id"))
            yield _lugar_google(p, rubro, zona, todo=False)


def probar_google(clave: str) -> str:
    res = _google("searchText", {"textQuery": "kiosco en Lomas de Zamora", "pageSize": 1}, clave, "places.id")
    return f"Clave válida ✓ (respondió con {len(res.get('places', []))} resultado de prueba)"


FUENTES = {"demo": buscar_demo, "osm": buscar_osm, "google": buscar_google}


# =====================================================================
#  ENRIQUECIMIENTO: visitar la web del lugar y buscar contactos públicos
# =====================================================================
RE_IG = re.compile(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?", re.I)
RE_FB = re.compile(r"https?://(?:www\.|m\.)?facebook\.com/([A-Za-z0-9_.\-]+)/?", re.I)
RE_WA = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp\.com/send\?phone=)\+?(\d{10,15})", re.I)
IG_IGNORAR = {"p", "reel", "explore", "accounts", "stories", "sharer", "share"}
FB_IGNORAR = {"sharer", "sharer.php", "share", "tr", "plugins", "dialog", "groups"}


def enriquecer(l: dict, pausa=1.5) -> dict:
    web = (l.get("web") or "").strip()
    if not web:
        return l
    if "instagram.com" in web:
        l.setdefault("instagram", "")
        l["instagram"] = l["instagram"] or web
        return l
    if "facebook.com" in web:
        l["facebook"] = l.get("facebook") or web
        return l
    if not web.startswith("http"):
        web = "https://" + web
    paginas = [web]
    base = web.rstrip("/")
    for sufijo in ("/contacto", "/contact", "/contactanos"):
        paginas.append(base + sufijo)
    for i, url in enumerate(paginas):
        try:
            html = _http(url, timeout=12)
        except Exception:
            if i == 0:
                break   # si la home no responde, no insistimos
            continue
        if not l.get("email"):
            mails = emails_validos(html)
            if mails:
                l["email"] = mails[0]
        if not l.get("instagram"):
            m = next((m for m in RE_IG.finditer(html) if m.group(1).lower() not in IG_IGNORAR), None)
            if m:
                l["instagram"] = f"https://instagram.com/{m.group(1)}"
        if not l.get("facebook"):
            m = next((m for m in RE_FB.finditer(html) if m.group(1).lower() not in FB_IGNORAR), None)
            if m:
                l["facebook"] = f"https://facebook.com/{m.group(1)}"
        if not l.get("whatsapp"):
            m = RE_WA.search(html)
            if m:
                l["whatsapp"] = m.group(1)
        time.sleep(pausa)
        if l.get("email"):
            break
    return l
