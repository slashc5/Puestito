"""Armado de mensajes personalizados a partir de plantillas."""
import re

from .config import ruta


class _Seguro(dict):
    def __missing__(self, k):
        return ""


def _get(fila, k):
    try:
        return fila[k]
    except (KeyError, IndexError):
        return None


def variables(lugar, perfil: dict, cfg_rubro: dict, cfg) -> dict:
    yo = cfg["yo"]
    cv_link = perfil.get("cv_link", "")
    return _Seguro(
        lugar=lugar["nombre"],
        rubro=lugar["rubro"],
        zona=lugar["zona"],
        gancho=cfg_rubro.get("gancho", "").rstrip("."),
        mi_nombre=yo.get("nombre", ""),
        mi_telefono=yo.get("telefono", ""),
        mi_email=yo.get("email", ""),
        mi_zona=yo.get("zona", ""),
        mi_linkedin=("· " + yo["linkedin"]) if yo.get("linkedin") else "",
        cv_link=cv_link,
        cv_link_texto=(f"Les dejo mi CV: {cv_link} " if cv_link else ""),
        busqueda_activa=("Vi que están buscando gente, así que les escribo." if _get(lugar, "busca_personal") else ""),
    )


_VAR = re.compile(r"\{(\w+)\}")


def formatear(texto: str, vars_: dict) -> str:
    """Reemplaza {variable} por su valor. Una llave suelta no rompe nada (queda tal cual)."""
    return _VAR.sub(lambda m: str(vars_.get(m.group(1), "")), texto)


def render(plantilla_rel: str, vars_: dict, almacen=None) -> str:
    texto = almacen.leer_plantilla(plantilla_rel) if almacen else ruta(plantilla_rel).read_text(encoding="utf-8")
    return formatear(texto, vars_).strip()


def mensaje_mail(lugar, perfil, cfg_rubro, cfg):
    v = variables(lugar, perfil, cfg_rubro, cfg)
    asunto = formatear(perfil.get("asunto", "Postulación – {mi_nombre}"), v)
    return asunto, render(perfil["plantilla_mail"], v, cfg.get("_almacen"))


def mensaje_whatsapp(lugar, perfil, cfg_rubro, cfg):
    v = variables(lugar, perfil, cfg_rubro, cfg)
    return " ".join(render(perfil["plantilla_whatsapp"], v, cfg.get("_almacen")).split())
