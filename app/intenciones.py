"""Búsqueda por intención: convierte lo que escribís ("atención al cliente", "depósito", "anime"…)
en varias búsquedas concretas para Google Places / OpenStreetMap, y elige un gancho acorde.

Para sumar una intención nueva, agregá un bloque a INTENCIONES: palabras clave → consultas.
"""
from .util import normalizar

INTENCIONES = [
    {
        "claves": ["atencion al cliente", "atencion al publico", "ventas", "vendedor", "vendedora", "cajero", "cajera",
                   "empleado de comercio", "repositor", "repositora"],
        "consultas": ["tiendas y locales comerciales", "local de ropa", "supermercado", "farmacia", "kiosco y almacén"],
        "osm": ["shop=clothes", "shop=supermarket", "shop=convenience", "amenity=pharmacy", "shop=shoes", "shop=department_store"],
        "gancho": "Me gusta atender gente, tengo paciencia y me adapto rápido a cómo trabaja cada lugar",
    },
    {
        "claves": ["deposito", "logistica", "almacen", "operario", "operaria", "carga y descarga", "picking", "distribuidora", "mayorista"],
        "consultas": ["depósito", "centro de distribución y logística", "distribuidora mayorista", "supermercado mayorista"],
        "osm": ["shop=wholesale", "industrial=warehouse", "building=warehouse", "office=logistics", "amenity=post_depot"],
        "gancho": "No tengo problema con el trabajo físico ni con los turnos rotativos, y soy de los que llegan a horario",
    },
    {
        "claves": ["gastronomia", "mozo", "moza", "camarero", "camarera", "cocina", "cocinero", "cocinera", "bachero", "bachera",
                   "ayudante de cocina", "barista", "delivery", "restaurante", "resto"],
        "consultas": ["restaurante", "bar", "cafetería", "pizzería", "parrilla", "hamburguesería"],
        "osm": ["amenity=restaurant", "amenity=bar", "amenity=cafe", "amenity=fast_food", "amenity=pub"],
        "gancho": "Me banco bien el ritmo de los días de mucho movimiento y no tengo drama con noches ni fines de semana",
    },
    {
        "claves": ["programacion", "programador", "programadora", "desarrollo", "desarrollador", "desarrolladora", "software",
                   "sistemas", "developer", "frontend", "backend", "full stack", "fullstack", "web", "it"],
        "consultas": ["empresa de desarrollo de software", "consultora de sistemas", "agencia de desarrollo web", "empresa de tecnología"],
        "osm": ["office=it", "office=software", "office=company", "office=telecommunication"],
        "gancho": "Vengo programando hace un tiempo, tengo algunos proyectos hechos y quiero meterme en un equipo donde aprenda de gente con más experiencia",
    },
    {
        "claves": ["soporte", "soporte it", "soporte tecnico", "helpdesk", "help desk", "tecnico en computacion", "reparacion de pc", "redes"],
        "consultas": ["servicio técnico de computadoras", "soporte informático para empresas", "reparación de celulares y computadoras"],
        "osm": ["shop=computer", "craft=electronics_repair", "shop=mobile_phone", "office=it"],
        "gancho": "Sé armar y configurar compus, instalar sistemas y resolver los problemas de siempre que trae la gente",
    },
    {
        "claves": ["tecnologia", "celulares", "computacion", "electronica", "gamer", "videojuegos"],
        "consultas": ["local de celulares y accesorios", "local de computación", "tienda de electrónica", "tienda de videojuegos"],
        "osm": ["shop=electronics", "shop=computer", "shop=mobile_phone", "shop=video_games"],
        "gancho": "Me llevo muy bien con celulares, compus y accesorios, y me sale natural explicarle a alguien qué le conviene",
    },
    {
        "claves": ["anime", "manga", "comics", "comic", "otaku", "coleccionables", "figuras", "juegos de mesa", "cartas"],
        "consultas": ["tienda de anime", "comiquería", "tienda de coleccionables y figuras", "tienda de juegos de mesa y cartas"],
        "osm": ["shop=anime", "shop=comics", "shop=games", "shop=collector", "shop=toys"],
        "gancho": "Miro anime y leo manga hace años, así que conozco bastante lo que se vende y lo que busca la gente que entra",
    },
    {
        "claves": ["administrativo", "administrativa", "recepcion", "recepcionista", "secretaria", "secretario", "data entry", "oficina"],
        "consultas": ["estudio contable", "inmobiliaria", "consultorio médico", "estudio jurídico", "oficinas administrativas"],
        "osm": ["office=accountant", "office=estate_agent", "office=lawyer", "amenity=clinic", "office=insurance"],
        "gancho": "Soy ordenado con los papeles y los horarios, manejo bien la compu y me gusta que las cosas salgan prolijas",
    },
    {
        "claves": ["limpieza", "maestranza", "mantenimiento"],
        "consultas": ["empresa de limpieza", "hotel", "gimnasio", "colegio privado"],
        "osm": ["office=cleaning", "tourism=hotel", "leisure=fitness_centre"],
        "gancho": "Soy responsable, cumplo horarios y no me asusta el trabajo pesado",
    },
    {
        "claves": ["cafeteria", "cafe"],
        "consultas": ["cafetería", "panadería y confitería", "heladería"],
        "osm": ["amenity=cafe", "shop=bakery", "amenity=ice_cream"],
        "gancho": "Me gusta atender al público y trabajar a buen ritmo, sobre todo en los horarios de más movimiento",
    },
    {
        "claves": ["bar", "bares", "cerveceria", "boliche", "noche"],
        "consultas": ["bar", "cervecería", "pub"],
        "osm": ["amenity=bar", "amenity=pub", "amenity=biergarten", "amenity=nightclub"],
        "gancho": "No tengo drama con trabajar de noche o los fines de semana, y me muevo bien cuando el lugar se llena",
    },
]

