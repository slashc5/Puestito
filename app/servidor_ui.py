"""Servidor de Postuladorsito (aplicación WSGI).

Sirve las dos versiones con el mismo código:
  - Local (python app_postulador.py): una sola persona, datos en la carpeta del proyecto, sin login.
  - Web (gunicorn wsgi:application): varias personas, cada una con su cuenta y sus datos separados
    (su configuración, sus credenciales cifradas, sus CVs y su historial). Ver wsgi.py.

Para buscar y enviar llama a las MISMAS funciones que la consola (cmd_buscar, cmd_enviar, cmd_marcar…).
"""
import contextlib
import io
import json
import mimetypes
import os
import platform
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from datetime import datetime
from http.cookies import SimpleCookie

import postulador as cli
from app import ajustes, portales, seguridad
from app.almacen import AlmacenArchivos, AlmacenDB, almacen_actual
from app.basedatos import conectar_cuentas, conectar_usuario, es_postgres, marcar_inicializado, ya_inicializado
from app.buscan import CATEGORIAS
from app.config import Config, ruta
from app.contexto import capturar, como, instalar_despachador, usuario_actual
from app.db import DB
from app.fuentes import FUENTES, probar_google
from app.intenciones import LO_QUE_SEA, expandir
from app.mensajes import formatear, mensaje_mail, mensaje_whatsapp, variables
from app.whatsapp import enlace, numero_para

NOMBRE = "Postuladorsito"
UI_HTML = ruta("app/ui/index.html")
UI_INGRESO = ruta("app/ui/ingreso.html")
WEB = False            # True cuando corre como sitio web multiusuario (wsgi.py)
PUERTO = 8765
TOKEN = None           # versión local con --red: clave que va en el link del celular
ORIGENES_EXTRA = set()
SERVIDOR = None
MAX_CUERPO = 20 * 1024 * 1024
COOKIE_SESION = "ps_sesion"


# =====================================================================
#  Usuarios
# =====================================================================
class UsuarioLocal:
    """La versión de escritorio: una sola persona, todo en archivos."""
    uid, nombre = 0, ""

    def __init__(self):
        self.almacen = AlmacenArchivos()

    def abrir_db(self):
        return DB()


class UsuarioWeb:
    """Una persona con cuenta en la versión web: sus datos viven en su propio esquema/archivo de base."""
    def __init__(self, uid: int, nombre: str):
        self.uid, self.nombre = int(uid), nombre
        self.almacen = AlmacenDB(self.uid)

    def abrir_db(self):
        return DB(con=conectar_usuario(self.uid), clave_cache=f"u{self.uid}", web=True)


LOCAL = UsuarioLocal()


# =====================================================================
#  Tareas en segundo plano (búsqueda / envío), una por usuario, con log en vivo
# =====================================================================
LOCK = threading.Lock()
JOBS = {}


def _job_vacio():
    return {"id": 0, "tipo": None, "estado": "libre", "log": [], "resultado": None}


def job_del_usuario():
    u = usuario_actual() or LOCAL
    with LOCK:
        return JOBS.setdefault(u.uid, _job_vacio())


def lanzar_job(tipo, funcion):
    u = usuario_actual() or LOCAL
    job = job_del_usuario()
    with LOCK:
        if job["estado"] == "corriendo":
            return None
        job.update(id=job["id"] + 1, tipo=tipo, estado="corriendo", log=[], resultado=None)
        jid = job["id"]

    def escribir(s):
        with LOCK:
            job["log"].append(s)

    def correr():
        with como(u), capturar(escribir):          # el hilo trabaja «como» ese usuario y con su propio log
            try:
                res = funcion()
                with LOCK:
                    job.update(estado="ok", resultado=res)
            except Exception as e:
                escribir(f"\n❌ Error: {e}\n")
                with LOCK:
                    job.update(estado="error", resultado=str(e))
                traceback.print_exc(file=sys.__stderr__)

    threading.Thread(target=correr, daemon=True).start()
    return jid


# =====================================================================
#  Helpers
# =====================================================================
def fila(r):
    return {k: r[k] for k in r.keys()} if r is not None else None


@contextlib.contextmanager
def conexion():
    db = (usuario_actual() or LOCAL).abrir_db()
    try:
        yield db
    finally:
        db.con.close()


def perfil_y_rubro(cfg, db, tanda_id):
    """Perfil (con el CV de la tanda) y datos del rubro de la tanda: lo mismo que usa el envío real."""
    t = db.tanda(tanda_id)
    return t, cli.perfil_de_tanda(cfg, t), cfg.rubro(t["rubro"])


def lugar_ui(db, l, pref):
    canal, destino = cli.canal_para(l, pref)
    previo = db.ya_contactado(l, destino)
    prep = db.ya_preparado(l)
    d = fila(l)
    d.update(canal=canal, destino=destino, numero_wa=numero_para(l),
             ya_contactado=(f"{str(previo['fecha'])[:10]} por {previo['canal']} ({previo['estado']})" if previo else ""),
             preparado=(f"{prep['estado']} del {str(prep['fecha'])[:10]}" if prep else ""))
    return d


# =====================================================================
#  Lectura
# =====================================================================
def api_config(q):
    cfg = Config()
    with conexion() as db:
        perfiles = [dict(nombre=n, descripcion=p.get("descripcion", ""), cv=p.get("cv", ""),
                         cv_existe=cfg.almacen.existe_cv(p.get("cv", "")), cv_link=p.get("cv_link", ""),
                         asunto=p.get("asunto", ""), plantilla_mail=p.get("plantilla_mail", ""),
                         plantilla_whatsapp=p.get("plantilla_whatsapp", ""),
                         rubros=p.get("rubros", []), zonas=p.get("zonas", []))
                    for n, p in cfg.perfiles.items()]
        return dict(
            nombre_app=NOMBRE, yo=cfg.general.get("yo", {}), perfiles=perfiles, fuentes=list(FUENTES),
            rubros=[dict(nombre=n, gancho=r.get("gancho", ""), google_query=r.get("google_query", ""), osm=r.get("osm", []))
                    for n, r in cfg.rubros.items()],
            busqueda=cfg.general.get("busqueda", {}), envio=cfg.general.get("envio", {}),
            cv_defecto=cfg.cv_defecto(), cvs=ajustes.listar_cvs(cfg.perfiles, cfg.cv_defecto()),
            mails_hoy=db.mails_hoy(), whatsapp_hoy=db.whatsapp_hoy(), credenciales=ajustes.estado_credenciales(),
            variables=ajustes.VARIABLES, modo_red=bool(TOKEN), modo_web=WEB,
            usuario=getattr(usuario_actual(), "nombre", ""), registro_con_codigo=bool(os.environ.get("CODIGO_INVITACION")),
            categorias=[{"id": k, "nombre": c["nombre"]} for k, c in CATEGORIAS.items()],
            apariencia=cfg.general.get("apariencia", {}),
        )


