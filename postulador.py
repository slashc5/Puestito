#!/usr/bin/env python3
"""
POSTULADORSITO — busca lugares por rubro (o lo que sea) y zona, arma mensajes por perfil, adjunta el CV
correspondiente y gestiona los envíos (mail / WhatsApp) con historial.

Uso rápido:
    python postulador.py                 -> menú guiado (lo más fácil)
    python postulador.py buscar --perfil comercial --rubro "bares" --zona "Temperley" --limite 5
    python postulador.py revisar         -> resumen + mensajes de la última tanda, y aprobación
    python postulador.py enviar          -> manda mails / deja borradores de la tanda aprobada
    python postulador.py whatsapp        -> genera página con links de WhatsApp listos
    python postulador.py whatsapp --interactivo  -> abre uno por uno y registra si lo enviaste
    python postulador.py marcar --ids 3,4 --canal whatsapp
    python postulador.py marcar --ids 7 --estado respondio
    python postulador.py estado          -> resumen general e historial
    python postulador.py exportar        -> genera datos/lugares.csv y datos/historial_envios.csv
"""
import argparse
import random
import sys
import time
import webbrowser

from app.config import Config, ruta
from app.correo import Correo, adjunto_de, armar_mail
from app.db import DB
from app.fuentes import FUENTES, enriquecer
from app.mensajes import mensaje_mail, mensaje_whatsapp
from app.whatsapp import enlace, numero_para, pagina_html

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ---------------------------------------------------------------- utilidades de consola
def preguntar(texto, opciones=None, defecto=None):
    while True:
        r = input(f"{texto}{f' [{defecto}]' if defecto else ''}: ").strip()
        if not r and defecto is not None:
            return defecto
        if not opciones or r in opciones:
            return r
        print("  Opción no válida.")


def elegir(titulo, items, permitir_otro=False):
    print(f"\n{titulo}")
    for i, it in enumerate(items, 1):
        print(f"  {i}. {it}")
    if permitir_otro:
        print("  0. Otro (escribirlo)")
    while True:
        r = input("> ").strip()
        if permitir_otro and r == "0":
            return input("  Escribí: ").strip()
        if r.isdigit() and 1 <= int(r) <= len(items):
            return items[int(r) - 1]
        if permitir_otro and r and not r.isdigit():
            return r
        print("  Elegí un número de la lista.")


def corto(s, n):
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def tabla(filas, columnas):
    anchos = {c: max(len(c), *(len(str(f.get(c, ""))) for f in filas)) if filas else len(c) for c in columnas}
    print("  " + "  ".join(c.upper().ljust(anchos[c]) for c in columnas))
    print("  " + "  ".join("-" * anchos[c] for c in columnas))
    for f in filas:
        print("  " + "  ".join(str(f.get(c, "")).ljust(anchos[c]) for c in columnas))


def canal_para(lugar, preferido):
    tiene_mail = bool(lugar["email"])
    num = numero_para(lugar)
    if preferido == "mail":
        return ("mail", lugar["email"]) if tiene_mail else ("—", "")
    if preferido == "whatsapp":
        return ("whatsapp", num) if num else ("—", "")
    if tiene_mail:
        return "mail", lugar["email"]
    if num:
        return "whatsapp", num
    return "—", ""


def tanda_o_ultima(db, tid):
    t = db.tanda(tid) if tid else db.ultima_tanda()
    if not t:
        sys.exit("Todavía no hay tandas. Empezá con: python postulador.py buscar ... (o sin argumentos para el menú)")
    return t


# ---------------------------------------------------------------- BUSCAR
def perfil_de_tanda(cfg, t) -> dict:
    """Perfil de la tanda, con el CV elegido para esa corrida (o el CV por defecto si el del perfil no está)."""
    p = dict(cfg.perfil(t["perfil"]))
    cv_tanda = t["cv"] if "cv" in t.keys() else None
    if cv_tanda:
        p["cv"] = cv_tanda
    elif not cfg.almacen.existe_cv(p.get("cv", "")) and cfg.cv_defecto():
        p["cv"] = cfg.cv_defecto()
    return p