LO_QUE_SEA = {
    "etiqueta": "lo que sea",
    "gancho": "Tengo muchas ganas de trabajar, aprendo rápido y me adapto a lo que haga falta",
    # Tipos de Google Places (Nearby Search), en grupos chicos: si uno falla, los otros siguen
    "grupos_google": [
        ["clothing_store", "shoe_store", "electronics_store", "cell_phone_store", "book_store", "jewelry_store",
         "furniture_store", "home_goods_store", "hardware_store", "pet_store", "sporting_goods_store", "gift_shop",
         "department_store"],
        ["restaurant", "cafe", "bar", "bakery", "fast_food_restaurant", "pizza_restaurant", "ice_cream_shop", "meal_takeaway"],
        ["supermarket", "grocery_store", "convenience_store", "pharmacy", "liquor_store"],
        ["gym", "beauty_salon", "hair_care", "car_repair", "car_wash", "veterinary_care", "laundry",
         "real_estate_agency", "insurance_agency", "accounting", "travel_agency"],
    ],
    "osm_regex": [("shop", ".*"), ("amenity", "restaurant|cafe|bar|pub|fast_food|ice_cream|pharmacy"), ("office", ".*"), ("craft", ".*")],
}

GANCHO_GENERICO = "Tengo muchas ganas de trabajar y aprendo rápido"


def _coincide(texto_n: str, clave: str) -> bool:
    clave_n = normalizar(clave)
    if len(clave_n) <= 3:   # claves cortas ("it", "bar") solo como palabra entera
        return clave_n in texto_n.split()
    return clave_n in texto_n


def detectar(texto: str) -> list[dict]:
    """Intenciones que aparecen en el texto, la coincidencia más específica primero."""
    t = normalizar(texto)
    halladas = []
    for i in INTENCIONES:
        largo = max((len(normalizar(c)) for c in i["claves"] if _coincide(t, c)), default=0)
        if largo:
            halladas.append((largo, i))
    return [i for _, i in sorted(halladas, key=lambda x: -x[0])]


def _clave(q: str) -> str:
    def singular(w):
        if len(w) > 4 and w.endswith("es") and w[-3] in "rlndz":
            return w[:-2]
        return w[:-1] if w.endswith("s") and len(w) > 3 else w
    return " ".join(singular(w) for w in normalizar(q).split())


def expandir(texto: str, cfg_rubros: dict | None = None, max_consultas: int = 4) -> dict:
    """Devuelve {consultas, osm, gancho} para un texto libre.

    Orden de prioridad: rubro configurado igual al texto → intenciones detectadas → el texto tal cual.
    """
    texto = (texto or "").strip()
    consultas, osm, gancho = [], [], None
    for nombre, r in (cfg_rubros or {}).items():
        if normalizar(nombre) == normalizar(texto):
            q = r.get("google_query", nombre).replace(" en {zona}", "").replace("{zona}", "").strip()
            consultas.append(q)
            osm += r.get("osm", [])
            gancho = r.get("gancho")
            break
    intenciones = detectar(texto)
    for i in intenciones:
        consultas += i["consultas"]
        osm += i["osm"]
        gancho = gancho or i["gancho"]
    vistas, finales = set(), []
    for q in consultas:
        if _clave(q) not in vistas:
            vistas.add(_clave(q))
            finales.append(q)
    finales = finales[: max_consultas - 1] if texto else finales[:max_consultas]
    if texto and _clave(texto) not in vistas:   # el texto tal cual, al final (puede ser un puesto, no un comercio)
        finales.append(texto)
    return {"consultas": finales[:max_consultas], "osm": list(dict.fromkeys(osm)), "gancho": gancho or GANCHO_GENERICO,
            "detectado": [i["consultas"][0] for i in intenciones]}