def api_intencion(q):
    """Vista previa de cómo se va a interpretar el texto libre."""
    cfg = Config()
    texto = q.get("texto", "")
    if not texto.strip():
        return {"consultas": [], "gancho": LO_QUE_SEA["gancho"]}
    e = expandir(texto, cfg.rubros)
    return {"consultas": e["consultas"], "gancho": cfg.rubro(texto)["gancho"], "detectado": e["detectado"]}


def api_tandas(q):
    with conexion() as db:
        tandas = [fila(t) for t in db.con.execute("SELECT * FROM tandas ORDER BY id DESC LIMIT 80")]
        for t in tandas:
            t["conteo"] = {r["estado"]: r["n"] for r in db.con.execute(
                "SELECT estado, COUNT(*) n FROM lugares WHERE tanda_id=? GROUP BY estado", (t["id"],))}
            t["total"] = sum(t["conteo"].values())
        return [t for t in tandas if t["total"]]


def api_tanda(q, tid):
    cfg = Config()
    with conexion() as db:
        t, perfil, _ = perfil_y_rubro(cfg, db, tid)
        pref = q.get("canal") or cfg.general.get("envio", {}).get("canal_preferido", "auto")
        lugares = [lugar_ui(db, l, pref) for l in db.lugares_de_tanda(tid)]
        if t["modo"] == "buscan":   # los que muestran más señales de búsqueda, primero
            lugares.sort(key=lambda l: -(l.get("busca_personal") or 0))
        return dict(tanda=fila(t), cv=perfil["cv"], cv_existe=cfg.almacen.existe_cv(perfil["cv"]), canal=pref, lugares=lugares)


def api_preview(q, lid):
    cfg = Config()
    with conexion() as db:
        l = db.lugar(lid)
        t, perfil, cfg_rubro = perfil_y_rubro(cfg, db, l["tanda_id"])
        cfg_rubro = cli.rubro_para(cfg, t, l, cfg_rubro)
        asunto, cuerpo = mensaje_mail(l, perfil, cfg_rubro, cfg.general)
        texto_wa = mensaje_whatsapp(l, perfil, cfg_rubro, cfg.general)
        num = numero_para(l)
        return dict(lugar=fila(l), asunto=asunto, cuerpo=cuerpo, adjunto=perfil["cv"],
                    whatsapp=texto_wa, numero=num, link=enlace(num, texto_wa) if num else "")


def api_whatsapp(q):
    cfg = Config()
    with conexion() as db:
        filas = db.con.execute("""
            SELECT l.* FROM lugares l
            WHERE EXISTS (SELECT 1 FROM envios e WHERE e.lugar_id=l.id AND e.estado='whatsapp_preparado')
              AND NOT EXISTS (SELECT 1 FROM envios e WHERE e.lugar_id=l.id
                              AND e.estado IN ('whatsapp_enviado','enviado','borrador','eml'))
              AND l.estado NOT IN ('descartado','respondio','excluido','contactado')
            ORDER BY l.id DESC""").fetchall()
        sin_canal = db.con.execute("""
            SELECT l.* FROM lugares l
            WHERE l.estado='aprobado' AND (l.email IS NULL OR l.email='')
              AND NOT EXISTS (SELECT 1 FROM envios e WHERE e.lugar_id=l.id)
            ORDER BY l.id DESC LIMIT 100""").fetchall()
        out = []
        for l in filas:
            try:
                t, perfil, cfg_rubro = perfil_y_rubro(cfg, db, l["tanda_id"])
                texto = mensaje_whatsapp(l, perfil, cli.rubro_para(cfg, t, l, cfg_rubro), cfg.general)
            except Exception:
                perfil, texto = {}, ""
            num = numero_para(l)
            out.append(dict(fila(l), numero=num, texto=texto, link=enlace(num, texto) if num else "", cv=perfil.get("cv", "")))
        return dict(pendientes=out, solo_redes=[fila(l) for l in sin_canal if not numero_para(l)])


def api_historial(q):
    with conexion() as db:
        envios = [fila(r) for r in db.con.execute("""
            SELECT e.*, l.nombre, l.rubro, l.zona, l.estado AS estado_lugar
            FROM envios e JOIN lugares l ON l.id=e.lugar_id
            WHERE e.estado != 'whatsapp_preparado' ORDER BY e.id DESC LIMIT 1500""")]
        ofertas = db.con.execute("SELECT estado, COUNT(*) n FROM ofertas GROUP BY estado").fetchall()
        return dict(envios=envios, resumen=[fila(r) for r in db.resumen()], mails_hoy=db.mails_hoy(),
                    ofertas={r["estado"]: r["n"] for r in ofertas})


def api_job(q):
    job = job_del_usuario()
    with LOCK:
        return dict(job, log="".join(job["log"]))


def api_plantillas(q):
    cfg = Config()
    out = []
    for n, p in cfg.perfiles.items():
        item = {"perfil": n, "asunto": p.get("asunto", "")}
        for tipo in ("mail", "whatsapp"):
            rel = p.get(f"plantilla_{tipo}", "")
            try:
                item[tipo] = cfg.almacen.leer_plantilla(rel) if rel else ""
            except OSError:
                item[tipo] = ""
            item[f"ruta_{tipo}"] = rel
        out.append(item)
    return out


