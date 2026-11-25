"""Seguridad de la versión web: contraseñas, sesiones firmadas y cifrado de credenciales.

- Contraseñas de las cuentas: hash scrypt con sal (nunca se guardan en texto plano).
- Sesión: cookie firmada con HMAC-SHA256 usando SECRET_KEY (no se puede falsificar sin la clave).
- Credenciales de cada usuario (contraseña de aplicación de Gmail, clave de Google): cifradas con Fernet
  (AES + HMAC) con una clave derivada de SECRET_KEY. Si alguien obtiene la base, no puede leerlas.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time

_CLAVE_DEV = None


def secret_key() -> bytes:
    """SECRET_KEY de las variables de entorno. Sin ella, solo se permite una clave aleatoria para desarrollo local."""
    global _CLAVE_DEV
    k = os.environ.get("SECRET_KEY", "").strip()
    if k:
        if len(k) < 32:
            print("⚠️  SECRET_KEY es muy corta: usá al menos 32 caracteres al azar.", file=sys.stderr)
        return k.encode()
    if os.environ.get("RENDER") or os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DATABASE_URL"):
        raise RuntimeError("Falta la variable de entorno SECRET_KEY (obligatoria en el hosting).")
    # Desarrollo local: se guarda en datos/ para que las sesiones y credenciales sobrevivan a un reinicio
    if _CLAVE_DEV is None:
        from .config import ruta
        archivo = ruta("datos/web/.secret_key_desarrollo")
        archivo.parent.mkdir(parents=True, exist_ok=True)
        if not archivo.exists():
            archivo.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        _CLAVE_DEV = archivo.read_text(encoding="utf-8").strip().encode()
    return _CLAVE_DEV


def _derivada(proposito: str) -> bytes:
    return hmac.new(secret_key(), proposito.encode(), hashlib.sha256).digest()


# ---------------------------------------------------------------- contraseñas
def hash_password(password: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=sal, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(sal).decode() + "$" + base64.b64encode(h).decode()


def verificar_password(password: str, guardado: str) -> bool:
    try:
        _, sal_b64, h_b64 = guardado.split("$")
        h = hashlib.scrypt(password.encode(), salt=base64.b64decode(sal_b64), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(h, base64.b64decode(h_b64))
    except Exception:
        return False


# ---------------------------------------------------------------- sesión firmada
DURACION_SESION = 30 * 24 * 3600


def crear_sesion(uid: int, usuario: str) -> str:
    datos = base64.urlsafe_b64encode(json.dumps({"u": uid, "n": usuario, "e": int(time.time()) + DURACION_SESION}).encode()).decode()
    firma = base64.urlsafe_b64encode(hmac.new(_derivada("sesion"), datos.encode(), hashlib.sha256).digest()).decode()
    return f"{datos}.{firma}"


def leer_sesion(valor: str):
    try:
        datos, firma = valor.split(".")
        esperada = base64.urlsafe_b64encode(hmac.new(_derivada("sesion"), datos.encode(), hashlib.sha256).digest()).decode()
        if not hmac.compare_digest(firma, esperada):
            return None
        d = json.loads(base64.urlsafe_b64decode(datos))
        if d.get("e", 0) < time.time():
            return None
        return {"uid": int(d["u"]), "usuario": d["n"]}
    except Exception:
        return None


# ---------------------------------------------------------------- cifrado de credenciales
def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(_derivada("credenciales")))


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(token: str) -> str:
    """Devuelve '' si no se puede descifrar (por ejemplo, si cambió SECRET_KEY)."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:
        return ""
