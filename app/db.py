"""Base de datos con lugares, tandas e historial de envíos.

Local: SQLite (datos/postulaciones.db). Web: SQLite o PostgreSQL por usuario (ver basedatos.py).
"""
import csv
import io
import sqlite3
from datetime import datetime, date

from .basedatos import ConexionSQLite, marcar_inicializado, ya_inicializado
from .config import ruta
from .util import clave_lugar, dominio, misma_altura, nombre_parecido, solo_digitos

ESQUEMA = """
CREATE TABLE IF NOT EXISTS tandas (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha   TEXT, perfil TEXT, rubro TEXT, zona TEXT, fuente TEXT
);
CREATE TABLE IF NOT EXISTS lugares (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    clave     TEXT UNIQUE,
    nombre    TEXT, rubro TEXT, direccion TEXT, zona TEXT,
    web       TEXT, instagram TEXT, facebook TEXT,
    email     TEXT, telefono TEXT, whatsapp TEXT,
    fuente    TEXT, fuente_id TEXT,
    tanda_id  INTEGER, perfil TEXT,
    estado    TEXT DEFAULT 'nuevo',   -- nuevo | aprobado | excluido | preparado | contactado | respondio | descartado
    notas     TEXT DEFAULT '',
    creado    TEXT
);
CREATE TABLE IF NOT EXISTS envios (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lugar_id  INTEGER REFERENCES lugares(id),
    fecha     TEXT, perfil TEXT, cv TEXT,
    canal     TEXT,                   -- mail | whatsapp
    destino   TEXT,                   -- dirección de mail o número
    estado    TEXT,                   -- enviado | borrador | eml | whatsapp_preparado | whatsapp_enviado | error
    asunto    TEXT, detalle TEXT
);
CREATE INDEX IF NOT EXISTS ix_envios_lugar ON envios(lugar_id);
CREATE TABLE IF NOT EXISTS ajustes (clave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS archivos (nombre TEXT PRIMARY KEY, datos BLOB, bytes INTEGER, modificado TEXT);
CREATE TABLE IF NOT EXISTS portal_busquedas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    puesto TEXT, ubicacion TEXT, portal TEXT, dias INTEGER, remoto INTEGER DEFAULT 0, url TEXT,
    creada TEXT, ultima_apertura TEXT, aperturas INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ofertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT, url_norm TEXT UNIQUE, titulo TEXT, empresa TEXT, portal TEXT, ubicacion TEXT,
    estado TEXT DEFAULT 'guardada',       -- guardada | vista | postulado | descartada
    notas TEXT DEFAULT '', cv TEXT DEFAULT '', creada TEXT, actualizada TEXT, postulado_en TEXT
);
"""

# Columnas agregadas en Postuladorsito. Se suman a una base vieja sin borrar nada.
COLUMNAS_NUEVAS = {
    "tandas": [("lat", "REAL"), ("lon", "REAL"), ("radio_m", "INTEGER"), ("modo", "TEXT DEFAULT 'rubro'"), ("cv", "TEXT")],
    "lugares": [("lat", "REAL"), ("lon", "REAL"), ("busca_personal", "INTEGER DEFAULT 0"), ("senal_empleo", "TEXT"),
                ("url_empleo", "TEXT")],
}

CAMPOS_CSV = ["id", "nombre", "rubro", "zona", "direccion", "web", "instagram", "facebook",
              "email", "telefono", "whatsapp", "estado", "perfil", "tanda_id", "fuente",
              "ultimo_canal", "ultimo_envio", "ultimo_cv", "notas", "creado"]