def api_portales(q):
    with conexion() as db:
        return dict(busquedas=[fila(r) for r in db.busquedas_portal()], ofertas=[fila(r) for r in db.ofertas()],
                    portales=portales.PORTALES)


# =====================================================================
#  Escritura: búsqueda, revisión, envío
# =====================================================================
def guardar_seleccion(tid, aprobados, excluidos):
    with conexion() as db:
        editables = {l["id"] for l in db.lugares_de_tanda(tid, ["nuevo", "aprobado", "excluido"])}
        db.set_estado([i for i in aprobados if i in editables], "aprobado")
        db.set_estado([i for i in excluidos if i in editables], "excluido")
        db.exportar_csv()
    return {"ok": True}


def api_buscar(p):
    todo = bool(p.get("todo"))
    if not p.get("perfil") or not (todo or p.get("rubro", "").strip()):
        raise ValueError("Elegí un perfil y escribí qué buscar (o activá «Lo que sea»)")
    if not (p.get("zona", "").strip() or p.get("lat") is not None):
        raise ValueError("Elegí una zona: escribila, usá tu ubicación o tocá el mapa")
    geo = None
    if p.get("lat") is not None and p.get("lon") is not None:
        geo = {"lat": float(p["lat"]), "lon": float(p["lon"]), "radio_m": int(p.get("radio_m") or 3000)}

    def f():
        cfg = Config()
        with conexion() as db:
            tid = cli.cmd_buscar(cfg, db, p["perfil"], p.get("rubro", "").strip(), (p.get("zona") or "").strip() or "zona elegida",
                                 int(p.get("limite") or 0) or None, p.get("fuente") or None,
                                 geo=geo, todo=todo, cv=p.get("cv") or None)
        return {"tanda": tid}
    jid = lanzar_job("buscar", f)
    if not jid:
        raise RuntimeError("Ya hay una tarea en curso")
    return {"job": jid}


def api_buscan(p):
    cats = [c for c in p.get("categorias", []) if c in CATEGORIAS]
    if not p.get("perfil"):
        raise ValueError("Elegí un perfil")
    if not cats:
        raise ValueError("Elegí al menos una categoría")
    if not (p.get("zona", "").strip() or p.get("lat") is not None):
        raise ValueError("Elegí una zona: escribila, usá tu ubicación o tocá el mapa")
    geo = None
    if p.get("lat") is not None and p.get("lon") is not None:
        geo = {"lat": float(p["lat"]), "lon": float(p["lon"]), "radio_m": int(p.get("radio_m") or 3000)}

    def f():
        cfg = Config()
        with conexion() as db:
            tid = cli.cmd_buscan(cfg, db, p["perfil"], cats, (p.get("zona") or "").strip() or "zona elegida",
                                 int(p.get("limite") or 0) or None, p.get("fuente") or None, geo=geo,
                                 solo_senales=p.get("solo_senales", True) is not False, cv=p.get("cv") or None,
                                 dias=int(p.get("dias") or 3))
        return {"tanda": tid}
    jid = lanzar_job("buscar", f)
    if not jid:
        raise RuntimeError("Ya hay una tarea en curso")
    return {"job": jid}


def api_deshacer(p):
    with conexion() as db:
        ok = db.deshacer_whatsapp(int(p["id"]))
        db.exportar_csv()
    return {"ok": ok}


def api_apariencia(p):
    """Guarda el tema elegido también en la config local (además del navegador)."""
    cfg = Config()
    ap = cfg.general.setdefault("apariencia", {})
    ap["tema"] = _texto(p.get("tema"), 40) or "vice"
    custom = p.get("custom") or {}
    limpio = {k: str(v)[:30] for k, v in custom.items() if isinstance(k, str) and k.startswith("--") and len(k) < 40}
    ap["custom"] = json.dumps(limpio, ensure_ascii=False) if limpio else ""
    ajustes.guardar_config(cfg.general)
    return {"ok": True}


def api_enviar(p):
    def f():
        cfg = Config()
        with conexion() as db:
            tid = int(p["tanda"])
            guardar_seleccion(tid, p.get("aprobados", []), p.get("excluidos", []))
            cli.cmd_enviar(cfg, db, tid, p.get("modo") or None, p.get("canal") or None,
                           auto_si=True, forzar=bool(p.get("forzar")))
            print("\n✅ Tanda procesada.")
        return {"tanda": tid}
    jid = lanzar_job("enviar", f)
    if not jid:
        raise RuntimeError("Ya hay una tarea en curso")
    return {"job": jid}


def api_marcar(p):
    cfg = Config()
    with conexion() as db:
        buf = io.StringIO()
        with capturar(buf.write):
            cli.cmd_marcar(cfg, db, [int(i) for i in p["ids"]], p.get("canal"), p.get("estado"))
    return {"ok": True, "log": buf.getvalue()}


def api_abrir(p):
    if WEB:
        raise ValueError("En la versión web no hay carpetas: descargá los CSV desde Historial")
    destino = ruta({"datos": "datos", "salidas": "salidas", "cvs": "cvs", "config": "config"}.get(p.get("que"), "datos"))
    destino.mkdir(exist_ok=True)
    sistema = platform.system()
    if sistema == "Windows":
        os.startfile(destino)  # type: ignore[attr-defined]
    elif sistema == "Darwin":
        subprocess.Popen(["open", str(destino)])
    else:
        subprocess.Popen(["xdg-open", str(destino)])
    return {"ok": True}


# =====================================================================
#  Escritura: configuración (sin tocar archivos a mano)
# =====================================================================
def _texto(v, largo=200):
    return str(v or "").strip()[:largo]


def api_guardar_yo(p):
    cfg = Config()
    yo = cfg.general.setdefault("yo", {})
    for k in ("nombre", "telefono", "email", "zona", "linkedin"):
        if k in p:
            yo[k] = _texto(p[k])
    ajustes.guardar_config(cfg.general)
    return {"ok": True}


