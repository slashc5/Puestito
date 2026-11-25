"""Guardar configuración desde la interfaz (datos, perfiles, plantillas, claves y CVs).

Las funciones de este módulo validan y dan formato; dónde se guarda cada cosa lo decide el almacén
del usuario actual (archivos en tu PC, o la base de datos de cada persona en la versión web).
En la versión local, antes de pisar un archivo se guarda una copia en config/.respaldo/ (las últimas 15).
"""
import base64
import json
import os
import re
import shutil
import smtplib
from datetime import datetime
from pathlib import Path

from .almacen import CLAVES_SECRETAS, almacen_actual
from .config import RAIZ, ruta

RESPALDOS = RAIZ / "config" / ".respaldo"
VARIABLES = ["lugar", "rubro", "zona", "gancho", "mi_nombre", "mi_telefono", "mi_email", "mi_zona",
             "mi_linkedin", "cv_link", "cv_link_texto", "busqueda_activa"]
CLAVES_ENV = CLAVES_SECRETAS
MAX_CV_BYTES = 12 * 1024 * 1024


# ---------------------------------------------------------------- TOML (escritura)
def _clave(k: str) -> str:
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k, ensure_ascii=False)


def _valor(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_valor(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)   # las cadenas JSON son cadenas TOML válidas


def _tabla(nombre: str, datos: dict, comentarios: dict | None = None) -> str:
    lineas = [f"[{nombre}]"]
    ancho = max((len(_clave(k)) for k in datos), default=0)
    for k, v in datos.items():
        if isinstance(v, dict):
            continue
        linea = f"{_clave(k).ljust(ancho)} = {_valor(v)}"
        if comentarios and k in comentarios:
            linea += f"   # {comentarios[k]}"
        lineas.append(linea)
    return "\n".join(lineas)


def respaldar(archivo: Path):
    if not archivo.exists():
        return
    RESPALDOS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archivo, RESPALDOS / f"{archivo.name}.{datetime.now():%Y%m%d_%H%M%S}.bak")
    for v in sorted(RESPALDOS.glob(f"{archivo.name}.*.bak"))[:-15]:
        v.unlink(missing_ok=True)


def escribir_con_respaldo(archivo: Path, texto: str):
    respaldar(archivo)
    tmp = archivo.with_suffix(archivo.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, archivo)   # escritura atómica: nunca queda un archivo a medio escribir


COMENTARIOS_CONFIG = {
    "busqueda": {"fuente": "osm | google | demo", "radio_km": "radio por defecto si no elegís punto en el mapa",
                 "limite": "máximo de lugares por corrida"},
    "envio": {"modo_mail": "borrador | enviar | eml", "canal_preferido": "auto | mail | whatsapp"},
}


def texto_config(general: dict) -> str:
    orden = ["yo", "busqueda", "envio", "cvs", "apariencia", "smtp", "imap"]
    partes = ["# ============================================================",
              "#  Configuración de Postuladorsito",
              "#  Se edita desde la app (Configuración y CVs). Las claves van en .env, no acá.",
              "# ============================================================", ""]
    for sec in orden + [k for k in general if k not in orden]:
        if not sec.startswith("_") and isinstance(general.get(sec), dict):
            partes.append(_tabla(sec, general[sec], COMENTARIOS_CONFIG.get(sec)))
            partes.append("")
    return "\n".join(partes)


def texto_perfiles(perfiles: dict, rubros: dict) -> str:
    partes = ["# ============================================================",
              "#  PERFILES (qué CV y qué plantillas usar) y RUBROS (ganchos por rubro)",
              "#  Se edita desde la app (Configuración y CVs).",
              "# ============================================================", ""]
    for nombre, p in perfiles.items():
        partes += [_tabla(f"perfiles.{_clave(nombre)}", p), ""]
    for nombre, r in rubros.items():
        partes += [_tabla(f"rubros.{_clave(nombre)}", r), ""]
    return "\n".join(partes)


# ---------------------------------------------------------------- configuración
def guardar_config(general: dict):
    almacen_actual().guardar_general({k: v for k, v in general.items() if not k.startswith("_")})


def guardar_perfiles(perfiles: dict, rubros: dict):
    almacen_actual().guardar_perfiles(perfiles, rubros)


# ---------------------------------------------------------------- credenciales
def guardar_env(cambios: dict):
    """Actualiza solo las claves recibidas. Un valor vacío NO borra el existente (para no perder la contraseña)."""
    cambios = {k: v.strip() for k, v in cambios.items() if k in CLAVES_ENV and v is not None and v.strip()}
    if "MAIL_PASSWORD" in cambios:
        cambios["MAIL_PASSWORD"] = cambios["MAIL_PASSWORD"].replace(" ", "")   # se muestra con espacios
    if cambios:
        almacen_actual().guardar_secretos(cambios)
    return list(cambios)


def borrar_clave_env(clave: str):
    if clave in CLAVES_ENV:
        almacen_actual().borrar_secreto(clave)