class DB:
    def __init__(self, archivo="datos/postulaciones.db", con=None, clave_cache=None, web=False):
        """Sin «con»: la base local de siempre. Con «con»: una conexión ya abierta (versión web)."""
        self.web = web
        self.con = con or ConexionSQLite(archivo)
        clave = clave_cache or f"sqlite:{getattr(self.con, 'archivo', archivo)}"
        if not ya_inicializado(clave):         # crear tablas y migrar, una sola vez por proceso
            self.con.executescript(ESQUEMA)
            self._migrar()
            self.con.commit()
            marcar_inicializado(clave)

    def _migrar(self):
        """Agrega columnas nuevas si faltan. Antes de tocar una base SQLite existente, guarda una copia de respaldo."""
        faltan = []
        for tabla, cols in COLUMNAS_NUEVAS.items():
            actuales = self.con.columnas(tabla)
            faltan += [(tabla, c, t) for c, t in cols if c not in actuales]
        if not faltan:
            return
        if self.con.tipo == "sqlite" and self.con.existia:
            import shutil
            archivo = self.con.archivo
            respaldo = archivo.with_name(f"{archivo.stem}_respaldo_{datetime.now():%Y%m%d_%H%M%S}.db")
            self.con.commit()
            shutil.copy2(archivo, respaldo)
        for tabla, col, tipo in faltan:
            self.con.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")
        self.con.commit()

    # ---------------- tandas ----------------
    def nueva_tanda(self, perfil, rubro, zona, fuente, geo=None, modo="rubro", cv=None) -> int:
        geo = geo or {}
        cur = self.con.execute(
            "INSERT INTO tandas(fecha, perfil, rubro, zona, fuente, lat, lon, radio_m, modo, cv) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), perfil, rubro, zona, fuente,
             geo.get("lat"), geo.get("lon"), geo.get("radio_m"), modo, cv or None))
        self.con.commit()
        return cur.lastrowid

    def ultima_tanda(self):
        r = self.con.execute("SELECT * FROM tandas ORDER BY id DESC LIMIT 1").fetchone()
        return r

    def tanda(self, tid):
        return self.con.execute("SELECT * FROM tandas WHERE id=?", (tid,)).fetchone()

    # ---------------- duplicados ----------------
    def buscar_duplicado(self, l: dict):
        """Devuelve el lugar ya registrado que sea EL MISMO local, o None.

        - Coincidencia fuerte (alcanza sola): mismo id de la fuente, o mismo nombre + misma dirección.
        - Coincidencia débil (mismo mail, teléfono o web): solo cuenta si además el nombre se parece.
          Así, dos sucursales de una misma cadena (misma web, distinto nombre/dirección) no se pisan:
          se guardan las dos y el control al momento de enviar evita escribirle dos veces al mismo mail/número.
        """
        c = self.con
        if l.get("fuente_id"):
            r = c.execute("SELECT * FROM lugares WHERE fuente_id=?", (l["fuente_id"],)).fetchone()
            if r:
                return r
        r = c.execute("SELECT * FROM lugares WHERE clave=?", (clave_lugar(l["nombre"], l.get("direccion", "")),)).fetchone()
        if r:
            return r
        candidatos = []
        if l.get("email"):
            candidatos += c.execute("SELECT * FROM lugares WHERE lower(email)=?", (l["email"].lower(),)).fetchall()
        tel = solo_digitos(l.get("telefono", ""))[-8:]
        if len(tel) == 8:
            candidatos += [r for r in c.execute("SELECT * FROM lugares WHERE telefono IS NOT NULL AND telefono!=''")
                           if solo_digitos(r["telefono"])[-8:] == tel]
        dom = dominio(l.get("web", ""))
        if dom and not any(x in dom for x in ("instagram.", "facebook.", "linktr.ee", "wa.me", "google.")):
            candidatos += [r for r in c.execute("SELECT * FROM lugares WHERE web IS NOT NULL AND web!=''")
                           if dominio(r["web"]) == dom]
        for r in candidatos:
            if nombre_parecido(r["nombre"], l["nombre"]) and misma_altura(r["direccion"], l.get("direccion", "")):
                return r
        return None

    def completar_datos(self, lid, l: dict):
        """Agrega datos de contacto nuevos a un lugar existente SIN pisar los que ya tenía."""
        actual = self.lugar(lid)
        nuevos = {k: l[k] for k in ("web", "instagram", "facebook", "email", "telefono", "whatsapp", "direccion")
                  if l.get(k) and not (actual[k] or "").strip()}
        if nuevos:
            self.actualizar(lid, **nuevos)
        return nuevos

    def recuperar_en_tanda(self, lid, tanda_id, perfil, rubro):
        """Un lugar encontrado antes y NUNCA contactado vuelve a aparecer en la tanda de hoy."""
        self.actualizar(lid, tanda_id=tanda_id, perfil=perfil, rubro=rubro, estado="nuevo")

    def insertar_lugar(self, l: dict, tanda_id: int, perfil: str) -> int:
        cur = self.con.execute(
            """INSERT INTO lugares(clave, nombre, rubro, direccion, zona, web, instagram, facebook,
                                   email, telefono, whatsapp, fuente, fuente_id, tanda_id, perfil, estado, creado, lat, lon,
                                   busca_personal, senal_empleo, url_empleo)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'nuevo', ?, ?, ?, ?, ?, ?)""",
            (clave_lugar(l["nombre"], l.get("direccion", "")), l["nombre"], l.get("rubro", ""),
             l.get("direccion", ""), l.get("zona", ""), l.get("web", ""), l.get("instagram", ""),
             l.get("facebook", ""), l.get("email", ""), l.get("telefono", ""), l.get("whatsapp", ""),
             l.get("fuente", ""), l.get("fuente_id", ""), tanda_id, perfil,
             datetime.now().isoformat(timespec="seconds"), l.get("lat"), l.get("lon"),
             int(l.get("busca_personal") or 0), l.get("senal_empleo") or None, l.get("url_empleo") or None))
        self.con.commit()
        return cur.lastrowid

    # ---------------- consultas ----------------
    def lugares_de_tanda(self, tid, estados=None):
        q = "SELECT * FROM lugares WHERE tanda_id=?"
        args = [tid]
        if estados:
            q += f" AND estado IN ({','.join('?' * len(estados))})"
            args += list(estados)
        return self.con.execute(q + " ORDER BY id", args).fetchall()

    def lugar(self, lid):
        return self.con.execute("SELECT * FROM lugares WHERE id=?", (lid,)).fetchone()

    def set_estado(self, ids, estado):
        self.con.executemany("UPDATE lugares SET estado=? WHERE id=?", [(estado, i) for i in ids])
        self.con.commit()

    def actualizar(self, lid, **campos):
        sets = ", ".join(f"{k}=?" for k in campos)
        self.con.execute(f"UPDATE lugares SET {sets} WHERE id=?", (*campos.values(), lid))
        self.con.commit()

    # ---------------- historial ----------------
    # Contactado = se le ENVIÓ algo de verdad (mail enviado, WhatsApp enviado, o lo marcaste a mano).
    # Un borrador o un .eml todavía no salió: el lugar queda "preparado" hasta que lo marques como enviado.
    ENVIADOS = ("enviado", "whatsapp_enviado")
    PREPARADOS = ("borrador", "eml")

    def ya_contactado(self, lugar, destino=""):
        """Devuelve el envío que prueba que ya se lo contactó (a este lugar o a este mismo mail/número), o None."""
        marcas = ",".join("?" * len(self.ENVIADOS))
        r = self.con.execute(
            f"SELECT * FROM envios WHERE lugar_id=? AND estado IN ({marcas}) ORDER BY id DESC LIMIT 1",
            (lugar["id"], *self.ENVIADOS)).fetchone()
        if r:
            return r
        if lugar["estado"] in ("contactado", "respondio"):
            # marcado a mano, o registros viejos: se respeta igual
            r = self.con.execute("SELECT * FROM envios WHERE lugar_id=? ORDER BY id DESC LIMIT 1", (lugar["id"],)).fetchone()
            return r or {"fecha": lugar["creado"] or "", "canal": "manual", "estado": lugar["estado"]}
        if destino:
            return self.con.execute(
                f"SELECT * FROM envios WHERE lower(destino)=? AND estado IN ({marcas}) ORDER BY id DESC LIMIT 1",
                (destino.lower(), *self.ENVIADOS)).fetchone()
        return None

    def ya_preparado(self, lugar):
        """Borrador o .eml ya generado y todavía sin marcar como enviado."""
        if lugar["estado"] != "preparado":
            return None
        return self.con.execute(
            "SELECT * FROM envios WHERE lugar_id=? AND estado IN ('borrador','eml') ORDER BY id DESC LIMIT 1",
            (lugar["id"],)).fetchone() or {"fecha": "", "canal": "mail", "estado": "borrador"}

    def registrar_envio(self, lugar_id, perfil, cv, canal, destino, estado, asunto="", detalle=""):
        self.con.execute(
            """INSERT INTO envios(lugar_id, fecha, perfil, cv, canal, destino, estado, asunto, detalle)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (lugar_id, datetime.now().isoformat(timespec="seconds"), perfil, cv, canal, destino, estado, asunto, detalle))
        if estado in self.ENVIADOS:
            self.con.execute("UPDATE lugares SET estado='contactado' WHERE id=? AND estado!='respondio'", (lugar_id,))
        elif estado in self.PREPARADOS:
            self.con.execute("UPDATE lugares SET estado='preparado' WHERE id=? AND estado NOT IN ('contactado','respondio')",
                             (lugar_id,))
        self.con.commit()

    def deshacer_whatsapp(self, lugar_id) -> bool:
        """Deshace el último «WhatsApp enviado» de un lugar (por si se abrió el chat pero no se mandó)."""
        r = self.con.execute("SELECT id FROM envios WHERE lugar_id=? AND estado='whatsapp_enviado' ORDER BY id DESC LIMIT 1",
                             (lugar_id,)).fetchone()
        if not r:
            return False
        self.con.execute("DELETE FROM envios WHERE id=?", (r["id"],))
        otros = self.con.execute(
            "SELECT 1 FROM envios WHERE lugar_id=? AND estado IN ('enviado','whatsapp_enviado') LIMIT 1", (lugar_id,)).fetchone()
        if not otros:
            self.con.execute("UPDATE lugares SET estado='aprobado' WHERE id=? AND estado='contactado'", (lugar_id,))
        self.con.commit()
        return True

    def whatsapp_hoy(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM envios WHERE estado='whatsapp_enviado' AND fecha LIKE ?",
                                (date.today().isoformat() + "%",)).fetchone()[0]

    def mails_hoy(self) -> int:
        hoy = date.today().isoformat()
        return self.con.execute(
            "SELECT COUNT(*) FROM envios WHERE canal='mail' AND estado IN ('enviado','borrador','eml') "
            "AND COALESCE(detalle,'') != 'marcado manualmente' AND fecha LIKE ?",
            (hoy + "%",)).fetchone()[0]

    def historial(self, limite=50):
        return self.con.execute(
            """SELECT e.*, l.nombre, l.rubro, l.zona FROM envios e JOIN lugares l ON l.id=e.lugar_id
               ORDER BY e.id DESC LIMIT ?""", (limite,)).fetchall()

    def resumen(self):
        return self.con.execute("SELECT estado, COUNT(*) n FROM lugares GROUP BY estado ORDER BY n DESC").fetchall()

    # ---------------- exportación ----------------
    def csv_textos(self) -> tuple[str, str]:
        """(lugares.csv, historial_envios.csv) como texto, generados en memoria."""
        filas = self.con.execute(
            """SELECT l.*,
                  (SELECT canal FROM envios e WHERE e.lugar_id=l.id ORDER BY e.id DESC LIMIT 1) ultimo_canal,
                  (SELECT fecha FROM envios e WHERE e.lugar_id=l.id ORDER BY e.id DESC LIMIT 1) ultimo_envio,
                  (SELECT cv    FROM envios e WHERE e.lugar_id=l.id ORDER BY e.id DESC LIMIT 1) ultimo_cv
               FROM lugares l ORDER BY l.id""").fetchall()
        a = io.StringIO()
        w = csv.DictWriter(a, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        w.writeheader()
        for r in filas:
            w.writerow({k: (r[k] if k in r.keys() and r[k] is not None else "") for k in CAMPOS_CSV})
        h = io.StringIO()
        w = csv.writer(h)
        w.writerow(["fecha", "lugar", "rubro", "zona", "perfil", "cv", "canal", "destino", "estado", "asunto", "detalle"])
        for r in self.historial(100000):
            w.writerow([r["fecha"], r["nombre"], r["rubro"], r["zona"], r["perfil"], r["cv"],
                        r["canal"], r["destino"], r["estado"], r["asunto"], r["detalle"]])
        return a.getvalue(), h.getvalue()

    def exportar_csv(self, archivo="datos/lugares.csv"):
        """Versión local: deja los CSV en datos/. En la web no escribe nada (se descargan generados al momento)."""
        if self.web:
            return None, None
        lugares, historial = self.csv_textos()
        p, hist = ruta(archivo), ruta("datos/historial_envios.csv")
        # utf-8-sig para que Excel muestre bien los acentos
        p.write_text(lugares, encoding="utf-8-sig", newline="")
        hist.write_text(historial, encoding="utf-8-sig", newline="")
        return p, hist

    # ---------------- portales de empleo ----------------
    def guardar_busqueda_portal(self, puesto, ubicacion, portal, dias, remoto, url) -> int:
        r = self.con.execute("SELECT id FROM portal_busquedas WHERE url=?", (url,)).fetchone()
        ahora = datetime.now().isoformat(timespec="seconds")
        if r:
            self.con.execute("UPDATE portal_busquedas SET creada=? WHERE id=?", (ahora, r["id"]))
            self.con.commit()
            return r["id"]
        cur = self.con.execute(
            "INSERT INTO portal_busquedas(puesto, ubicacion, portal, dias, remoto, url, creada) VALUES (?,?,?,?,?,?,?)",
            (puesto, ubicacion, portal, dias, int(bool(remoto)), url, ahora))
        self.con.commit()
        return cur.lastrowid

    def busqueda_abierta(self, bid):
        self.con.execute("UPDATE portal_busquedas SET ultima_apertura=?, aperturas=aperturas+1 WHERE id=?",
                         (datetime.now().isoformat(timespec="seconds"), bid))
        self.con.commit()

    def busquedas_portal(self, limite=60):
        return self.con.execute("SELECT * FROM portal_busquedas ORDER BY COALESCE(ultima_apertura, creada) DESC LIMIT ?",
                                (limite,)).fetchall()

    def borrar_busqueda_portal(self, bid):
        self.con.execute("DELETE FROM portal_busquedas WHERE id=?", (bid,))
        self.con.commit()

    def guardar_oferta(self, o: dict, url_norm: str):
        ahora = datetime.now().isoformat(timespec="seconds")
        r = self.con.execute("SELECT * FROM ofertas WHERE url_norm=?", (url_norm,)).fetchone()
        if r:
            campos = {k: o[k] for k in ("titulo", "empresa", "portal", "ubicacion", "notas") if o.get(k)}
            if campos:
                self.con.execute(f"UPDATE ofertas SET {', '.join(f'{k}=?' for k in campos)}, actualizada=? WHERE id=?",
                                 (*campos.values(), ahora, r["id"]))
                self.con.commit()
            return r["id"], False
        cur = self.con.execute(
            """INSERT INTO ofertas(url, url_norm, titulo, empresa, portal, ubicacion, estado, notas, creada, actualizada)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (o["url"], url_norm, o.get("titulo", ""), o.get("empresa", ""), o.get("portal", ""), o.get("ubicacion", ""),
             o.get("estado") or "guardada", o.get("notas", ""), ahora, ahora))
        self.con.commit()
        return cur.lastrowid, True

    def estado_oferta(self, oid, estado, cv=""):
        ahora = datetime.now().isoformat(timespec="seconds")
        extra = ", postulado_en=?, cv=?" if estado == "postulado" else ""
        args = [estado, ahora] + ([ahora, cv] if estado == "postulado" else []) + [oid]
        self.con.execute(f"UPDATE ofertas SET estado=?, actualizada=?{extra} WHERE id=?", args)
        self.con.commit()

    def notas_oferta(self, oid, notas):
        self.con.execute("UPDATE ofertas SET notas=?, actualizada=? WHERE id=?",
                         (notas, datetime.now().isoformat(timespec="seconds"), oid))
        self.con.commit()

    def borrar_oferta(self, oid):
        self.con.execute("DELETE FROM ofertas WHERE id=?", (oid,))
        self.con.commit()

    def ofertas(self):
        return self.con.execute("SELECT * FROM ofertas ORDER BY actualizada DESC").fetchall()