def api_guardar_preferencias(p):
    cfg = Config()
    b = cfg.general.setdefault("busqueda", {})
    e = cfg.general.setdefault("envio", {})
    if p.get("fuente") in FUENTES:
        b["fuente"] = p["fuente"]
    for k, minimo, maximo in (("limite", 1, 60),):
        if k in p:
            b[k] = max(minimo, min(maximo, int(p[k])))
    if "radio_km" in p:
        b["radio_km"] = max(0.2, min(50.0, float(p["radio_km"])))
    if "enriquecer_web" in p:
        b["enriquecer_web"] = bool(p["enriquecer_web"])
    if p.get("modo_mail") in (("borrador", "enviar") if WEB else ("borrador", "enviar", "eml")):
        e["modo_mail"] = p["modo_mail"]
    if p.get("canal_preferido") in ("auto", "mail", "whatsapp"):
        e["canal_preferido"] = p["canal_preferido"]
    for k, minimo, maximo in (("max_por_tanda", 1, 50), ("max_por_dia", 1, 100), ("pausa_min_seg", 10, 600), ("pausa_max_seg", 15, 900)):
        if k in p:
            e[k] = max(minimo, min(maximo, int(p[k])))
    if e.get("pausa_max_seg", 120) < e.get("pausa_min_seg", 45):
        e["pausa_max_seg"] = e["pausa_min_seg"]
    ajustes.guardar_config(cfg.general)
    return {"ok": True}


def api_guardar_perfil(p):
    cfg = Config()
    nombre = _texto(p.get("nombre"), 40)
    if nombre not in cfg.perfiles:
        raise ValueError("Ese perfil no existe")
    pf = cfg.perfiles[nombre]
    for k in ("descripcion", "asunto", "cv_link"):
        if k in p:
            pf[k] = _texto(p[k], 300)
    if "cv" in p:
        cv = _texto(p["cv"])
        if cv and not cfg.almacen.existe_cv(cv):
            raise ValueError("Ese CV no está subido")
        pf["cv"] = cv
    for k in ("rubros", "zonas"):
        if k in p:
            pf[k] = [_texto(x, 80) for x in p[k] if _texto(x)]
    ajustes.guardar_perfiles(cfg.perfiles, cfg.rubros)
    return {"ok": True}


def api_nuevo_perfil(p):
    cfg = Config()
    nombre = cli_slug = "".join(c for c in ajustes.nombre_seguro(_texto(p.get("nombre"), 30)).removesuffix(".pdf").lower() if c.isalnum() or c == "_")
    if not nombre:
        raise ValueError("Poné un nombre para el perfil")
    if nombre in cfg.perfiles:
        raise ValueError("Ya existe un perfil con ese nombre")
    base = cfg.perfiles.get(p.get("copiar_de")) or next(iter(cfg.perfiles.values()), {})
    nuevo = dict(base)
    nuevo.update(descripcion=_texto(p.get("descripcion"), 120) or nombre.capitalize(),
                 plantilla_mail=f"plantillas/{cli_slug}_mail.txt", plantilla_whatsapp=f"plantillas/{cli_slug}_whatsapp.txt")
    for tipo in ("mail", "whatsapp"):
        origen = base.get(f"plantilla_{tipo}")
        texto = (cfg.almacen.leer_plantilla(origen) if origen else "") or "Hola, ¿qué tal? Soy {mi_nombre}."
        ajustes.guardar_plantilla(nuevo[f"plantilla_{tipo}"], texto)
    cfg.perfiles[nombre] = nuevo
    ajustes.guardar_perfiles(cfg.perfiles, cfg.rubros)
    return {"ok": True, "nombre": nombre}


def api_borrar_perfil(p):
    cfg = Config()
    if len(cfg.perfiles) <= 1:
        raise ValueError("Tiene que quedar al menos un perfil")
    cfg.perfiles.pop(p.get("nombre"), None)
    ajustes.guardar_perfiles(cfg.perfiles, cfg.rubros)
    return {"ok": True}


def api_guardar_rubro(p):
    cfg = Config()
    nombre = _texto(p.get("nombre"), 60)
    if not nombre:
        raise ValueError("Falta el nombre del rubro")
    anterior = p.get("anterior")
    r = cfg.rubros.pop(anterior, None) if anterior and anterior in cfg.rubros else cfg.rubros.get(nombre, {})
    r = dict(r or {})
    r["gancho"] = _texto(p.get("gancho"), 300).rstrip(".")
    r.setdefault("google_query", f"{nombre} en {{zona}}")
    r.setdefault("osm", expandir(nombre)["osm"])
    cfg.rubros[nombre] = r
    ajustes.guardar_perfiles(cfg.perfiles, cfg.rubros)
    return {"ok": True}


def api_borrar_rubro(p):
    cfg = Config()
    cfg.rubros.pop(p.get("nombre"), None)
    ajustes.guardar_perfiles(cfg.perfiles, cfg.rubros)
    return {"ok": True}


def api_guardar_plantilla(p):
    cfg = Config()
    pf = cfg.perfil(p["perfil"])
    tipo = p.get("tipo")
    if tipo == "asunto":
        pf["asunto"] = _texto(p.get("texto"), 200)
        ajustes.guardar_perfiles(cfg.perfiles, cfg.rubros)
        return {"ok": True, "avisos": ajustes.validar_plantilla(pf["asunto"])}
    if tipo not in ("mail", "whatsapp"):
        raise ValueError("Tipo de plantilla no válido")
    texto = str(p.get("texto", ""))
    if not texto.strip():
        raise ValueError("La plantilla no puede quedar vacía")
    ajustes.guardar_plantilla(pf[f"plantilla_{tipo}"], texto)
    return {"ok": True, "avisos": ajustes.validar_plantilla(texto)}


