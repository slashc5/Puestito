# Postuladorsito

Buscá lugares para dejar tu CV por **qué tipo de laburo querés** (o «lo que sea») y **dónde** (marcándolo en un mapa). Postuladorsito arma un mensaje personalizado con el **CV que elijas**, te deja **revisar todo antes de mandar**, envía o prepara mails y WhatsApp **con pausas y topes**, y lleva el **historial**, sin duplicar lugares ni escribirle dos veces al mismo.

También genera búsquedas con filtro de fecha en **LinkedIn, Computrabajo, Indeed y Google Empleos**, y registra las ofertas que viste o a las que te postulaste.

> 🌐 **¿La querés online para tus amigos?** Seguí **[DESPLIEGUE.md](DESPLIEGUE.md)**: GitHub + Render + Neon, gratis. Cada amigo tiene su cuenta y sus datos separados.

**No hace falta editar ningún archivo a mano:** datos, CVs, plantillas, ganchos, claves y preferencias se cargan desde la pestaña **Configuración y CVs**.

- Python 3.11+, sin librerías externas (la ventana propia con `pywebview` es opcional).
- Base local SQLite (`datos/postulaciones.db`) + exportación a CSV.
- Todo corre en tu PC. Solo sale a internet para buscar lugares, mostrar el mapa y mandar mails.

---

## 1. Abrir la app

| Cómo | Para qué |
|---|---|
| **`iniciar_silencioso.vbs`** (doble clic, Windows) | Abre la app sin ventana negra. Se cierra con el botón **⏻ Cerrar Postuladorsito** (en Configuración). |
| `abrir_app.bat` | Igual, pero con la ventana negra visible (útil para ver errores). |
| `abrir_app_celular.bat` | Para usarla desde el celu en el mismo Wi-Fi (muestra un link con clave). |
| `abrir_app.command` (Mac) / `python app_postulador.py` | Cualquier sistema. |
| `python postulador.py` | La versión de consola de siempre (sigue funcionando). |

La app vive en **http://127.0.0.1:8765**. Si instalás `pip install pywebview`, se abre en una ventana propia en lugar del navegador.
Abierta en modo silencioso, los mensajes técnicos quedan en `datos/postuladorsito.log`.

## 2. Primera vez (5 minutos, todo desde la app)

En **Configuración y CVs**:
1. **Mis datos**: nombre, teléfono, mail, zona, LinkedIn.
2. **CVs**: arrastrá tus PDF. Elegí uno **por defecto** y asigná cada uno a un perfil.
3. **Claves y conexión**: tu Gmail y la **contraseña de aplicación** (se genera en myaccount.google.com/apppasswords) → **Probar conexión Gmail**. Si vas a usar Google Places, pegá la clave y tocá **Probar clave**.
4. **Plantillas** y **Ganchos**: retocá los textos si querés. Los botones `{lugar}`, `{gancho}`… insertan las variables y a la derecha ves cómo queda.

## 3. Uso diario

1. **Buscar**
   - Elegí perfil y CV.
   - Escribí qué buscás, como «atención al cliente», «depósito», «tiendas de anime» o «soporte IT». La app lo traduce a varias búsquedas concretas y te muestra cuáles va a hacer. Si no te importa el rubro, activá **Lo que sea**: trae comercios y empresas de cualquier rubro de la zona.
   - Elegí la zona de una de estas tres formas: **Usar mi ubicación**, el **buscador de direcciones** o **tocar el mapa**. El pin se puede arrastrar y el radio se ajusta con la barra, entre 300 m y 20 km.
2. **Revisión y envío**: tildá a quién escribirle, mirá la vista previa exacta del mail y del WhatsApp, y tocá **Procesar tanda**. Antes de hacer nada, te pide confirmación.
3. **WhatsApp**: abrís cada chat con el mensaje listo, lo mandás vos y lo marcás como enviado. Para ir rápido, usá la **⚡ Cola rápida** (sección 3 bis).
4. **Portales de empleo**: escribí el puesto y la ubicación, elegí desde cuándo y tocá **Generar búsquedas**. Pegá el link de una oferta para guardarla y marcala como **Vista**, **Me postulé** o **Descartada**. La postulación la hacés vos dentro de cada portal: nada se automatiza ahí, para que no te bloqueen la cuenta.
5. **Historial**: todo lo enviado, los contadores y la descarga de CSV.

## 3 bis. Modos nuevos

### 🔥 Lugares que buscan gente
En **Buscar**, elegí el modo **Buscan gente** y una o varias categorías: Atención al cliente, Soporte IT / Técnico, Ventas / Local comercial, Gastronomía o Administración / Depósito.

