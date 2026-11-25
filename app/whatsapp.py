"""WhatsApp: enlaces wa.me con el mensaje ya armado + página HTML para ir abriéndolos a mano.

No se envía nada automáticamente: vos apretás "Enviar" en cada chat. Así no hay riesgo de bloqueo.
"""
import html
import urllib.parse
from datetime import datetime

from .config import ruta
from .util import telefono_whatsapp_ar


def numero_para(lugar) -> str:
    return telefono_whatsapp_ar(lugar["whatsapp"] or "") or telefono_whatsapp_ar(lugar["telefono"] or "")


def enlace(numero: str, texto: str) -> str:
    return f"https://wa.me/{numero}?text={urllib.parse.quote(texto)}"


def pagina_html(items: list[dict], titulo: str, cv_path: str):
    """items: [{id, nombre, rubro, direccion, numero, link, texto, instagram, facebook, web}]"""
    tarjetas = []
    for it in items:
        e = {k: html.escape(str(v or "")) for k, v in it.items()}
        redes = " · ".join(
            f'<a href="{e[k]}" target="_blank">{n}</a>' for k, n in (("web", "Web"), ("instagram", "Instagram"), ("facebook", "Facebook")) if it.get(k))
        boton = (f'<a class="btn" href="{e["link"]}" target="_blank" onclick="marcar(this)">Abrir WhatsApp</a>'
                 if it.get("link") else '<span class="sin">Sin número válido: contactá por redes</span>')
        tarjetas.append(f"""
<div class="card" id="c{e['id']}">
  <div class="top"><b>#{e['id']} · {e['nombre']}</b><span>{e['rubro']}</span></div>
  <div class="dir">{e['direccion']} {('· +' + e['numero']) if it.get('numero') else ''}</div>
  <textarea readonly>{e['texto']}</textarea>
  <div class="acc">{boton}<button onclick="copiar(this)">Copiar texto</button>{redes}</div>
</div>""")
    doc = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>{html.escape(titulo)}</title><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;background:#f4f5f2;color:#1d1d1b}}
h1{{font-size:20px}} .nota{{background:#fff8e1;border:1px solid #f0d98a;padding:10px 12px;border-radius:8px;font-size:14px}}
.card{{background:#fff;border:1px solid #ddd;border-radius:10px;padding:14px;margin:14px 0}}
.card.hecho{{opacity:.45}} .top{{display:flex;justify-content:space-between;gap:8px}} .top span{{color:#666;font-size:13px}}
.dir{{color:#555;font-size:13px;margin:4px 0 8px}} textarea{{width:100%;min-height:90px;font:inherit;font-size:14px;box-sizing:border-box}}
.acc{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:8px;font-size:14px}}
.btn{{background:#1f8f4e;color:#fff;padding:7px 12px;border-radius:6px;text-decoration:none}} .sin{{color:#a33}}
button{{padding:6px 10px;border-radius:6px;border:1px solid #bbb;background:#fafafa;cursor:pointer}}
</style></head><body>
<h1>{html.escape(titulo)}</h1>
<p class="nota">Abrí cada chat, revisá el texto y tocá <b>Enviar</b> vos. El CV ({html.escape(cv_path)}) lo adjuntás desde el clip 📎
si te lo piden. Mandá de a pocos (5–10 por día) y espaciados. Al terminar, registrá los enviados con:<br>
<code>python postulador.py marcar --ids 1,2,3 --canal whatsapp</code> (o usá <code>whatsapp --interactivo</code>).</p>
{''.join(tarjetas)}
<script>
function marcar(a){{a.closest('.card').classList.add('hecho')}}
function copiar(b){{const t=b.closest('.card').querySelector('textarea');navigator.clipboard.writeText(t.value);b.textContent='¡Copiado!'}}
</script></body></html>"""
    archivo = ruta(f"salidas/whatsapp_{datetime.now():%Y%m%d_%H%M}.html")
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(doc, encoding="utf-8")
    return archivo
