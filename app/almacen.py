"""Dónde se guardan la configuración, las plantillas, los CVs y las credenciales de cada persona.

- AlmacenArchivos: la versión de siempre, en tu PC (config/*.toml, plantillas/*.txt, cvs/*.pdf, .env).
- AlmacenDB: la versión web. Todo va a la base de datos del usuario (su propio esquema o archivo):
    · configuración y plantillas → tabla «ajustes»
    · CVs (el PDF completo) → tabla «archivos»  (no depende del disco del servidor, que se borra al reiniciar)
    · credenciales → tabla «ajustes», cifradas con SECRET_KEY
"""
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from .config import RAIZ, cargar_env, ruta

CLAVES_SECRETAS = ["MAIL_USUARIO", "MAIL_PASSWORD", "GOOGLE_PLACES_API_KEY"]


def _toml(archivo: Path) -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover
        import tomli as tomllib
    with open(archivo, "rb") as f:
        return tomllib.load(f)


def _rel_cv(nombre: str) -> str:
    return f"cvs/{Path(nombre).name}"


# =====================================================================
#  Versión local: archivos en la carpeta del proyecto
# =====================================================================
class AlmacenArchivos:
    web = False

    def leer_general(self) -> dict:
        cfg = ruta("config/config.toml")
        if not cfg.exists() and ruta("config/config.ejemplo.toml").exists():
            cfg.write_text(ruta("config/config.ejemplo.toml").read_text(encoding="utf-8"), encoding="utf-8")
        return _toml(cfg)

    def leer_perfiles(self) -> dict:
        return _toml(ruta("config/perfiles.toml"))

    def guardar_general(self, general: dict):
        from .ajustes import texto_config, escribir_con_respaldo
        escribir_con_respaldo(ruta("config/config.toml"), texto_config(general))

    def guardar_perfiles(self, perfiles: dict, rubros: dict):
        from .ajustes import texto_perfiles, escribir_con_respaldo
        escribir_con_respaldo(ruta("config/perfiles.toml"), texto_perfiles(perfiles, rubros))

    # ---- plantillas
    def leer_plantilla(self, rel: str) -> str:
        p = ruta(rel)
        return p.read_text(encoding="utf-8") if rel and p.exists() else ""

    def existe_plantilla(self, rel: str) -> bool:
        return bool(rel) and ruta(rel).exists()

    def guardar_plantilla(self, rel: str, texto: str):
        from .ajustes import ruta_plantilla, respaldar
        p = ruta_plantilla(rel)
        p.parent.mkdir(exist_ok=True)
        if p.exists():
            respaldar(p)
        p.write_text(texto, encoding="utf-8")

    # ---- CVs
    def _carpeta(self) -> Path:
        c = ruta("cvs")
        c.mkdir(exist_ok=True)
        return c

    def _archivo_cv(self, nombre: str) -> Path:
        p = (self._carpeta() / Path(nombre).name).resolve()
        if p.parent != self._carpeta().resolve():
            raise ValueError("Nombre de archivo no válido")
        return p

    def listar_cvs(self) -> list[dict]:
        out = []
        for p in sorted(self._carpeta().glob("*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True):
            out.append({"archivo": p.name, "ruta": _rel_cv(p.name), "bytes": p.stat().st_size,
                        "modificado": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")})
        return out

    def existe_cv(self, rel: str) -> bool:
        return bool(rel) and self._archivo_cv(rel).exists()

    def leer_cv(self, rel: str) -> tuple[str, bytes]:
        p = self._archivo_cv(rel)
        if not p.exists():
            raise FileNotFoundError(f"No encuentro el CV {Path(rel).name}. Subilo en Configuración y CVs.")
        return p.name, p.read_bytes()

    def guardar_cv(self, nombre: str, datos: bytes, reemplazar=False) -> str:
        destino = self._carpeta() / nombre
        if destino.exists() and not reemplazar:
            n = 2
            while (self._carpeta() / f"{destino.stem}_{n}.pdf").exists():
                n += 1
            destino = self._carpeta() / f"{destino.stem}_{n}.pdf"
        destino.write_bytes(datos)
        return _rel_cv(destino.name)

    def borrar_cv(self, nombre: str):
        p = self._archivo_cv(nombre)
        papelera = self._carpeta() / ".borrados"
        papelera.mkdir(exist_ok=True)
        shutil.move(str(p), papelera / f"{int(time.time())}_{p.name}")

    # ---- credenciales (.env)
    def secretos(self) -> dict:
        cargar_env()
        return {k: os.environ.get(k, "") for k in CLAVES_SECRETAS}

    def guardar_secretos(self, cambios: dict):
        from .ajustes import escribir_con_respaldo
        env = RAIZ / ".env"
        lineas = env.read_text(encoding="utf-8").splitlines() if env.exists() else [
            "# Claves de Postuladorsito. Se editan desde la app. NUNCA subas este archivo a GitHub.", ""]
        hechos = set()
        for i, linea in enumerate(lineas):
            k = linea.split("=", 1)[0].strip()
            if k in cambios and not linea.strip().startswith("#"):
                lineas[i] = f"{k}={cambios[k]}"
                hechos.add(k)
        lineas += [f"{k}={v}" for k, v in cambios.items() if k not in hechos]
        escribir_con_respaldo(env, "\n".join(lineas) + "\n")
        os.environ.update(cambios)

    def borrar_secreto(self, clave: str):
        from .ajustes import escribir_con_respaldo
        env = RAIZ / ".env"
        if env.exists():
            lineas = [l for l in env.read_text(encoding="utf-8").splitlines() if l.split("=", 1)[0].strip() != clave]
            escribir_con_respaldo(env, "\n".join(lineas) + "\n")
        os.environ.pop(clave, None)


# =====================================================================
#  Versión web: base de datos de cada usuario
# =====================================================================
class AlmacenDB:
    web = True

    def __init__(self, uid: int):
        self.uid = int(uid)

    def _con(self):
        from .basedatos import conectar_usuario
        from .db import DB
        return DB(con=conectar_usuario(self.uid), clave_cache=f"u{self.uid}", web=True).con   # asegura las tablas

    def _leer(self, clave: str):
        c = self._con()
        try:
            r = c.execute("SELECT valor FROM ajustes WHERE clave=?", (clave,)).fetchone()
            return r[0] if r else None
        finally:
            c.close()

    def _escribir(self, clave: str, valor: str):
        c = self._con()
        try:
            c.execute("INSERT INTO ajustes(clave, valor) VALUES (?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                      (clave, valor))
            c.commit()
        finally:
            c.close()

    def _borrar(self, clave: str):
        c = self._con()
        try:
            c.execute("DELETE FROM ajustes WHERE clave=?", (clave,))
            c.commit()
        finally:
            c.close()

    # ---- configuración (valores iniciales: los del repositorio, sin datos personales)
    def leer_general(self) -> dict:
        v = self._leer("general")
        if v:
            return json.loads(v)
        general = _toml(ruta("config/config.ejemplo.toml"))
        general["yo"] = {"nombre": "", "telefono": "", "email": "", "zona": "", "linkedin": ""}
        general.setdefault("busqueda", {})["fuente"] = "osm"
        general.setdefault("envio", {})["modo_mail"] = "borrador"
        general.setdefault("cvs", {})["defecto"] = ""
        return general

    def leer_perfiles(self) -> dict:
        v = self._leer("perfiles")
        if v:
            return json.loads(v)
        base = _toml(ruta("config/perfiles.toml"))
        for p in base.get("perfiles", {}).values():
            p["cv"] = ""          # cada persona sube su propio CV
        return base

    def guardar_general(self, general: dict):
        limpio = {k: v for k, v in general.items() if not k.startswith("_")}
        self._escribir("general", json.dumps(limpio, ensure_ascii=False))

    def guardar_perfiles(self, perfiles: dict, rubros: dict):
        self._escribir("perfiles", json.dumps({"perfiles": perfiles, "rubros": rubros}, ensure_ascii=False))

    # ---- plantillas
    def leer_plantilla(self, rel: str) -> str:
        v = self._leer(f"plantilla:{rel}")
        if v is not None:
            return v
        p = ruta(rel)       # plantilla de ejemplo del repositorio
        return p.read_text(encoding="utf-8") if rel and p.exists() and p.parent == ruta("plantillas") else ""

    def existe_plantilla(self, rel: str) -> bool:
        return bool(self.leer_plantilla(rel))

    def guardar_plantilla(self, rel: str, texto: str):
        from .ajustes import ruta_plantilla
        ruta_plantilla(rel)             # valida el nombre
        self._escribir(f"plantilla:{rel}", texto)

    # ---- CVs (el PDF entero se guarda en la base)
    def listar_cvs(self) -> list[dict]:
        c = self._con()
        try:
            filas = c.execute("SELECT nombre, bytes, modificado FROM archivos ORDER BY modificado DESC").fetchall()
        finally:
            c.close()
        return [{"archivo": f["nombre"], "ruta": _rel_cv(f["nombre"]), "bytes": f["bytes"], "modificado": f["modificado"]} for f in filas]

    def existe_cv(self, rel: str) -> bool:
        if not rel:
            return False
        c = self._con()
        try:
            return c.execute("SELECT 1 FROM archivos WHERE nombre=?", (Path(rel).name,)).fetchone() is not None
        finally:
            c.close()

    def leer_cv(self, rel: str) -> tuple[str, bytes]:
        c = self._con()
        try:
            r = c.execute("SELECT nombre, datos FROM archivos WHERE nombre=?", (Path(rel).name,)).fetchone()
        finally:
            c.close()
        if not r:
            raise FileNotFoundError(f"No encuentro el CV {Path(rel).name}. Subilo en Configuración y CVs.")
        return r["nombre"], bytes(r["datos"])

    def guardar_cv(self, nombre: str, datos: bytes, reemplazar=False) -> str:
        existentes = {c["archivo"] for c in self.listar_cvs()}
        if nombre in existentes and not reemplazar:
            base, n = Path(nombre).stem, 2
            while f"{base}_{n}.pdf" in existentes:
                n += 1
            nombre = f"{base}_{n}.pdf"
        c = self._con()
        try:
            c.execute("""INSERT INTO archivos(nombre, datos, bytes, modificado) VALUES (?,?,?,?)
                         ON CONFLICT(nombre) DO UPDATE SET datos=excluded.datos, bytes=excluded.bytes, modificado=excluded.modificado""",
                      (nombre, datos, len(datos), datetime.now().isoformat(timespec="seconds")))
            c.commit()
        finally:
            c.close()
        return _rel_cv(nombre)

    def borrar_cv(self, nombre: str):
        c = self._con()
        try:
            c.execute("DELETE FROM archivos WHERE nombre=?", (Path(nombre).name,))
            c.commit()
        finally:
            c.close()

    # ---- credenciales cifradas
    def secretos(self) -> dict:
        from .seguridad import descifrar
        out = {}
        for k in CLAVES_SECRETAS:
            v = self._leer(f"secreto:{k}")
            out[k] = descifrar(v) if v else ""
        return out

    def guardar_secretos(self, cambios: dict):
        from .seguridad import cifrar
        for k, v in cambios.items():
            if k in CLAVES_SECRETAS:
                self._escribir(f"secreto:{k}", cifrar(v))

    def borrar_secreto(self, clave: str):
        self._borrar(f"secreto:{clave}")


def almacen_actual():
    """El almacén del usuario que se está atendiendo (web) o el de archivos (local)."""
    from .contexto import usuario_actual
    u = usuario_actual()
    return u.almacen if u is not None else AlmacenArchivos()