- **Webs con señales:** busca comercios y empresas de esa categoría dentro del radio y revisa su web. Busca secciones «Trabajá con nosotros», frases como «envianos tu CV», «buscamos personal» o «búsqueda laboral», y mails de selección (`rrhh@`, `empleos@`, `cv@`, `seleccion@`…). Cada lugar recibe un puntaje y la frase encontrada. Si aparece un mail de RRHH, se usa ese para escribirles.
- **Avisos recientes:** arma las búsquedas de los últimos 1, 3 o 7 días en LinkedIn, Computrabajo, Indeed y Google Empleos, y las guarda en **Portales de empleo** para abrirlas con un clic. Los portales no se leen solos: lo prohíben y bloquean a quien lo intenta.
- **Resultados:** van a una tanda normal, ordenados por puntaje, con el badge 🔥 *Busca personal* y un link a la página de empleo. No se duplican. Un lugar que ya tenías sin contactar y nunca fue revisado se revisa en ese momento y, si muestra señales, vuelve a la tanda.
- **Variable nueva:** en las plantillas podés usar `{busqueda_activa}`. Escribe «Vi que están buscando gente, así que les escribo.» solo cuando el lugar muestra señales.
- **Lugares sin web:** no se pueden revisar. Si destildás «Solo los que muestran señales», entran igual.

### ⚡ Cola rápida de WhatsApp
Está en **Revisión y envío** (toma los tildados con canal WhatsApp) y en la pestaña **WhatsApp** (toma los pendientes).

| Tecla | Qué hace |
|---|---|
| <kbd>Enter</kbd> | Abre el chat con el mensaje escrito, lo marca como contactado y deja listo el siguiente |
| <kbd>→</kbd> | Salta al siguiente |
| <kbd>Ctrl</kbd>+<kbd>Z</kbd> | Deshace el último (si abriste el chat pero no lo mandaste) |
| <kbd>Esc</kbd> | Cierra la cola |

- **No envía nada solo:** el **Enviar** de WhatsApp lo tocás vos. Así tu número no corre riesgo de bloqueo.
- **Espera mínima:** hay 4 segundos entre un chat y el siguiente.
- **Aviso diario:** a partir de 20 chats en el día te sugiere seguir mañana.

### 🎨 Personalización
- **12 temas:** Miami Vice City Neón, Cyberpunk, Matrix, Synthwave, Blanco Minimalista, Azul Ejecutivo, Rojo Carmesí, Esmeralda Nocturno, Dorado & Negro, Pastel Suave, Lavanda & Menta y Alto Contraste.
- **Mis colores:** podés elegir el fondo, las tarjetas, los tres acentos y el color del texto, más el brillo neón, la opacidad de las tarjetas y la fuerza de los bordes. La vista previa es en vivo.
- **Restaurar tema por defecto:** vuelve al tema Vice City.
- **Qué cambia:** toda la app, incluidos los botones, los badges y el pin y el radio del mapa. Con un tema claro, el mapa pasa a «Claro» solo.
- **Dónde se guarda:** en el navegador (`localStorage`) y también en `config/config.toml`, en `[apariencia]`, así se mantiene aunque abras la app en otra ventana o navegador.
- **Técnico:** todos los colores salen de variables CSS globales (`--bg-primary`, `--bg-card`, `--accent-primary`, `--accent-secondary`, `--accent-tertiary`, `--text-primary`, `--border-color`, `--accent-glow`…) definidas al principio de `app/ui/index.html`.

## 4. Fuentes de búsqueda

| Fuente | Costo | Qué trae |
|---|---|---|
| **Google Places** | Cuota gratuita mensual; después es pago (revisá precios y poné un límite en Google Cloud) | La mejor cobertura: dirección, teléfono y web. «Lo que sea» usa *Nearby Search* dentro del radio. |
| **OpenStreetMap** | Gratis | Le faltan locales chicos y casi nunca trae el mail. |
| **Demo** | Gratis | Lugares inventados para practicar. |

El mapa usa Leaflet con mapas de OpenStreetMap/CARTO. El buscador de direcciones usa Photon y Nominatim, que son gratuitos: usalos con moderación.
«Usar mi ubicación» funciona en la PC. Desde el celu por Wi-Fi local el navegador no lo permite (exige HTTPS): ahí usá el buscador o tocá el mapa.

## 5. Duplicados y «ya contactado»