def api_preview_plantilla(p):
    """Muestra cómo queda una plantilla (sin guardarla) con un lugar de ejemplo."""
    cfg = Config()
    pf = dict(cfg.perfil(p["perfil"]))
    rubro = p.get("rubro") or (pf.get("rubros") or ["tiendas de anime"])[0]
    lugar = {"nombre": "Otaku Corner", "rubro": rubro, "zona": cfg.general.get("yo", {}).get("zona", "Lomas de Zamora")}
    v = variables(lugar, pf, cfg.rubro(rubro), cfg.general)
    texto = formatear(str(p.get("texto", "")), v).strip()
    if p.get("tipo") == "whatsapp":
        texto = " ".join(texto.split())
    return {"texto": texto, "avisos": ajustes.validar_plantilla(str(p.get("texto", ""))), "rubro": rubro}


def api_subir_cv(p):
    cfg = Config()
    rel = ajustes.guardar_cv(_texto(p.get("nombre"), 120) or "CV.pdf", p.get("datos", ""), bool(p.get("reemplazar")))
    if p.get("perfil") in cfg.perfiles:
        cfg.perfiles[p["perfil"]]["cv"] = rel
        ajustes.guardar_perfiles(cfg.perfiles, cfg.rubros)
    if not cfg.cv_defecto():
        cfg.general.setdefault("cvs", {})["defecto"] = rel
        ajustes.guardar_config(cfg.general)
    return {"ok": True, "ruta": rel}


def api_cv_defecto(p):
    cfg = Config()
    rel = _texto(p.get("ruta"))
    if rel and not cfg.almacen.existe_cv(rel):
        raise ValueError("Ese CV no existe")
    cfg.general.setdefault("cvs", {})["defecto"] = rel
    ajustes.guardar_config(cfg.general)
    return {"ok": True}


def api_borrar_cv(p):
    cfg = Config()
    rel = f"cvs/{os.path.basename(p.get('archivo', ''))}"
    usado = [n for n, pf in cfg.perfiles.items() if pf.get("cv") == rel]
    if usado and not p.get("forzar"):
        raise ValueError(f"Ese CV lo usa el perfil: {', '.join(usado)}. Asigná otro antes de borrarlo.")
    ajustes.borrar_cv(p.get("archivo", ""))
    if cfg.cv_defecto() == rel:
        cfg.general.setdefault("cvs", {})["defecto"] = ""
        ajustes.guardar_config(cfg.general)
    return {"ok": True}


def api_guardar_env(p):
    cambios = ajustes.guardar_env({k: p.get(k) for k in ajustes.CLAVES_ENV})
    for k in p.get("borrar", []):
        ajustes.borrar_clave_env(k)
    return {"ok": True, "guardadas": cambios, "credenciales": ajustes.estado_credenciales()}


def api_probar_gmail(p):
    ok, msg = ajustes.probar_gmail(Config().general, p.get("MAIL_USUARIO", ""), p.get("MAIL_PASSWORD", ""))
    return {"ok": ok, "mensaje": msg}


def api_probar_google(p):
    clave = (p.get("GOOGLE_PLACES_API_KEY") or almacen_actual().secretos().get("GOOGLE_PLACES_API_KEY", "")).strip()
    if not clave:
        return {"ok": False, "mensaje": "Todavía no cargaste la clave de Google Places."}
    try:
        return {"ok": True, "mensaje": probar_google(clave)}
    except Exception as e:
        detalle = str(e)
        if "403" in detalle or "400" in detalle:
            detalle += " · Revisá que la clave sea correcta y que «Places API (New)» esté activada en Google Cloud."
        return {"ok": False, "mensaje": f"Google rechazó la prueba: {detalle}"}


# =====================================================================
#  Portales de empleo
# =====================================================================
def api_portales_generar(p):
    puesto = _texto(p.get("puesto"), 100)
    if not puesto:
        raise ValueError("Escribí el puesto que buscás")
    ubic, dias, remoto = _texto(p.get("ubicacion"), 100), int(p.get("dias") or 7), bool(p.get("remoto"))
    urls = portales.links(puesto, ubic, dias, remoto)
    elegidos = p.get("portales") or list(urls)
    with conexion() as db:
        res = []
        for portal in elegidos:
            if portal in urls:
                bid = db.guardar_busqueda_portal(puesto, ubic, portal, dias, remoto, urls[portal])
                res.append({"id": bid, "portal": portal, "nombre": portales.PORTALES[portal], "url": urls[portal]})
    return {"busquedas": res}


def api_portales_abierta(p):
    with conexion() as db:
        db.busqueda_abierta(int(p["id"]))
    return {"ok": True}


def api_portales_borrar_busqueda(p):
    with conexion() as db:
        db.borrar_busqueda_portal(int(p["id"]))
    return {"ok": True}


def api_oferta(p):
    url = _texto(p.get("url"), 1000)
    if not url or "." not in url:
        raise ValueError("Pegá el link de la oferta")
    if "://" not in url:
        url = "https://" + url
    o = dict(url=url, titulo=_texto(p.get("titulo"), 160), empresa=_texto(p.get("empresa"), 120),
             portal=_texto(p.get("portal"), 40) or portales.portal_de(url), ubicacion=_texto(p.get("ubicacion"), 100),
             notas=_texto(p.get("notas"), 1000), estado=p.get("estado") if p.get("estado") in ("guardada", "vista", "postulado", "descartada") else "guardada")
    with conexion() as db:
        oid, nueva = db.guardar_oferta(o, portales.normalizar_url(url))
    return {"ok": True, "id": oid, "nueva": nueva}


def api_oferta_estado(p):
    if p.get("estado") not in ("guardada", "vista", "postulado", "descartada"):
        raise ValueError("Estado no válido")
    with conexion() as db:
        db.estado_oferta(int(p["id"]), p["estado"], _texto(p.get("cv")))
    return {"ok": True}


def api_oferta_notas(p):
    with conexion() as db:
        db.notas_oferta(int(p["id"]), _texto(p.get("notas"), 1000))
    return {"ok": True}


def api_oferta_borrar(p):
    with conexion() as db:
        db.borrar_oferta(int(p["id"]))
    return {"ok": True}


def api_apagar(p):
    if WEB:
        raise ValueError("La versión web no se apaga desde acá")
    threading.Timer(0.5, lambda: SERVIDOR and SERVIDOR.shutdown()).start()
    return {"ok": True, "mensaje": "Postuladorsito se cerró. Ya podés cerrar esta pestaña."}


