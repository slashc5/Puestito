"""Funciones auxiliares: normalización de textos, teléfonos y claves de duplicados."""
import re
import unicodedata
from urllib.parse import urlparse


def sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def normalizar(s: str) -> str:
    s = sin_acentos(s).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def clave_lugar(nombre: str, direccion: str = "") -> str:
    """Clave para detectar duplicados: nombre + calle/número normalizados."""
    # nos quedamos con la calle y altura (primer tramo antes de la coma)
    dir_n = normalizar((direccion or "").split(",")[0])
    return f"{normalizar(nombre)}|{dir_n}"


_RELLENO = {"de", "del", "la", "el", "los", "las", "y", "bar", "cafe", "tienda", "local", "sa", "srl", "demo"}


def nombre_parecido(a: str, b: str) -> bool:
    """True si dos nombres de local parecen el mismo (ignora acentos, mayúsculas y palabras de relleno)."""
    ta = {w for w in normalizar(a).split() if w not in _RELLENO}
    tb = {w for w in normalizar(b).split() if w not in _RELLENO}
    if not ta or not tb:
        return normalizar(a) == normalizar(b)
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.6


def misma_altura(dir_a: str, dir_b: str) -> bool:
    """False solo si las dos direcciones tienen altura (número de calle) y es distinta: son sucursales distintas."""
    na = re.findall(r"\b(\d{2,5})\b", (dir_a or "").split(",")[0])
    nb = re.findall(r"\b(\d{2,5})\b", (dir_b or "").split(",")[0])
    return not (na and nb) or na[0] == nb[0]


def dominio(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def solo_digitos(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def telefono_whatsapp_ar(tel: str) -> str:
    """Convierte un teléfono argentino al formato internacional de WhatsApp: 549 + área + número.

    Ej: "011 15-2345-6789" -> "5491123456789"; "+54 9 11 2345-6789" -> "5491123456789".
    Devuelve "" si no se puede interpretar.
    """
    d = solo_digitos(tel)
    if not d:
        return ""
    if d.startswith("549") and len(d) == 13:
        return d
    if d.startswith("54"):
        d = d[2:]
        if d.startswith("9"):
            d = d[1:]
    d = d.lstrip("0")
    if len(d) == 12:  # tiene el "15" del celular metido después del código de área
        candidatos = [2] if d.startswith("11") else [4, 3, 2]
        for i in candidatos:
            if d[i:i + 2] == "15":
                d = d[:i] + d[i + 2:]
                break
    if len(d) == 8:  # número local de AMBA sin código de área
        d = "11" + d
    if len(d) != 10:
        return ""
    return "549" + d


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_BASURA = ("example.", "sentry", "wixpress", "@2x", ".png", ".jpg", ".webp", ".gif", "domain.com", "email.com")


def emails_validos(texto: str) -> list[str]:
    vistos = []
    for e in EMAIL_RE.findall(texto or ""):
        e = e.strip(".").lower()
        if any(b in e for b in EMAIL_BASURA):
            continue
        if e not in vistos:
            vistos.append(e)
    return vistos


def distancia_m(lat1, lon1, lat2, lon2) -> float:
    """Distancia en metros entre dos coordenadas (fórmula de haversine)."""
    import math
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar(s)).strip("-")