- Un lugar repetido se reconoce por el id de la fuente o por nombre + dirección. Un mail, teléfono o web en común solo cuenta si además el nombre se parece y la altura de la calle coincide, así las sucursales de una cadena no se pisan.
- **Contactado** = mail enviado, WhatsApp marcado como enviado, o marcado a mano. Un borrador o un .eml queda como «Borrador sin enviar» hasta que toques **📤 Lo envié** en el Historial.
- Los lugares que nunca contactaste **vuelven a aparecer** en búsquedas nuevas. Los contactados y los que descartaste no.

## 6. Tus datos y GitHub

El `.gitignore` ya deja afuera todo lo personal:

| No se sube | Qué es |
|---|---|
| `.env` | Contraseña de Gmail y clave de Google |
| `datos/` | Base de datos, respaldos, CSV, log |
| `cvs/` | Tus CVs |
| `config/config.toml` | Tus datos personales. Se sube `config.ejemplo.toml`, y la app crea `config.toml` sola la primera vez |
| `config/.respaldo/`, `salidas/` | Copias de seguridad y archivos generados |

**Respaldos automáticos:**
- Antes de actualizar la estructura de la base, la app copia `datos/postulaciones.db` como `datos/postulaciones_respaldo_FECHA.db`.
- Antes de guardar configuración o plantillas, guarda la versión anterior en `config/.respaldo/`.
- Los CVs que borrás van a `cvs/.borrados/`.

## 6 bis. Versión web (multiusuario)
- **Arranque:** `wsgi.py` es el punto de entrada (`gunicorn wsgi:application`). Usa el mismo código que la versión de escritorio, con login.
- **Variables de entorno:** `SECRET_KEY` (obligatoria en el hosting), `DATABASE_URL` (PostgreSQL; sin ella, SQLite en `datos/web/`) y `CODIGO_INVITACION` (opcional, recomendada). El puerto lo toma de `PORT`.
- **Datos por usuario:** cada persona tiene su propio esquema de PostgreSQL. Ahí se guardan su configuración, sus plantillas, sus CVs (el PDF completo, no en disco), su historial y sus credenciales cifradas.
- **Diferencias con la versión de escritorio:** no hay modo .eml ni botones de carpeta, y los CSV se descargan generados al momento.
- **Archivos de despliegue:** `Procfile`, `render.yaml`, `requirements.txt` y `.python-version`.

## 7. Estructura

```
postuladorsito/
├── iniciar_silencioso.vbs   abrir_app.bat   abrir_app_celular.bat   abrir_app.command
├── app_postulador.py        ← arranca la app de escritorio
├── wsgi.py                  ← versión web (gunicorn) · Procfile · render.yaml · requirements.txt
├── postulador.py            ← versión de consola
├── config/  config.ejemplo.toml · config.toml (tuyo) · perfiles.toml
├── plantillas/  *_mail.txt · *_whatsapp.txt
├── cvs/  datos/  salidas/   ← tuyos, no van a GitHub
└── app/
    ├── servidor_ui.py       ← servidor local
    ├── ui/index.html        ← la interfaz
    ├── fuentes.py           ← Google Places / OpenStreetMap / demo
    ├── intenciones.py       ← «atención al cliente» → búsquedas concretas
    ├── buscan.py            ← modo «Buscan gente»: categorías y detector de señales de empleo
    ├── portales.py          ← links de LinkedIn, Computrabajo, Indeed, Google
    ├── ajustes.py           ← guardar config, claves, plantillas y CVs
    ├── almacen.py           ← dónde se guarda todo: archivos (PC) o base de datos (web)
    ├── basedatos.py         ← SQLite o PostgreSQL (DATABASE_URL), un esquema por usuario
    ├── seguridad.py         ← contraseñas, sesiones firmadas y cifrado de credenciales
    ├── contexto.py          ← qué usuario atiende cada pedido
    └── db.py, mensajes.py, correo.py, whatsapp.py, util.py, config.py
```

## 8. Consola (opcional)

```bash
python postulador.py buscar --perfil comercial --rubro "atención al cliente" --zona "Temperley" --limite 5
python postulador.py buscar --perfil comercial --todo --zona "Temperley" --lat -34.776 --lon -58.393 --radio 2500
python postulador.py buscar --perfil tecnico --rubro "soporte IT" --zona "Lomas de Zamora" --cv cvs/CV_IT.pdf
python postulador.py buscan --perfil comercial --categorias atencion,gastro --zona "Temperley" --limite 8
python postulador.py revisar · enviar · whatsapp · marcar · estado · exportar
```

Para sumar una intención de búsqueda nueva (por ejemplo «enfermería»), agregá un bloque en `app/intenciones.py`.