# =====================================================================
#  Cuentas (solo versión web)
# =====================================================================
ESQUEMA_CUENTAS = """CREATE TABLE IF NOT EXISTS cuentas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT UNIQUE, hash TEXT, creado TEXT, ultimo_ingreso TEXT)"""
RE_USUARIO = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")
INTENTOS = {}          # ip → [tiempos de intentos fallidos] (freno simple contra adivinar contraseñas)


def _cuentas():
    c = conectar_cuentas()
    if not ya_inicializado("cuentas"):
        c.executescript(ESQUEMA_CUENTAS)
        c.commit()
        marcar_inicializado("cuentas")
    return c


def _frenar(ip):
    ahora = time.time()
    with LOCK:
        lista = [t for t in INTENTOS.get(ip, []) if ahora - t < 600]
        INTENTOS[ip] = lista
        if len(lista) >= 8:
            raise PermissionError("Demasiados intentos. Esperá unos minutos y probá de nuevo.")


def _fallo(ip):
    with LOCK:
        INTENTOS.setdefault(ip, []).append(time.time())


def api_registrarse(p, ip):
    _frenar(ip)
    codigo = os.environ.get("CODIGO_INVITACION", "").strip()
    if codigo and not secrets.compare_digest(str(p.get("codigo", "")).strip(), codigo):
        _fallo(ip)
        raise PermissionError("El código de invitación no es correcto. Pedíselo a quien te pasó el link.")
    usuario = str(p.get("usuario", "")).strip().lower()
    password = str(p.get("password", ""))
    if not RE_USUARIO.match(usuario):
        raise ValueError("El usuario tiene que tener entre 3 y 30 letras, números, puntos o guiones (sin espacios).")
    if len(password) < 8:
        raise ValueError("La contraseña tiene que tener al menos 8 caracteres.")
    c = _cuentas()
    try:
        if c.execute("SELECT 1 FROM cuentas WHERE usuario=?", (usuario,)).fetchone():
            raise ValueError("Ese usuario ya existe. Elegí otro o iniciá sesión.")
        cur = c.execute("INSERT INTO cuentas(usuario, hash, creado, ultimo_ingreso) VALUES (?,?,?,?)",
                        (usuario, seguridad.hash_password(password), datetime.now().isoformat(timespec="seconds"),
                         datetime.now().isoformat(timespec="seconds")))
        c.commit()
        uid = cur.lastrowid
    finally:
        c.close()
    return {"ok": True, "_sesion": seguridad.crear_sesion(uid, usuario)}


def api_ingresar(p, ip):
    _frenar(ip)
    usuario = str(p.get("usuario", "")).strip().lower()
    c = _cuentas()
    try:
        r = c.execute("SELECT id, hash FROM cuentas WHERE usuario=?", (usuario,)).fetchone()
        if not r or not seguridad.verificar_password(str(p.get("password", "")), r["hash"]):
            _fallo(ip)
            raise PermissionError("Usuario o contraseña incorrectos.")
        c.execute("UPDATE cuentas SET ultimo_ingreso=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"), r["id"]))
        c.commit()
        uid = r["id"]
    finally:
        c.close()
    return {"ok": True, "_sesion": seguridad.crear_sesion(uid, usuario)}


def api_borrar_cuenta(p):
    """Borra la cuenta y TODOS los datos de la persona (configuración, credenciales, CVs e historial)."""
    u = usuario_actual()
    c = _cuentas()
    try:
        r = c.execute("SELECT hash FROM cuentas WHERE id=?", (u.uid,)).fetchone()
        if not r or not seguridad.verificar_password(str(p.get("password", "")), r["hash"]):
            raise PermissionError("La contraseña no es correcta.")
        if es_postgres():
            c.execute(f'DROP SCHEMA IF EXISTS "u{u.uid}" CASCADE')
        else:
            archivo = ruta(f"datos/web/usuario_{u.uid}.db")
            if archivo.exists():
                archivo.unlink()
        c.execute("DELETE FROM cuentas WHERE id=?", (u.uid,))
        c.commit()
    finally:
        c.close()
    return {"ok": True, "_salir": True}


# =====================================================================
#  Rutas
# =====================================================================
GET = {
    "/api/config": api_config, "/api/intencion": api_intencion, "/api/tandas": api_tandas,
    "/api/whatsapp": api_whatsapp, "/api/historial": api_historial, "/api/job": api_job,
    "/api/plantillas": api_plantillas, "/api/portales": api_portales,
}
POST = {
    "/api/buscar": api_buscar, "/api/buscan": api_buscan, "/api/deshacer": api_deshacer,
    "/api/ajustes/apariencia": api_apariencia, "/api/enviar": api_enviar, "/api/marcar": api_marcar, "/api/abrir": api_abrir,
    "/api/seleccion": lambda p: guardar_seleccion(int(p["tanda"]), p.get("aprobados", []), p.get("excluidos", [])),
    "/api/ajustes/yo": api_guardar_yo, "/api/ajustes/preferencias": api_guardar_preferencias,
    "/api/ajustes/perfil": api_guardar_perfil, "/api/ajustes/perfil/nuevo": api_nuevo_perfil,
    "/api/ajustes/perfil/borrar": api_borrar_perfil, "/api/ajustes/rubro": api_guardar_rubro,
    "/api/ajustes/rubro/borrar": api_borrar_rubro, "/api/plantillas": api_guardar_plantilla,
    "/api/plantillas/preview": api_preview_plantilla, "/api/cvs": api_subir_cv, "/api/cvs/defecto": api_cv_defecto,
    "/api/cvs/borrar": api_borrar_cv, "/api/env": api_guardar_env, "/api/probar/gmail": api_probar_gmail,
    "/api/probar/google": api_probar_google, "/api/portales/generar": api_portales_generar,
    "/api/portales/abierta": api_portales_abierta, "/api/portales/borrar": api_portales_borrar_busqueda,
    "/api/ofertas": api_oferta, "/api/ofertas/estado": api_oferta_estado, "/api/ofertas/notas": api_oferta_notas,
    "/api/ofertas/borrar": api_oferta_borrar, "/api/apagar": api_apagar, "/api/cuenta/borrar": api_borrar_cuenta,
}
PUBLICAS_POST = {"/api/ingresar": api_ingresar, "/api/registrarse": api_registrarse}