def estado_credenciales() -> dict:
    s = almacen_actual().secretos()
    clave_g = s.get("GOOGLE_PLACES_API_KEY", "")
    return {
        "mail_usuario": s.get("MAIL_USUARIO", ""),
        "mail_password": bool(s.get("MAIL_PASSWORD")),        # nunca se devuelve la contraseña
        "google": bool(clave_g),
        "google_mascara": ("••••" + clave_g[-4:]) if len(clave_g) > 8 else ("••••" if clave_g else ""),
    }


def probar_gmail(cfg_general: dict, usuario: str = "", password: str = "") -> tuple[bool, str]:
    s = almacen_actual().secretos()
    usuario = (usuario or s.get("MAIL_USUARIO") or cfg_general.get("yo", {}).get("email", "")).strip()
    password = (password or s.get("MAIL_PASSWORD", "")).replace(" ", "")
    if not usuario or not password:
        return False, "Falta el mail o la contraseña de aplicación."
    import imaplib
    i = cfg_general.get("imap", {})
    smtp_cfg = cfg_general.get("smtp", {})
    # 1) IMAP (borradores): funciona también en hostings gratuitos que bloquean SMTP
    try:
        imap = imaplib.IMAP4_SSL(i.get("servidor", "imap.gmail.com"), int(i.get("puerto", 993)), timeout=20)
        imap.login(usuario, password)
        imap.logout()
    except imaplib.IMAP4.error:
        return False, ("Gmail rechazó el acceso. Revisá que sea la contraseña de aplicación de 16 letras "
                       "(no tu contraseña normal) y que la verificación en 2 pasos esté activa.")
    except OSError as e:
        return False, f"No pude conectarme a Gmail: {e}"
    # 2) SMTP (envío directo): en algunos hostings gratuitos está bloqueado
    try:
        with smtplib.SMTP(smtp_cfg.get("servidor", "smtp.gmail.com"), int(smtp_cfg.get("puerto", 587)), timeout=12) as smtp:
            smtp.starttls()
            smtp.login(usuario, password)
        return True, f"Conexión OK ✓ Gmail aceptó el acceso de {usuario}: podés dejar borradores y enviar directo."
    except smtplib.SMTPAuthenticationError:
        return False, "Gmail aceptó los borradores pero rechazó el envío directo. Revisá la contraseña de aplicación."
    except (OSError, smtplib.SMTPException):
        return True, (f"Conexión OK ✓ para borradores ({usuario}). El envío directo no está disponible en este "
                      "servidor (el hosting gratuito bloquea SMTP): usá «Borradores en Gmail» y mandalos desde tu Gmail.")


# ---------------------------------------------------------------- CVs
def nombre_seguro(nombre: str) -> str:
    base = Path(nombre).stem
    base = re.sub(r"[^\w\-]+", "_", base, flags=re.UNICODE).strip("_")[:60] or "CV"
    return base + ".pdf"


def guardar_cv(nombre: str, datos_b64: str, reemplazar=False) -> str:
    if "," in datos_b64[:100]:
        datos_b64 = datos_b64.split(",", 1)[1]          # quita "data:application/pdf;base64,"
    datos = base64.b64decode(datos_b64)
    if len(datos) > MAX_CV_BYTES:
        raise ValueError("El PDF supera los 12 MB")
    if not datos.startswith(b"%PDF"):
        raise ValueError("El archivo no es un PDF válido")
    return almacen_actual().guardar_cv(nombre_seguro(nombre), datos, reemplazar)


def listar_cvs(perfiles: dict, defecto: str) -> list[dict]:
    out = []
    for c in almacen_actual().listar_cvs():
        out.append(dict(c, perfiles=[n for n, pf in perfiles.items() if pf.get("cv") == c["ruta"]], defecto=c["ruta"] == defecto))
    return out


def leer_cv(archivo: str) -> tuple[str, bytes]:
    return almacen_actual().leer_cv(f"cvs/{Path(archivo).name}")


def borrar_cv(archivo: str):
    almacen_actual().borrar_cv(Path(archivo).name)


# ---------------------------------------------------------------- plantillas
def ruta_plantilla(rel: str) -> Path:
    p = ruta(rel).resolve()
    if p.parent != ruta("plantillas").resolve() or p.suffix != ".txt":
        raise ValueError("Las plantillas tienen que estar en la carpeta plantillas/ y terminar en .txt")
    return p


def validar_plantilla(texto: str) -> list[str]:
    """Devuelve avisos: llaves mal cerradas o variables que no existen."""
    avisos = []
    try:
        texto.format_map({v: "" for v in VARIABLES} | {"__x": ""})
    except (ValueError, IndexError):
        avisos.append("Hay una llave { o } suelta: cada variable va así: {lugar}")
    except KeyError:
        pass
    desconocidas = sorted(set(re.findall(r"\{(\w+)\}", texto)) - set(VARIABLES))
    if desconocidas:
        avisos.append("Variables que no existen (quedarían vacías): " + ", ".join("{" + d + "}" for d in desconocidas))
    return avisos


def guardar_plantilla(rel: str, texto: str):
    almacen_actual().guardar_plantilla(rel, texto.replace("\r\n", "\n").strip() + "\n")
