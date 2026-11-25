"""Envío de mails o creación de borradores (Gmail u otro proveedor SMTP/IMAP)."""
import imaplib
import mimetypes
import os
import re
import smtplib
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from .config import ruta


def armar_mail(remitente, nombre_remitente, destino, asunto, cuerpo, adjunto) -> EmailMessage:
    """adjunto: (nombre_archivo, bytes) — el PDF se adjunta desde memoria, sin archivos temporales."""
    m = EmailMessage()
    m["From"] = f"{nombre_remitente} <{remitente}>"
    m["To"] = destino
    m["Subject"] = asunto
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid()
    m.set_content(cuerpo)
    if adjunto:
        nombre, datos = adjunto
        tipo, _ = mimetypes.guess_type(nombre)
        principal, sub = (tipo or "application/pdf").split("/")
        m.add_attachment(datos, maintype=principal, subtype=sub, filename=nombre)
    return m


class Correo:
    """Abre UNA conexión por tanda y la reutiliza."""

    def __init__(self, cfg, modo: str):
        self.cfg, self.modo = cfg, modo
        secretos = cfg.get("_secretos") or {}
        self.usuario = secretos.get("MAIL_USUARIO") or os.environ.get("MAIL_USUARIO") or cfg["yo"].get("email")
        self.password = secretos.get("MAIL_PASSWORD") or os.environ.get("MAIL_PASSWORD", "")
        self.smtp = self.imap = None
        self.carpeta_borradores = None
        if modo in ("enviar", "borrador") and not self.password:
            raise RuntimeError("Falta la contraseña de aplicación de Gmail: cargala en Configuración y CVs → Claves.")

    def __enter__(self):
        if self.modo == "enviar":
            s = self.cfg["smtp"]
            try:
                self.smtp = smtplib.SMTP(s["servidor"], s["puerto"], timeout=30)
            except OSError as e:
                raise RuntimeError("No pude conectarme al servidor de envío (en hostings gratuitos el envío directo "
                                   "suele estar bloqueado). Usá «Borradores en Gmail» y mandalos desde tu Gmail.") from e
            self.smtp.starttls()
            self.smtp.login(self.usuario, self.password)
        elif self.modo == "borrador":
            i = self.cfg["imap"]
            try:
                self.imap = imaplib.IMAP4_SSL(i["servidor"], i["puerto"], timeout=30)
                self.imap.login(self.usuario, self.password)
            except imaplib.IMAP4.error as e:
                raise RuntimeError("Gmail rechazó el acceso: revisá la contraseña de aplicación en Configuración → Claves.") from e
            except OSError as e:
                raise RuntimeError(f"No pude conectarme a Gmail para dejar los borradores ({e}). Probá de nuevo en un rato.") from e
            self.carpeta_borradores = self._detectar_borradores()
        return self

    def __exit__(self, *a):
        try:
            if self.smtp:
                self.smtp.quit()
            if self.imap:
                self.imap.logout()
        except Exception:
            pass

    def _detectar_borradores(self) -> str:
        typ, carpetas = self.imap.list()
        for c in carpetas or []:
            linea = c.decode(errors="ignore")
            if "\\Drafts" in linea:
                m = re.search(r'"([^"]+)"\s*$', linea) or re.search(r"(\S+)\s*$", linea)
                return '"' + m.group(1).strip('"') + '"'
        return '"[Gmail]/Drafts"'

    def procesar(self, msg: EmailMessage, carpeta_eml: Path) -> str:
        """Devuelve el estado a registrar: enviado | borrador | eml."""
        if self.modo == "enviar":
            self.smtp.send_message(msg)
            return "enviado"
        if self.modo == "borrador":
            self.imap.append(self.carpeta_borradores, "\\Draft",
                             imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            return "borrador"
        carpeta_eml.mkdir(parents=True, exist_ok=True)
        nombre = re.sub(r"[^\w\-]+", "_", msg["To"])[:60] + ".eml"
        (carpeta_eml / nombre).write_bytes(msg.as_bytes())
        return "eml"


def adjunto_de(perfil, almacen=None):
    """(nombre, bytes) del CV del perfil, leído del almacén del usuario (archivo local o base de datos)."""
    if almacen is None:
        from .almacen import almacen_actual
        almacen = almacen_actual()
    return almacen.leer_cv(perfil["cv"])