# =====================================================================
#  WSGI
# =====================================================================
ESTADOS = {200: "200 OK", 302: "302 Found", 400: "400 Bad Request", 401: "401 Unauthorized", 403: "403 Forbidden",
           404: "404 Not Found", 409: "409 Conflict", 413: "413 Payload Too Large", 429: "429 Too Many Requests",
           500: "500 Internal Server Error"}
CABECERAS_SEGURIDAD = [("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "same-origin"),
                       ("X-Frame-Options", "SAMEORIGIN")]


class Respuesta:
    def __init__(self, cuerpo=b"", codigo=200, tipo="application/json; charset=utf-8", extra=None):
        self.cuerpo = cuerpo if isinstance(cuerpo, bytes) else cuerpo.encode()
        self.codigo, self.tipo, self.extra = codigo, tipo, list(extra or [])


def _json(data, codigo=200, extra=None):
    return Respuesta(json.dumps(data, ensure_ascii=False, default=str), codigo, extra=(extra or []) + [("Cache-Control", "no-store")])


def _archivo(path, tipo, extra=None):
    return Respuesta(path.read_bytes(), 200, tipo, (extra or []) + [("Cache-Control", "no-store")])


def _es_https(environ):
    return environ.get("wsgi.url_scheme") == "https" or environ.get("HTTP_X_FORWARDED_PROTO", "").split(",")[0].strip() == "https"


def _cookie_sesion(environ, valor, max_age=seguridad.DURACION_SESION):
    c = f"{COOKIE_SESION}={valor}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
    return ("Set-Cookie", c + ("; Secure" if _es_https(environ) else ""))


def _ip(environ):
    reenviada = environ.get("HTTP_X_FORWARDED_FOR", "")
    return reenviada.split(",")[0].strip() if reenviada else environ.get("REMOTE_ADDR", "")


def _host_permitido_local(environ):
    """Versión local: solo responde a 127.0.0.1/localhost (y a la IP de la red con --red). Evita «DNS rebinding»."""
    host = environ.get("HTTP_HOST", "")
    permitidos = {f"127.0.0.1:{PUERTO}", f"localhost:{PUERTO}"} | {o.split("://", 1)[1] for o in ORIGENES_EXTRA}
    return host in permitidos


def _origen_ok(environ):
    """Un POST tiene que venir de esta misma página (protección contra pedidos falsificados desde otros sitios)."""
    origen = environ.get("HTTP_ORIGIN")
    if not origen:
        return True
    return urllib.parse.urlparse(origen).netloc == environ.get("HTTP_HOST", "")


def _leer_cuerpo(environ):
    try:
        n = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        n = 0
    if n > MAX_CUERPO:
        raise OverflowError("El archivo es demasiado grande (máximo 12 MB por CV)")
    datos = environ["wsgi.input"].read(n) if n else b""
    return json.loads(datos or b"{}")


def _atender(environ):
    metodo = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/") or "/"
    try:   # WSGI entrega la ruta ya decodificada como latin-1: se pasa a UTF-8 (nombres con tildes, como «CV_Lucía.pdf»)
        path = path.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    q = dict(urllib.parse.parse_qsl(environ.get("QUERY_STRING", "")))
    cookies = SimpleCookie(environ.get("HTTP_COOKIE", ""))
    ip = _ip(environ)

    if path == "/salud":
        return Respuesta("ok", 200, "text/plain; charset=utf-8")
    if path == "/temas.js":
        return _archivo(ruta("app/ui/temas.js"), "application/javascript; charset=utf-8")

    # ---------------- ¿quién es? ----------------
    if WEB:
        sesion = seguridad.leer_sesion(cookies[COOKIE_SESION].value) if COOKIE_SESION in cookies else None
        usuario = UsuarioWeb(sesion["uid"], sesion["usuario"]) if sesion else None
    else:
        if not _host_permitido_local(environ):
            return _json({"error": "host no permitido"}, 403)
        remoto = environ.get("REMOTE_ADDR", "") not in ("127.0.0.1", "::1")
        if TOKEN and remoto and q.get("t") != TOKEN and ("pt" not in cookies or cookies["pt"].value != TOKEN):
            return _json({"error": "Falta la clave: abrí el link completo que muestra la PC"}, 403)
        usuario = LOCAL

    # ---------------- páginas ----------------
    if metodo == "GET" and path in ("/", "/index.html"):
        if WEB and not usuario:
            return Respuesta(b"", 302, extra=[("Location", "/ingreso")])
        extra = [("Set-Cookie", f"pt={TOKEN}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000")] if (TOKEN and q.get("t") == TOKEN) else []
        return _archivo(UI_HTML, "text/html; charset=utf-8", extra)
    if metodo == "GET" and path == "/ingreso":
        if not WEB:
            return Respuesta(b"", 302, extra=[("Location", "/")])
        if usuario:
            return Respuesta(b"", 302, extra=[("Location", "/")])
        return _archivo(UI_INGRESO, "text/html; charset=utf-8")

    # ---------------- sesión ----------------
    if metodo == "POST" and path in PUBLICAS_POST:
        if not WEB:
            return _json({"error": "no disponible"}, 404)
        if not _origen_ok(environ):
            return _json({"error": "origen no permitido"}, 403)
        res = PUBLICAS_POST[path](_leer_cuerpo(environ), ip)
        return _json({"ok": True}, extra=[_cookie_sesion(environ, res["_sesion"])])
    if path == "/api/salir":
        return _json({"ok": True}, extra=[_cookie_sesion(environ, "", 0)])

    if WEB and not usuario:
        if path.startswith("/api/") or path.startswith("/cvs/"):
            return _json({"error": "Tenés que iniciar sesión", "login": True}, 401)
        return Respuesta(b"", 302, extra=[("Location", "/ingreso")])

    # ---------------- API (siempre «como» el usuario de la sesión) ----------------
    with como(usuario):
        if metodo == "GET":
            if path.startswith("/cvs/"):
                nombre, datos = ajustes.leer_cv(path[5:])
                return Respuesta(datos, 200, "application/pdf",
                                 [("Content-Disposition", f"inline; filename*=UTF-8''{urllib.parse.quote(nombre)}"), ("Cache-Control", "no-store")])
            if path.startswith("/api/tanda/"):
                return _json(api_tanda(q, int(path.rsplit("/", 1)[1])))
            if path.startswith("/api/preview/"):
                return _json(api_preview(q, int(path.rsplit("/", 1)[1])))
            if path.startswith("/api/csv/"):
                with conexion() as db:
                    lugares, historial = db.csv_textos()
                es_hist = path.endswith("historial")
                nombre = "historial_envios.csv" if es_hist else "lugares.csv"
                texto = "﻿" + (historial if es_hist else lugares)       # BOM: Excel muestra bien los acentos
                return Respuesta(texto.encode("utf-8"), 200, "text/csv; charset=utf-8",
                                 [("Content-Disposition", f'attachment; filename="{nombre}"'), ("Cache-Control", "no-store")])
            if path in GET:
                return _json(GET[path](q))
            return _json({"error": "no encontrado"}, 404)
        if metodo == "POST":
            if not _origen_ok(environ):
                return _json({"error": "origen no permitido"}, 403)
            if path not in POST:
                return _json({"error": "no encontrado"}, 404)
            res = POST[path](_leer_cuerpo(environ))
            if isinstance(res, dict) and res.pop("_salir", False):
                return _json(res, extra=[_cookie_sesion(environ, "", 0)])
            return _json(res)
    return _json({"error": "método no permitido"}, 400)


def aplicacion(environ, start_response):
    try:
        r = _atender(environ)
    except PermissionError as e:
        r = _json({"error": str(e)}, 429 if "intentos" in str(e) else 403)
    except OverflowError as e:
        r = _json({"error": str(e)}, 413)
    except RuntimeError as e:
        r = _json({"error": str(e)}, 409)
    except (ValueError, KeyError, FileNotFoundError) as e:
        r = _json({"error": str(e)}, 400)
    except Exception as e:
        traceback.print_exc(file=sys.__stderr__)
        r = _json({"error": "Error interno del servidor" if WEB else str(e)}, 500)
    cabeceras = [("Content-Type", r.tipo), ("Content-Length", str(len(r.cuerpo)))] + CABECERAS_SEGURIDAD + r.extra
    start_response(ESTADOS.get(r.codigo, f"{r.codigo} Error"), cabeceras)
    return [r.cuerpo]


def crear_app(web: bool = False):
    """Devuelve la aplicación WSGI. web=True → multiusuario con login (lo usa wsgi.py / gunicorn)."""
    global WEB
    WEB = web
    instalar_despachador()
    mimetypes.add_type("application/pdf", ".pdf")
    if web:
        seguridad.secret_key()       # falla al arrancar (y no a mitad de uso) si falta SECRET_KEY en el hosting
        c = _cuentas()
        c.close()
    return aplicacion


# =====================================================================
#  Servidor local (sin gunicorn): hilos + WSGI de la biblioteca estándar
# =====================================================================
def servidor_wsgi(host, puerto, app):
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

    class ServidorHilos(ThreadingMixIn, WSGIServer):
        daemon_threads = True
        allow_reuse_address = True

    class Silencioso(WSGIRequestHandler):
        def log_message(self, *a):
            pass

    return make_server(host, puerto, app, server_class=ServidorHilos, handler_class=Silencioso)


def ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # no manda nada: solo sirve para saber qué IP usa la PC en tu red
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    """Versión de escritorio (una persona): python app_postulador.py"""
    global PUERTO, TOKEN, SERVIDOR
    import argparse
    ap = argparse.ArgumentParser(description=f"{NOMBRE}: interfaz visual")
    ap.add_argument("--puerto", type=int, default=PUERTO)
    ap.add_argument("--navegador", action="store_true", help="abrir en el navegador aunque esté pywebview")
    ap.add_argument("--sin-abrir", action="store_true", help="no abrir nada (solo levantar el servidor)")
    ap.add_argument("--red", action="store_true", help="permitir abrirla desde el celular en el mismo Wi-Fi (con clave)")
    a = ap.parse_args()
    PUERTO = a.puerto
    app = crear_app(web=False)
    host = "127.0.0.1"
    if a.red:
        host, TOKEN = "0.0.0.0", secrets.token_urlsafe(9)
        ip = ip_local()
        ORIGENES_EXTRA.add(f"http://{ip}:{PUERTO}")
    url = f"http://127.0.0.1:{PUERTO}"
    try:
        SERVIDOR = servidor_wsgi(host, PUERTO, app)
    except OSError:
        print(f"{NOMBRE} ya está abierto en {url}. Lo abro en el navegador.")
        webbrowser.open(url)
        return
    print(f"{NOMBRE} listo en {url}  (cerrá esta ventana, Ctrl+C o el botón «Cerrar app» para salir)")
    if a.red:
        print("\n📱 Para abrirlo desde el celular (conectado al MISMO Wi-Fi que esta PC), entrá a:")
        print(f"\n     http://{ip}:{PUERTO}/?t={TOKEN}\n")
        print("   Ese link tiene una clave nueva cada vez que abrís la app: no lo compartas.")
        print("   Si Windows pregunta por el firewall, permití el acceso en 'Redes privadas'.\n")
    if not a.sin_abrir and not a.navegador:
        try:
            import webview  # opcional: pip install pywebview  → ventana propia
            threading.Thread(target=SERVIDOR.serve_forever, daemon=True).start()
            webview.create_window(NOMBRE, url, width=1360, height=880, min_size=(980, 640))
            webview.start()
            SERVIDOR.shutdown()
            return
        except ImportError:
            pass
    if not a.sin_abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        SERVIDOR.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{NOMBRE} cerrado.")
