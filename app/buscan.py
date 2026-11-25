"""Modo «Lugares que buscan gente».

Busca comercios y empresas de una categoría en la zona y revisa sus webs buscando señales de que
están contratando: secciones «Trabajá con nosotros», frases como «envianos tu CV» o «buscamos
personal», formularios de RRHH o mails del tipo rrhh@ / empleos@ / cv@.

Los avisos en portales (LinkedIn, Computrabajo, Indeed, Google Empleos) no se leen automáticamente
(sus condiciones lo prohíben y bloquean a quien lo hace): se generan las búsquedas de los últimos días
y se guardan para abrirlas con un clic.
"""
import re
import time
import urllib.parse

from .fuentes import RE_FB, RE_IG, RE_WA, FB_IGNORAR, IG_IGNORAR, _http
from .util import emails_validos, normalizar

CATEGORIAS = {
    "atencion": {"nombre": "Atención al cliente", "texto": "atención al cliente", "puesto": "atención al cliente",
                 "consultas": ["tiendas y locales comerciales", "supermercado", "farmacia", "atención al cliente"],
                 "osm": ["shop=clothes", "shop=supermarket", "shop=convenience", "amenity=pharmacy", "shop=department_store"]},
    "it": {"nombre": "Soporte IT / Técnico", "texto": "soporte IT", "puesto": "soporte técnico IT",
           "consultas": ["servicio técnico de computadoras", "empresa de tecnología", "soporte informático para empresas",
                         "reparación de celulares"],
           "osm": ["shop=computer", "craft=electronics_repair", "shop=mobile_phone", "office=it", "office=telecommunication"]},
    "ventas": {"nombre": "Ventas / Local comercial", "texto": "ventas local comercial", "puesto": "vendedor",
               "consultas": ["local de ropa", "local de celulares y accesorios", "tienda de electrónica", "zapatería"],
               "osm": ["shop=clothes", "shop=shoes", "shop=electronics", "shop=mobile_phone", "shop=sports"]},
    "gastro": {"nombre": "Gastronomía", "texto": "gastronomía", "puesto": "mozo cocina gastronomía",
               "consultas": ["restaurante", "bar", "cafetería", "pizzería"],
               "osm": ["amenity=restaurant", "amenity=bar", "amenity=cafe", "amenity=fast_food"]},
    "admin": {"nombre": "Administración / Depósito", "texto": "administrativo depósito", "puesto": "administrativo depósito",
              "consultas": ["estudio contable", "distribuidora mayorista", "depósito", "centro de distribución y logística"],
              "osm": ["office=accountant", "office=company", "shop=wholesale", "industrial=warehouse"]},
}

# Frases que indican búsqueda de personal (se comparan sin acentos ni mayúsculas)
FRASES = [
    "trabaja con nosotros", "trabaje con nosotros", "sumate al equipo", "sumate a nuestro equipo", "unite al equipo",
    "unite a nuestro equipo", "buscamos personal", "estamos buscando", "estamos contratando", "busqueda laboral",
    "busquedas laborales", "busquedas vigentes", "envianos tu cv", "envia tu cv", "enviar tu cv", "envie su cv",
    "dejanos tu cv", "deja tu cv", "carga tu cv", "cargar cv", "subi tu cv", "manda tu cv", "postulate",
    "postulaciones", "oportunidades laborales", "bolsa de trabajo", "recursos humanos", "seleccion de personal",
    "vacantes", "se busca", "se necesita", "work with us", "join our team", "we are hiring", "careers",
]
# Palabras que, en un link (texto o dirección), apuntan a una sección de empleo
LINKS_EMPLEO = ["trabaja con nosotros", "trabaja-con-nosotros", "trabajaconnosotros", "trabaje con nosotros", "empleo",
                "empleos", "rrhh", "recursos humanos", "careers", "carreras", "sumate", "postulate", "vacantes",
                "busquedas", "trabaja", "unite", "jobs", "join"]
PREFIJOS_RRHH = ("rrhh", "recursoshumanos", "empleo", "empleos", "trabajo", "trabajaconnosotros", "cv", "curriculum",
                 "curriculums", "seleccion", "talento", "talentos", "jobs", "careers", "postulaciones", "busquedas", "personal")

RE_A = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.I | re.S)
RE_TAGS = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>|<[^>]+>", re.I | re.S)


def _texto_plano(html: str) -> str:
    return normalizar(RE_TAGS.sub(" ", html))


