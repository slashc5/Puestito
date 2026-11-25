"""Conexiones a la base de datos: SQLite (local) o PostgreSQL (nube, con DATABASE_URL).

El resto del código escribe SQL al estilo SQLite (marcadores «?») y esta capa lo adapta a PostgreSQL.

Aislamiento por usuario en la versión web:
  - PostgreSQL: cada usuario tiene su propio esquema (u1, u2, …). Las tablas son idénticas en cada esquema,
    así ninguna consulta puede mezclar datos de dos personas. Las cuentas viven en el esquema public.
  - SQLite (web en tu PC, para probar): un archivo por usuario en datos/web/.
"""
import os
import re
import sqlite3
import threading

from .config import ruta

TABLAS_CON_ID = {"tandas", "lugares", "envios", "portal_busquedas", "ofertas", "cuentas"}


def url_base():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):             # algunos proveedores todavía usan el prefijo viejo
        url = "postgresql://" + url[len("postgres://"):]
    return url


def es_postgres() -> bool:
    return url_base().startswith("postgresql://")


class Fila(dict):
    """Fila de resultado: se lee por nombre (fila["nombre"]) o por posición (fila[0]), como sqlite3.Row."""
    def __init__(self, columnas, valores):
        super().__init__(zip(columnas, valores))
        self._valores = list(valores)

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._valores[k]
        return super().__getitem__(k)


class _Resultado:
    def __init__(self, filas=None, cursor=None, lastrowid=None):
        self._filas, self._cursor, self.lastrowid = filas, cursor, lastrowid

    def fetchone(self):
        if self._filas is not None:
            return self._filas.pop(0) if self._filas else None
        return self._cursor.fetchone()

    def fetchall(self):
        if self._filas is not None:
            f, self._filas = self._filas, []
            return f
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self.fetchall())


# =====================================================================
#  SQLite
# =====================================================================
class ConexionSQLite:
    tipo = "sqlite"

    def __init__(self, archivo):
        from pathlib import Path
        self.archivo = Path(archivo) if os.path.isabs(str(archivo)) else ruta(str(archivo))
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        self.existia = self.archivo.exists() and self.archivo.stat().st_size > 0
        self.con = sqlite3.connect(self.archivo, timeout=15, check_same_thread=False)
        self.con.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        cur = self.con.execute(sql, params)
        return _Resultado(cursor=cur, lastrowid=cur.lastrowid)

    def executemany(self, sql, filas):
        self.con.executemany(sql, filas)

    def executescript(self, sql):
        self.con.executescript(sql)

    def columnas(self, tabla):
        return {r[1] for r in self.con.execute(f"PRAGMA table_info({tabla})")}

    def commit(self):
        self.con.commit()

    def close(self):
        self.con.close()


# =====================================================================
#  PostgreSQL (psycopg 3)
# =====================================================================
def traducir(sql: str) -> str:
    """SQL estilo SQLite → PostgreSQL."""
    sql = sql.replace("%", "%%").replace("?", "%s")
    sql = re.sub(r"INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"\bBLOB\b", "BYTEA", sql)
    sql = re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql)
    return sql


def _fabrica_filas(cursor):
    columnas = [d.name for d in cursor.description] if cursor.description else []
    return lambda valores: Fila(columnas, valores)


class ConexionPostgres:
    tipo = "postgres"

    def __init__(self, esquema="public"):
        import psycopg  # se instala con requirements.txt (psycopg[binary])
        self.con = psycopg.connect(url_base(), row_factory=_fabrica_filas, connect_timeout=15)
        self.esquema = esquema
        self.existia = True
        if esquema != "public":
            self.con.execute(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"')
            self.con.commit()
        self._tx_nueva = True

    def _esquema(self):
        """Al empezar cada transacción fija el esquema del usuario con SET LOCAL: vale solo para esa transacción.
        Así funciona también con conexiones «pooled» (PgBouncer en modo transacción, como Neon) sin que el
        esquema de una persona pueda quedar aplicado a la conexión de otra."""
        if self._tx_nueva:
            self.con.execute(f'SET LOCAL search_path TO "{self.esquema}"')
            self._tx_nueva = False

    def execute(self, sql, params=()):
        self._esquema()
        sql_pg = traducir(sql)
        m = re.match(r"\s*INSERT\s+INTO\s+(\w+)", sql, re.I)
        if m and m.group(1).lower() in TABLAS_CON_ID and "RETURNING" not in sql.upper():
            cur = self.con.execute(sql_pg + " RETURNING id", tuple(params))
            fila = cur.fetchone()
            return _Resultado(filas=[], lastrowid=fila[0] if fila else None)
        cur = self.con.execute(sql_pg, tuple(params))
        if cur.description is None:
            return _Resultado(filas=[])
        return _Resultado(filas=cur.fetchall())

    def executemany(self, sql, filas):
        self._esquema()
        with self.con.cursor() as cur:
            cur.executemany(traducir(sql), [tuple(f) for f in filas])

    def executescript(self, sql):
        self._esquema()
        for sentencia in [s.strip() for s in sql.split(";") if s.strip()]:
            if sentencia.startswith("--") and "\n" not in sentencia:
                continue
            self.con.execute(traducir(sentencia))

    def columnas(self, tabla):
        cur = self.con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",
            (self.esquema, tabla))
        return {r[0] for r in cur.fetchall()}

    def commit(self):
        self.con.commit()
        self._tx_nueva = True

    def close(self):
        try:
            self.con.close()
        except Exception:
            pass


# =====================================================================
#  Fábricas
# =====================================================================
def conectar_usuario(uid: int):
    """Conexión a los datos de un usuario de la versión web."""
    uid = int(uid)
    if es_postgres():
        return ConexionPostgres(f"u{uid}")
    return ConexionSQLite(f"datos/web/usuario_{uid}.db")


def conectar_cuentas():
    """Conexión a la tabla de cuentas (compartida, solo usuario + hash de contraseña)."""
    if es_postgres():
        return ConexionPostgres("public")
    return ConexionSQLite("datos/web/cuentas.db")


_inicializados = set()
_lock_init = threading.Lock()


def ya_inicializado(clave) -> bool:
    with _lock_init:
        return clave in _inicializados


def marcar_inicializado(clave):
    with _lock_init:
        _inicializados.add(clave)
