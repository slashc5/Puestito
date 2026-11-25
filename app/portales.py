"""Portales de empleo: arma búsquedas listas para abrir (LinkedIn, Computrabajo, Indeed y Google Empleos).

No se automatiza nada dentro de los portales (ni scraping ni clics de postulación): solo se generan
los links con filtros útiles y se lleva registro de qué abriste y a qué te postulaste.
"""
import urllib.parse

from .util import normalizar, slug

# Localidades del Gran Buenos Aires que Computrabajo reconoce como ciudad dentro de "buenos-aires-gba"
GBA = {
    "lomas de zamora", "temperley", "banfield", "adrogue", "lanus", "avellaneda", "quilmes", "berazategui",
    "florencio varela", "almirante brown", "burzaco", "longchamps", "ezeiza", "esteban echeverria", "monte grande",
    "la matanza", "san justo", "moron", "ramos mejia", "merlo", "moreno", "ituzaingo", "hurlingham", "tres de febrero",
    "san martin", "vicente lopez", "san isidro", "tigre", "san fernando", "pilar", "escobar", "jose c paz",
    "malvinas argentinas", "san miguel", "castelar", "haedo", "caseros", "olivos", "martinez", "wilde", "bernal",
}
# Barrios que en Computrabajo se agrupan bajo su partido
PARTIDO = {"temperley": "lomas de zamora", "banfield": "lomas de zamora", "burzaco": "almirante brown",
           "longchamps": "almirante brown", "monte grande": "esteban echeverria", "wilde": "avellaneda",
           "bernal": "quilmes", "ramos mejia": "la matanza", "san justo": "la matanza", "castelar": "moron",
           "haedo": "moron", "caseros": "tres de febrero", "olivos": "vicente lopez", "martinez": "san isidro"}
CABA = {"caba", "capital", "capital federal", "ciudad de buenos aires", "ciudad autonoma de buenos aires"}

PORTALES = {
    "linkedin": "LinkedIn",
    "computrabajo": "Computrabajo",
    "indeed": "Indeed",
    "google": "Google Empleos",
}


def _computrabajo_lugar(ubicacion: str) -> str:
    u = normalizar(ubicacion).split(",")[0].strip()
    if not u:
        return ""
    if u in CABA:
        return "-en-capital-federal"
    u = PARTIDO.get(u, u)
    if u in GBA:
        return f"-en-buenos-aires-gba-en-{slug(u)}"
    return f"-en-{slug(u)}"


def links(puesto: str, ubicacion: str = "", dias: int = 7, remoto: bool = False) -> dict:
    """Devuelve {portal: url} con los filtros aplicados."""
    puesto = puesto.strip()
    dias = max(1, int(dias or 7))
    q = urllib.parse.quote
    kw_extra = " remoto" if remoto else ""

    li = {"keywords": puesto, "f_TPR": f"r{dias * 86400}", "sortBy": "DD"}
    if ubicacion:
        li["location"] = ubicacion + ", Argentina" if "argentina" not in ubicacion.lower() else ubicacion
        li["distance"] = "25"
    else:
        li["location"] = "Argentina"
    if remoto:
        li["f_WT"] = "2"

    ind = {"q": puesto + kw_extra, "sort": "date", "fromage": str(min(dias, 14))}
    if ubicacion:
        ind["l"] = ubicacion
        ind["radius"] = "25"

    # Computrabajo filtra por fecha con pubdate (1 = hoy, 3 = últimos 3 días, 7 = última semana)
    pub = 1 if dias <= 1 else 3 if dias <= 3 else 7
    ct = f"https://ar.computrabajo.com/trabajo-de-{slug(puesto + kw_extra)}{_computrabajo_lugar(ubicacion)}?pubdate={pub}"

    goo = {"q": f"empleo {puesto}{kw_extra} {ubicacion}".strip(), "ibp": "htl;jobs"}

    return {
        "linkedin": "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(li, quote_via=q),
        "computrabajo": ct,
        "indeed": "https://ar.indeed.com/jobs?" + urllib.parse.urlencode(ind, quote_via=q),
        "google": "https://www.google.com/search?" + urllib.parse.urlencode(goo, quote_via=q),
    }


def normalizar_url(url: str) -> str:
    """Clave para no guardar dos veces la misma oferta: saca parámetros de rastreo y deja el id del aviso."""
    url = url.strip()
    p = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    host = p.netloc.lower().removeprefix("www.").removeprefix("m.")
    qs = urllib.parse.parse_qs(p.query)
    conservar = {k: qs[k] for k in ("jk", "vjk", "currentJobId", "oferta", "id") if k in qs}
    if "linkedin.com" in host and "currentJobId" in conservar:
        return f"linkedin.com/jobs/view/{conservar['currentJobId'][0]}"
    if "indeed." in host and ("jk" in conservar or "vjk" in conservar):
        return f"indeed/{(conservar.get('jk') or conservar.get('vjk'))[0]}"
    ruta = p.path.rstrip("/")
    extra = ("?" + urllib.parse.urlencode(conservar, doseq=True)) if conservar else ""
    return f"{host}{ruta}{extra}".lower()


def portal_de(url: str) -> str:
    h = urllib.parse.urlparse(url if "://" in url else "https://" + url).netloc.lower()
    for k, n in (("linkedin", "LinkedIn"), ("computrabajo", "Computrabajo"), ("indeed", "Indeed"),
                 ("bumeran", "Bumeran"), ("zonajobs", "ZonaJobs"), ("google", "Google")):
        if k in h:
            return n
    return h.removeprefix("www.")