def _contexto(texto_n: str, frase: str, ancho=70) -> str:
    i = texto_n.find(frase)
    if i < 0:
        return frase
    ini, fin = max(0, i - ancho), min(len(texto_n), i + len(frase) + ancho)
    return ("…" if ini else "") + texto_n[ini:fin].strip() + ("…" if fin < len(texto_n) else "")


def detectar_empleo(web: str, pausa: float = 1.0, max_paginas: int = 3) -> dict:
    """Revisa la web de un lugar y devuelve {puntaje 0-100, senal, url_empleo, email, instagram, facebook, whatsapp}."""
    res = {"puntaje": 0, "senal": "", "url_empleo": "", "email": "", "email_rrhh": "", "instagram": "", "facebook": "", "whatsapp": ""}
    web = (web or "").strip()
    if not web or any(x in web for x in ("instagram.com", "facebook.com", "wa.me", "linktr.ee")):
        return res
    if not web.startswith("http"):
        web = "https://" + web
    base = urllib.parse.urlparse(web)
    try:
        html = _http(web, timeout=12)
    except Exception:
        return res
    paginas = [(web, html)]
    # links internos que parecen sección de empleo o contacto
    candidatos = []
    for href, texto in RE_A.findall(html):
        destino = urllib.parse.urljoin(web, href.strip())
        u = urllib.parse.urlparse(destino)
        if u.scheme not in ("http", "https") or u.netloc.replace("www.", "") != base.netloc.replace("www.", ""):
            continue
        clave = normalizar(_texto_plano(texto) + " " + u.path.replace("-", " ").replace("_", " "))
        if any(k in clave for k in LINKS_EMPLEO):
            candidatos.insert(0, destino)       # las de empleo primero
        elif "contacto" in clave or "contact" in clave:
            candidatos.append(destino)
    vistos = {web}
    for destino in candidatos:
        if len(paginas) > max_paginas or destino in vistos:
            continue
        vistos.add(destino)
        time.sleep(pausa)
        try:
            paginas.append((destino, _http(destino, timeout=12)))
        except Exception:
            continue

    puntos, frases_halladas, senal_de_seccion = 0, [], False
    for url, h in paginas:
        es_seccion = url != web
        # en la portada no cuentan los textos de los links (un menú con «Trabajá con nosotros» no es una búsqueda activa)
        texto = _texto_plano(h if es_seccion else RE_A.sub(" ", h))
        halladas = [f for f in FRASES if f in texto]
        if halladas:
            puntos += 45 if es_seccion else 25
            if es_seccion and not res["url_empleo"]:
                res["url_empleo"] = url
            if not res["senal"] or (es_seccion and not senal_de_seccion):
                res["senal"] = _contexto(texto, halladas[0])
                senal_de_seccion = es_seccion
            frases_halladas += halladas
        for e in emails_validos(h):
            if e.split("@")[0].replace(".", "").replace("-", "") in PREFIJOS_RRHH or e.split("@")[0].startswith(PREFIJOS_RRHH):
                res["email_rrhh"] = res["email_rrhh"] or e
            res["email"] = res["email"] or e
        if not res["instagram"]:
            m = next((m for m in RE_IG.finditer(h) if m.group(1).lower() not in IG_IGNORAR), None)
            if m:
                res["instagram"] = f"https://instagram.com/{m.group(1)}"
        if not res["facebook"]:
            m = next((m for m in RE_FB.finditer(h) if m.group(1).lower() not in FB_IGNORAR), None)
            if m:
                res["facebook"] = f"https://facebook.com/{m.group(1)}"
        if not res["whatsapp"]:
            m = RE_WA.search(h)
            if m:
                res["whatsapp"] = m.group(1)
    if res["email_rrhh"]:
        puntos += 35
        res["senal"] = res["senal"] or f"Tiene un mail de selección: {res['email_rrhh']}"
    if res["url_empleo"] and not frases_halladas:
        puntos += 20
    res["puntaje"] = min(100, puntos)
    return res


def senal_demo(l: dict) -> dict:
    """En la fuente demo no hay internet: usa la señal de ejemplo guardada en los datos de prueba."""
    s = l.get("demo_senal") or {}
    return {"puntaje": s.get("puntaje", 0), "senal": s.get("senal", ""), "url_empleo": s.get("url", ""),
            "email": "", "email_rrhh": s.get("email_rrhh", ""), "instagram": "", "facebook": "", "whatsapp": ""}