def rubro_para(cfg, t, l, cfg_rubro=None):
    """Datos del rubro para escribirle a un lugar. En «Buscan gente» cada lugar tiene su propia categoría."""
    modo = t["modo"] if "modo" in t.keys() else "rubro"
    if modo == "buscan" and l["rubro"]:
        return cfg.rubro(l["rubro"])
    return cfg_rubro or cfg.rubro(t["rubro"])


def cmd_buscan(cfg, db, perfil, categorias, zona, limite=None, fuente=None, geo=None, solo_senales=True, cv=None, dias=3):
    """Modo «Lugares que buscan gente»: avisos recientes en portales + webs con señales de búsqueda de personal."""
    from app import portales
    from app.buscan import CATEGORIAS, detectar_empleo, senal_demo
    cfg.perfil(perfil)
    fuente = fuente or cfg.busqueda("fuente", "osm")
    limite = int(limite or cfg.busqueda("limite", 10))
    cats = [CATEGORIAS[c] for c in categorias if c in CATEGORIAS] or list(CATEGORIAS.values())
    etiqueta = " + ".join(c["nombre"] for c in cats)
    tid = db.nueva_tanda(perfil, etiqueta, zona, fuente, geo=geo, modo="buscan", cv=cv)
    donde = f"{zona} (radio {geo['radio_m'] / 1000:g} km)" if geo and geo.get("radio_m") else zona
    print(f"\n🔥 Lugares que buscan gente · {etiqueta} · {donde} (fuente: {fuente}, máx. {limite})")

    # 1) Avisos recientes: búsquedas listas en los portales (no se leen solas: se abren con un clic)
    print(f"\n📰 Avisos de los últimos {dias} días en portales (guardados en «Portales de empleo»):")
    for c in cats:
        for portal, url in portales.links(c["puesto"], zona if zona != "zona elegida" else "", dias).items():
            db.guardar_busqueda_portal(c["puesto"], zona, portal, dias, False, url)
        print(f"   · {c['nombre']}: LinkedIn, Computrabajo, Indeed y Google Empleos")

    # 2) Comercios y empresas de la zona con señales de búsqueda de personal en su web
    print("\n🔎 Revisando webs de la zona en busca de «Trabajá con nosotros», «envianos tu CV», mails de RRHH…")
    c_ = dict(encontrados=0, recuperados=0, sin_senal=0, sin_web=0, contactados=0, revisadas=0)
    cupo = max(1, -(-limite // len(cats)))           # reparte el límite entre las categorías
    vistos = set()
    try:
        for cat in cats:
            hallados_cat, revisadas_cat = 0, 0
            cfg_rubro = {"consultas": cat["consultas"], "osm": cat["osm"], "gancho": cfg.rubro(cat["texto"])["gancho"]}
            for l in FUENTES[fuente](cat["texto"], zona, cfg_rubro, cfg.general, geo=geo, todo=False):
                if hallados_cat >= cupo or c_["encontrados"] + c_["recuperados"] >= limite or revisadas_cat >= cupo * 6:
                    break
                l["rubro"] = cat["nombre"]
                dup = db.buscar_duplicado(l)
                if dup:
                    db.completar_datos(dup["id"], l)
                    if dup["id"] in vistos:
                        continue
                    vistos.add(dup["id"])
                    if db.ya_contactado(dup) or dup["estado"] in ("preparado", "descartado"):
                        c_["contactados"] += 1
                        continue
                    if dup["tanda_id"] == tid:
                        continue
                    puntaje = dup["busca_personal"] or 0
                    web = dup["web"] or l.get("web")
                    if not puntaje and dup["senal_empleo"] is None and web:   # registrado pero nunca revisado: se revisa ahora
                        det = senal_demo(l) if fuente == "demo" else detectar_empleo(web, cfg.busqueda("pausa_web_seg", 1.0))
                        revisadas_cat += 1
                        c_["revisadas"] += 1
                        puntaje = det.get("puntaje", 0)
                        db.actualizar(dup["id"], busca_personal=puntaje, senal_empleo=det.get("senal", ""), url_empleo=det.get("url_empleo", ""))
                        if det.get("email_rrhh"):
                            db.actualizar(dup["id"], email=det["email_rrhh"])
                    if puntaje > 0 or not solo_senales:
                        db.recuperar_en_tanda(dup["id"], tid, perfil, cat["nombre"])
                        c_["recuperados"] += 1
                        hallados_cat += 1
                        if puntaje > 0:
                            print(f"   🔥 {corto(dup['nombre'], 40)} ({puntaje}%): ya lo tenías sin contactar, vuelve a esta tanda")
                    continue
                if not l.get("web"):
                    c_["sin_web"] += 1
                    if solo_senales:
                        continue
                    det = {"puntaje": 0}
                else:
                    det = senal_demo(l) if fuente == "demo" else detectar_empleo(l["web"], cfg.busqueda("pausa_web_seg", 1.0))
                    revisadas_cat += 1
                    c_["revisadas"] += 1
                for k in ("instagram", "facebook", "whatsapp"):
                    l[k] = l.get(k) or det.get(k, "")
                l["email"] = det.get("email_rrhh") or l.get("email") or det.get("email", "")
                l.update(busca_personal=det.get("puntaje", 0), senal_empleo=det.get("senal", ""), url_empleo=det.get("url_empleo", ""))
                if det.get("puntaje", 0) <= 0 and solo_senales:
                    c_["sin_senal"] += 1
                    print(f"   · {corto(l['nombre'], 40)}: sin señales de búsqueda")
                    continue
                if db.buscar_duplicado(l):      # puede coincidir por el mail de RRHH encontrado
                    continue
                db.insertar_lugar(l, tid, perfil)
                c_["encontrados"] += 1
                hallados_cat += 1
                if det.get("puntaje", 0) > 0:
                    print(f"   🔥 {corto(l['nombre'], 40)} ({det['puntaje']}%): {corto(det.get('senal', ''), 90)}")
    except Exception as e:
        print(f"⚠️  Error en la búsqueda: {e}")
    db.exportar_csv()
    print(f"\n✅ Tanda #{tid}: {c_['encontrados']} lugares nuevos · {c_['recuperados']} pendientes recuperados")
    print(f"   Webs revisadas: {c_['revisadas']} · sin señales: {c_['sin_senal']} · sin web: {c_['sin_web']} · "
          f"ya contactados/omitidos: {c_['contactados']}")
    if solo_senales and not c_["encontrados"] + c_["recuperados"]:
        print("   Tip: ampliá el radio, probá otra categoría o desactivá «Solo los que muestran señales».")
    return tid


def cmd_buscar(cfg, db, perfil, rubro, zona, limite=None, fuente=None, geo=None, todo=False, cv=None):
    cfg.perfil(perfil)  # valida
    fuente = fuente or cfg.busqueda("fuente", "osm")
    limite = int(limite or cfg.busqueda("limite", 10))
    if todo:
        rubro = "lo que sea"
    cfg_rubro = cfg.rubro(rubro)
    tid = db.nueva_tanda(perfil, rubro, zona, fuente, geo=geo, modo="todo" if todo else "rubro", cv=cv)
    donde = f"{zona} (radio {geo['radio_m'] / 1000:g} km)" if geo and geo.get("radio_m") else zona
    print(f"\n🔎 Buscando «{rubro}» en {donde} (fuente: {fuente}, máx. {limite} lugares)…")
    c = dict(nuevos=0, recuperados=0, contactados=0, preparados=0, descartados=0, repetidos=0)
    vistos = set()

    def ya_registrado(l) -> bool:
        """Decide qué hacer si el lugar ya está en la base. Devuelve True si NO hay que insertarlo."""
        dup = db.buscar_duplicado(l)
        if not dup:
            return False
        db.completar_datos(dup["id"], l)            # nunca se pierden datos nuevos de contacto
        if dup["id"] in vistos:
            return True                                # mismo local repetido en los resultados
        vistos.add(dup["id"])
        if dup["tanda_id"] == tid:
            c["repetidos"] += 1                        # vino dos veces en la misma búsqueda
        elif db.ya_contactado(dup):
            c["contactados"] += 1                      # ya le escribiste: no vuelve a aparecer
        elif dup["estado"] == "preparado":
            c["preparados"] += 1                       # tiene borrador/.eml esperando que lo mandes
        elif dup["estado"] == "descartado":
            c["descartados"] += 1                      # lo descartaste vos a mano
        else:                                          # nuevo / aprobado / excluido y nunca contactado
            db.recuperar_en_tanda(dup["id"], tid, perfil, rubro)
            c["recuperados"] += 1
        return True

    try:
        for l in FUENTES[fuente](rubro, zona, cfg_rubro, cfg.general, geo=geo, todo=todo):
            if c["nuevos"] + c["recuperados"] >= limite:
                break
            if ya_registrado(l):
                continue
            if cfg.busqueda("enriquecer_web", True) and fuente != "demo" and l.get("web"):
                print(f"   · revisando web de {corto(l['nombre'], 40)}…")
                l = enriquecer(l, cfg.busqueda("pausa_web_seg", 1.5))
                if ya_registrado(l):   # puede coincidir por el mail que encontró en la web
                    continue
            db.insertar_lugar(l, tid, perfil)
            c["nuevos"] += 1
    except Exception as e:
        print(f"⚠️  Error en la búsqueda: {e}")
    db.exportar_csv()
    print(f"✅ Tanda #{tid}: {c['nuevos']} nuevos · {c['recuperados']} pendientes recuperados de búsquedas anteriores")
    omitidos = [f"{c['contactados']} ya contactados", f"{c['preparados']} con borrador sin enviar",
                f"{c['descartados']} descartados por vos"]
    print("   Omitidos: " + " · ".join(omitidos))
    return tid


# ---------------------------------------------------------------- REVISAR
def cmd_revisar(cfg, db, tid=None, auto_si=False):
    t = tanda_o_ultima(db, tid)
    perfil = perfil_de_tanda(cfg, t)
    cfg_rubro = cfg.rubro(t["rubro"])
    pref = cfg["envio"]["canal_preferido"]
    lugares = db.lugares_de_tanda(t["id"], ["nuevo", "aprobado"])
    if not lugares:
        print(f"La tanda #{t['id']} no tiene lugares pendientes de revisión.")
        return False
    print(f"\n━━━━━━━━ TANDA #{t['id']} · perfil «{t['perfil']}» · {t['rubro']} · {t['zona']} ━━━━━━━━")
    print(f"CV que se adjunta: {perfil['cv']}")
    filas = []
    for l in lugares:
        canal, destino = canal_para(l, pref)
        redes = "IG " if l["instagram"] else ""
        redes += "FB" if l["facebook"] else ""
        filas.append({"id": l["id"], "lugar": corto(l["nombre"], 28), "dirección": corto(l["direccion"], 26),
                      "canal": canal, "destino": corto(destino, 28), "redes": redes.strip()})
    tabla(filas, ["id", "lugar", "dirección", "canal", "destino", "redes"])
    n_mail = sum(f["canal"] == "mail" for f in filas)
    n_wa = sum(f["canal"] == "whatsapp" for f in filas)
    n_no = len(filas) - n_mail - n_wa
    print(f"\n  📧 {n_mail} por mail · 💬 {n_wa} por WhatsApp · ❔ {n_no} sin mail/celular (quedan con sus redes en la página de WhatsApp)")

    def mostrar(l):
        canal, destino = canal_para(l, pref)
        if canal == "mail" or (canal == "—" and l["email"]):
            asunto, cuerpo = mensaje_mail(l, perfil, rubro_para(cfg, t, l, cfg_rubro), cfg.general)
            print(f"\n── MAIL para #{l['id']} {l['nombre']} <{l['email']}> ──\nAsunto: {asunto}\n\n{cuerpo}\n[Adjunto: {perfil['cv']}]")
        else:
            print(f"\n── WHATSAPP para #{l['id']} {l['nombre']} ({destino or 'sin número'}) ──\n{mensaje_whatsapp(l, perfil, rubro_para(cfg, t, l, cfg_rubro), cfg.general)}")

    ej_mail = next((l for l in lugares if canal_para(l, pref)[0] == "mail"), None)
    ej_wa = next((l for l in lugares if canal_para(l, pref)[0] != "mail"), None)
    for l in (ej_mail, ej_wa):
        if l:
            mostrar(l)

    if auto_si:
        db.set_estado([l["id"] for l in lugares], "aprobado")
        return True
    print("\n¿Qué hacemos?  [Enter] aprobar todos · x 3,5 excluir IDs · v 4 ver mensaje del ID 4 · n cancelar")
    ids_tanda = {l["id"]: l for l in lugares}
    excluidos = set()
    while True:
        r = input("> ").strip().lower()
        if r == "":
            break
        if r == "n":
            print("Cancelado. Nada se envió. Podés volver con: python postulador.py revisar")
            return False
        if r.startswith("x"):
            for p in r[1:].replace(" ", "").split(","):
                if p.isdigit() and int(p) in ids_tanda:
                    excluidos.add(int(p))
            print(f"  Excluidos: {sorted(excluidos) or 'ninguno'}  (Enter para aprobar el resto)")
        elif r.startswith("v"):
            p = r[1:].strip()
            if p.isdigit() and int(p) in ids_tanda:
                mostrar(ids_tanda[int(p)])
        else:
            print("  No entendí. Enter, x IDs, v ID o n.")
    db.set_estado(list(excluidos), "excluido")
    db.set_estado([i for i in ids_tanda if i not in excluidos], "aprobado")
    print(f"✅ Aprobados {len(ids_tanda) - len(excluidos)} lugares de la tanda #{t['id']}.")
    db.exportar_csv()
    return True


# ---------------------------------------------------------------- ENVIAR (mail) + preparar WhatsApp
def cmd_enviar(cfg, db, tid=None, modo=None, canal=None, auto_si=False, forzar=False):
    t = tanda_o_ultima(db, tid)
    perfil = perfil_de_tanda(cfg, t)
    cfg_rubro = cfg.rubro(t["rubro"])
    env = cfg["envio"]
    modo = modo or env["modo_mail"]
    pref = canal or env["canal_preferido"]
    aprobados = db.lugares_de_tanda(t["id"], ["aprobado"])
    if not aprobados:
        print("No hay lugares aprobados en esta tanda. Corré primero: python postulador.py revisar")
        return

    para_mail, para_wa, omitidos = [], [], []
    for l in aprobados:
        c, destino = canal_para(l, pref)
        previo = db.ya_contactado(l, destino)
        if previo and not forzar:
            omitidos.append((l, previo))
            continue
        prep = db.ya_preparado(l)
        if prep and c == "mail" and not forzar:
            print(f"  ⏭  #{l['id']} {l['nombre']}: ya tiene {prep['estado']} del {str(prep['fecha'])[:10]} sin enviar. "
                  f"Cuando lo mandes: python postulador.py marcar --ids {l['id']} --canal mail")
            continue
        if c == "mail":
            para_mail.append(l)
        else:
            para_wa.append(l)

    for l, p in omitidos:
        print(f"  ⏭  #{l['id']} {l['nombre']}: ya contactado el {str(p['fecha'])[:10]} por {p['canal']} ({p['estado']}). Omitido.")

    restante_dia = max(0, int(env["max_por_dia"]) - db.mails_hoy())
    cupo = min(int(env["max_por_tanda"]), restante_dia)
    if len(para_mail) > cupo:
        print(f"  ⚠️  Límite: se procesan {cupo} mails ahora (tope por tanda {env['max_por_tanda']}, "
              f"quedan {restante_dia} hoy). El resto queda aprobado para la próxima corrida.")
        para_mail = para_mail[:cupo]

    if para_mail:
        etiqueta = {"enviar": "ENVIAR", "borrador": "dejar como BORRADOR en tu Gmail", "eml": "generar archivos .eml"}[modo]
        print(f"\n📧 {len(para_mail)} mails → modo: {etiqueta}. CV: {perfil['cv']}")
        if modo == "enviar":
            print(f"   Pausa aleatoria entre envíos: {env['pausa_min_seg']}–{env['pausa_max_seg']} s")
        if auto_si or preguntar("¿Confirmás? (s/n)", ["s", "n", "S", "N"], "n").lower() == "s":
            _procesar_mails(cfg, db, t, perfil, cfg_rubro, para_mail, modo)
        else:
            print("   Mails no procesados.")

    if para_wa:
        cmd_whatsapp(cfg, db, t["id"], lugares=para_wa)
    db.exportar_csv()


def _procesar_mails(cfg, db, t, perfil, cfg_rubro, lugares, modo):
    env = cfg["envio"]
    if modo == "eml" and cfg.web:
        print("   ❌ En la versión web no hay archivos .eml: elegí «Borradores en Gmail».")
        return
    try:
        adj = adjunto_de(perfil, cfg.almacen)          # el PDF se lee en memoria (archivo local o base de datos)
    except FileNotFoundError as e:
        print(f"   ❌ {e}")
        return
    yo = cfg["yo"]
    carpeta_eml = ruta(f"salidas/eml_tanda_{t['id']}")
    try:
        conexion = Correo(cfg.general, modo)
    except RuntimeError as e:
        print(f"   ❌ {e}")
        return
    try:
        correo = conexion.__enter__()          # conecta a Gmail (SMTP o IMAP)
    except RuntimeError as e:
        print(f"   ❌ {e}")
        return
    try:
        for i, l in enumerate(lugares):
            asunto, cuerpo = mensaje_mail(l, perfil, rubro_para(cfg, t, l, cfg_rubro), cfg.general)
            msg = armar_mail(correo.usuario, yo["nombre"], l["email"], asunto, cuerpo, adj)
            try:
                estado = correo.procesar(msg, carpeta_eml)
                db.registrar_envio(l["id"], t["perfil"], perfil["cv"], "mail", l["email"], estado, asunto)
                print(f"   ✔ [{i + 1}/{len(lugares)}] {l['nombre']} <{l['email']}> → {estado}")
            except Exception as e:
                db.registrar_envio(l["id"], t["perfil"], perfil["cv"], "mail", l["email"], "error", asunto, str(e))
                print(f"   ✖ {l['nombre']}: {e}")
            if modo == "enviar" and i < len(lugares) - 1:
                espera = random.uniform(env["pausa_min_seg"], env["pausa_max_seg"])
                print(f"     …esperando {espera:.0f} s")
                time.sleep(espera)
    finally:
        conexion.__exit__(None, None, None)
    if modo == "eml":
        print(f"   Archivos en: {carpeta_eml}  (doble clic para abrirlos en tu programa de correo)")
    elif modo == "borrador":
        print("   Revisá la carpeta Borradores de tu Gmail y enviá cuando quieras.")


# ---------------------------------------------------------------- WHATSAPP
def cmd_whatsapp(cfg, db, tid=None, lugares=None, interactivo=False):
    t = tanda_o_ultima(db, tid)
    perfil = perfil_de_tanda(cfg, t)
    cfg_rubro = cfg.rubro(t["rubro"])
    if lugares is None:
        pref = cfg["envio"]["canal_preferido"]
        lugares = [l for l in db.lugares_de_tanda(t["id"], ["aprobado"])
                   if not db.ya_contactado(l) and canal_para(l, pref)[0] != "mail"]
    if not lugares:
        print("No hay lugares aprobados pendientes para WhatsApp.")
        return
    items = []
    for l in lugares:
        num = numero_para(l)
        texto = mensaje_whatsapp(l, perfil, rubro_para(cfg, t, l, cfg_rubro), cfg.general)
        link = enlace(num, texto) if num else ""
        items.append(dict(id=l["id"], nombre=l["nombre"], rubro=l["rubro"], direccion=l["direccion"], numero=num,
                          link=link, texto=texto, instagram=l["instagram"], facebook=l["facebook"], web=l["web"]))
        ya_prep = db.con.execute("SELECT 1 FROM envios WHERE lugar_id=? AND estado='whatsapp_preparado'",
                                 (l["id"],)).fetchone()
        if num and not ya_prep:
            db.registrar_envio(l["id"], t["perfil"], perfil["cv"], "whatsapp", num, "whatsapp_preparado")
    if cfg.web:   # en la web los chats se ven en la pestaña WhatsApp (no se generan archivos)
        print(f"\n💬 {sum(bool(i['link']) for i in items)} chats de WhatsApp listos "
              f"(+{sum(not i['link'] for i in items)} solo con redes). Están en la pestaña WhatsApp.")
        return
    archivo = pagina_html(items, f"WhatsApp · tanda #{t['id']} · {t['rubro']} · {t['zona']}", perfil["cv"])
    print(f"\n💬 {sum(bool(i['link']) for i in items)} chats de WhatsApp listos "
          f"(+{sum(not i['link'] for i in items)} solo con redes). Página: {archivo}")

    if not interactivo:
        print("   Abrila en el navegador. Cuando envíes, registrá con: "
              "python postulador.py marcar --ids ... --canal whatsapp")
        return
    print("\nModo interactivo: abro cada chat; vos revisás y tocás Enviar en WhatsApp.")
    for it in items:
        if not it["link"]:
            continue
        r = input(f"\n#{it['id']} {it['nombre']} (+{it['numero']}) — [Enter] abrir · s saltar · q salir: ").strip().lower()
        if r == "q":
            break
        if r == "s":
            continue
        webbrowser.open(it["link"])
        ok = input("   ¿Lo enviaste? (s/n): ").strip().lower()
        if ok == "s":
            db.registrar_envio(it["id"], t["perfil"], perfil["cv"], "whatsapp", it["numero"], "whatsapp_enviado")
            print("   ✔ registrado")
        time.sleep(1)
    db.exportar_csv()


# ---------------------------------------------------------------- MARCAR / ESTADO
def cmd_marcar(cfg, db, ids, canal=None, estado=None):
    for i in ids:
        l = db.lugar(i)
        if not l:
            print(f"  #{i} no existe")
            continue
        if canal:
            t = db.tanda(l["tanda_id"]) if l["tanda_id"] else None
            perfil = perfil_de_tanda(cfg, t) if t and t["perfil"] in cfg.perfiles else cfg.perfiles.get(l["perfil"], {})
            destino = numero_para(l) if canal == "whatsapp" else (l["email"] or "")
            est = "whatsapp_enviado" if canal == "whatsapp" else "enviado"
            db.registrar_envio(i, l["perfil"], perfil.get("cv", ""), canal, destino, est, detalle="marcado manualmente")
        if estado:
            db.set_estado([i], estado)
        print(f"  ✔ #{i} {l['nombre']} actualizado")
    db.exportar_csv()


def cmd_estado(db):
    print("\nLugares por estado:")
    tabla([dict(estado=r["estado"], cantidad=r["n"]) for r in db.resumen()], ["estado", "cantidad"])
    print(f"\nMails procesados hoy: {db.mails_hoy()}")
    print("\nÚltimos envíos:")
    tabla([dict(fecha=r["fecha"][:16].replace("T", " "), lugar=corto(r["nombre"], 28), canal=r["canal"],
                estado=r["estado"], cv=r["cv"].split("/")[-1]) for r in db.historial(20)],
          ["fecha", "lugar", "canal", "estado", "cv"])


# ---------------------------------------------------------------- MENÚ GUIADO
def menu(cfg, db):
    print("╔══════════════════════════════════╗\n║  POSTULADORSITO · corrida nueva  ║\n╚══════════════════════════════════╝")
    nombres = list(cfg.perfiles)
    etiquetas = [f"{n} — {cfg.perfiles[n].get('descripcion', '')} ({cfg.perfiles[n]['cv']})" for n in nombres]
    perfil = nombres[etiquetas.index(elegir("¿Qué perfil / CV usás hoy?", etiquetas))]
    p = cfg.perfiles[perfil]
    rubro = elegir("¿Qué rubro buscás?", p.get("rubros", []), permitir_otro=True)
    zona = elegir("¿En qué zona?", p.get("zonas", []), permitir_otro=True)
    limite = preguntar("¿Cuántos lugares nuevos como máximo?", defecto=str(cfg["busqueda"]["limite"]))
    tid = cmd_buscar(cfg, db, perfil, rubro, zona, limite)
    if not db.lugares_de_tanda(tid):
        print("No se encontraron lugares nuevos. Probá otra zona, otro rubro o la fuente 'google'.")
        return
    if cmd_revisar(cfg, db, tid):
        cmd_enviar(cfg, db, tid)
    cmd_estado(db)


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Postuladorsito: búsqueda de lugares y envío de CVs con historial")
    sub = ap.add_subparsers(dest="cmd")

    b = sub.add_parser("buscar", help="buscar lugares nuevos y guardarlos")
    b.add_argument("--perfil", required=True)
    b.add_argument("--rubro", default="", help="texto libre: 'atención al cliente', 'depósito', 'tiendas de anime'…")
    b.add_argument("--zona", required=True)
    b.add_argument("--limite", type=int)
    b.add_argument("--fuente", choices=list(FUENTES))
    b.add_argument("--lat", type=float, help="centro de la búsqueda (opcional)")
    b.add_argument("--lon", type=float)
    b.add_argument("--radio", type=int, help="radio en metros (con --lat/--lon)")
    b.add_argument("--todo", action="store_true", help="modo 'lo que sea': cualquier rubro en la zona")
    b.add_argument("--cv", help="CV para esta corrida, ej: cvs/CV_ventas.pdf")

    bg = sub.add_parser("buscan", help="lugares que buscan gente (avisos recientes + webs con señales de empleo)")
    bg.add_argument("--perfil", required=True)
    bg.add_argument("--categorias", default="", help="atencion,it,ventas,gastro,admin (vacío = todas)")
    bg.add_argument("--zona", required=True)
    bg.add_argument("--limite", type=int)
    bg.add_argument("--fuente", choices=list(FUENTES))
    bg.add_argument("--lat", type=float)
    bg.add_argument("--lon", type=float)
    bg.add_argument("--radio", type=int)
    bg.add_argument("--todos", action="store_true", help="incluir también los que no muestran señales")
    bg.add_argument("--cv")

    r = sub.add_parser("revisar", help="ver resumen y mensajes; aprobar la tanda")
    r.add_argument("--tanda", type=int)

    e = sub.add_parser("enviar", help="procesar mails y preparar WhatsApp de la tanda aprobada")
    e.add_argument("--tanda", type=int)
    e.add_argument("--modo", choices=["borrador", "enviar", "eml"])
    e.add_argument("--canal", choices=["auto", "mail", "whatsapp"])
    e.add_argument("--si", action="store_true", help="no pedir confirmación")
    e.add_argument("--forzar", action="store_true", help="incluir lugares ya contactados (¡cuidado!)")

    w = sub.add_parser("whatsapp", help="generar links de WhatsApp")
    w.add_argument("--tanda", type=int)
    w.add_argument("--interactivo", action="store_true")

    m = sub.add_parser("marcar", help="registrar envíos manuales o cambiar estado")
    m.add_argument("--ids", required=True, help="ej: 3,4,10")
    m.add_argument("--canal", choices=["mail", "whatsapp"])
    m.add_argument("--estado", choices=["respondio", "descartado", "contactado", "aprobado", "excluido", "nuevo"])

    sub.add_parser("estado", help="resumen e historial")
    sub.add_parser("exportar", help="exportar CSV")

    a = ap.parse_args()
    cfg, db = Config(), DB()
    try:
        if a.cmd is None:
            menu(cfg, db)
        elif a.cmd == "buscar":
            if not a.rubro and not a.todo:
                sys.exit("Indicá --rubro \"...\" o usá --todo")
            geo = {"lat": a.lat, "lon": a.lon, "radio_m": a.radio or 3000} if a.lat is not None and a.lon is not None else None
            cmd_buscar(cfg, db, a.perfil, a.rubro, a.zona, a.limite, a.fuente, geo=geo, todo=a.todo, cv=a.cv)
        elif a.cmd == "buscan":
            geo = {"lat": a.lat, "lon": a.lon, "radio_m": a.radio or 3000} if a.lat is not None and a.lon is not None else None
            cmd_buscan(cfg, db, a.perfil, [c.strip() for c in a.categorias.split(",") if c.strip()], a.zona, a.limite,
                       a.fuente, geo=geo, solo_senales=not a.todos, cv=a.cv)
        elif a.cmd == "revisar":
            cmd_revisar(cfg, db, a.tanda)
        elif a.cmd == "enviar":
            cmd_enviar(cfg, db, a.tanda, a.modo, a.canal, a.si, a.forzar)
        elif a.cmd == "whatsapp":
            cmd_whatsapp(cfg, db, a.tanda, interactivo=a.interactivo)
        elif a.cmd == "marcar":
            cmd_marcar(cfg, db, [int(x) for x in a.ids.split(",") if x.strip().isdigit()], a.canal, a.estado)
        elif a.cmd == "estado":
            cmd_estado(db)
        elif a.cmd == "exportar":
            print("Exportado:", *db.exportar_csv())
    except KeyboardInterrupt:
        print("\nInterrumpido. Lo hecho hasta acá quedó registrado.")


if __name__ == "__main__":
    main()
