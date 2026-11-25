"""Carga de configuración (TOML) y secretos (.env)."""
import os
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # pip install tomli  (Python 3.8-3.10)
    except ModuleNotFoundError:
        sys.exit("Necesitás Python 3.11 o superior (o instalar 'tomli').")

RAIZ = Path(__file__).resolve().parent.parent


def ruta(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else RAIZ / p


def _leer_toml(rel: str) -> dict:
    with open(ruta(rel), "rb") as f:
        return tomllib.load(f)


def cargar_env() -> None:
    """Lee .env (CLAVE=valor) y lo pone en os.environ si no está definido."""
    env = RAIZ / ".env"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def asegurar_archivos():
    """Si falta config.toml (por ejemplo, recién clonado de GitHub), lo crea desde el ejemplo."""
    cfg = RAIZ / "config" / "config.toml"
    ejemplo = RAIZ / "config" / "config.ejemplo.toml"
    if not cfg.exists() and ejemplo.exists():
        cfg.write_text(ejemplo.read_text(encoding="utf-8"), encoding="utf-8")
    for carpeta in ("cvs", "datos", "salidas", "plantillas"):
        (RAIZ / carpeta).mkdir(exist_ok=True)


class Config:
    """Configuración del usuario actual: archivos en tu PC, o su base de datos en la versión web."""
    def __init__(self, almacen=None):
        from .almacen import almacen_actual
        self.almacen = almacen or almacen_actual()
        self.web = self.almacen.web
        if not self.web:
            asegurar_archivos()
            cargar_env()
        self.general = self.almacen.leer_general()
        p = self.almacen.leer_perfiles()
        self.perfiles: dict = p.get("perfiles", {})
        self.rubros: dict = p.get("rubros", {})
        # datos que no se guardan, pero que necesitan las búsquedas, los mensajes y el correo
        self.general["_secretos"] = self.almacen.secretos()
        self.general["_almacen"] = self.almacen

    def __getitem__(self, k):
        return self.general[k]

    def perfil(self, nombre: str) -> dict:
        if nombre not in self.perfiles:
            if self.web:
                raise ValueError(f"El perfil «{nombre}» no existe")
            sys.exit(f"Perfil '{nombre}' no existe. Disponibles: {', '.join(self.perfiles)}")
        return self.perfiles[nombre]

    def rubro(self, nombre: str) -> dict:
        """Datos para buscar y escribir sobre un rubro, aunque sea texto libre ("atención al cliente")."""
        from .intenciones import LO_QUE_SEA, expandir
        from .util import normalizar
        if normalizar(nombre) == LO_QUE_SEA["etiqueta"]:
            return {"consultas": [], "osm": [], "gancho": LO_QUE_SEA["gancho"]}
        exp = expandir(nombre, self.rubros)
        base = next((r for n, r in self.rubros.items() if normalizar(n) == normalizar(nombre)), {})
        return {
            "google_query": base.get("google_query", f"{nombre} en {{zona}}"),
            "consultas": exp["consultas"],
            "osm": list(dict.fromkeys(base.get("osm", []) + exp["osm"])),
            "gancho": base.get("gancho") or exp["gancho"],
        }

    # valores con defecto, para que una config vieja (sin claves nuevas) siga andando
    def busqueda(self, k, defecto=None):
        return self.general.get("busqueda", {}).get(k, defecto)

    def cv_defecto(self) -> str:
        return self.general.get("cvs", {}).get("defecto", "")
