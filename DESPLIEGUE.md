# Postuladorsito online: guía rápida (GitHub + Render + Neon)

Resultado: un link `https://postuladorsito-xxxx.onrender.com` donde cada amigo crea su cuenta y usa la app sin instalar nada.
Cada cuenta tiene sus propios datos, CVs, plantillas, historial y credenciales (cifradas).

**Costo: $0.** Render (app) + Neon (base de datos PostgreSQL que no expira).

---

## 1. Base de datos en Neon (5 min)
1. Entrá a **neon.com** → *Sign up* (podés usar tu cuenta de GitHub).
2. *Create project* → nombre `postuladorsito` → región **AWS São Paulo** (o la más cercana) → *Create*.
3. En *Connect*, copiá la **connection string**. Empieza con `postgresql://` y termina con `sslmode=require`. Sirve la común o la *pooled*.
   Guardala: es la `DATABASE_URL`.

## 2. Subir el código a GitHub (5 min)
1. En **github.com** → *New repository* → nombre `postuladorsito` → elegí **Private** → *Create*.
2. La forma más fácil es arrastrar los archivos: en el repo nuevo, *uploading an existing file*, arrastrá **el contenido** de la carpeta `postuladorsito` y tocá *Commit changes*.
   Con Git instalado, también podés hacerlo desde la consola:
   ```bash
   cd postuladorsito
   git init && git add . && git commit -m "Postuladorsito web"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/postuladorsito.git
   git push -u origin main
   ```
3. Revisá en GitHub que **no** aparezcan `.env`, `datos/`, tus PDFs de `cvs/` ni `config/config.toml`. El `.gitignore` ya los excluye.

## 3. Publicar en Render (5 min)
1. Entrá a **render.com** → *Sign up with GitHub*.
2. *New* → **Blueprint** → elegí el repo `postuladorsito`. Render lee `render.yaml` solo.
3. Te pide dos valores:
   - `DATABASE_URL`: pegá la de Neon.
   - `CODIGO_INVITACION`: inventá uno (ej. `vicecity-2026`). Solo quien lo tenga puede crear cuenta.
   - `SECRET_KEY` se genera sola. **No la cambies después**: con ella se cifran las claves de todos.
4. *Apply* → esperá el *build* (2–4 min) → arriba aparece el link `https://postuladorsito-xxxx.onrender.com`.
5. Abrilo, tocá **Crear cuenta** y usá el código de invitación.

## 4. Pasárselo a tus amigos
Mandales el link y el código de invitación. Cada uno:
1. Crea su cuenta (usuario y contraseña propios, distintos de los de su Gmail).
2. En **Configuración y CVs**:
   - carga sus datos;
   - sube su CV;
   - pega su Gmail y una **contraseña de aplicación** (myaccount.google.com/apppasswords);
   - toca **Probar conexión Gmail**.
3. Busca con **OpenStreetMap**, que es gratis, o con su propia clave de Google Places.

## 5. Actualizar la app
Cada cambio que subas a GitHub (`git push` o subiendo archivos) hace que Render la vuelva a publicar sola. Los datos no se pierden porque están en Neon.

---

## Límites del plan gratuito (importante)
- **El servidor se duerme** tras 15 minutos sin visitas. La primera visita después tarda alrededor de un minuto en despertar.
- **Mantené la pestaña abierta mientras procesás una tanda.** Si la cerrás y nadie más usa la app, el servidor puede dormirse a mitad del proceso.
- **Mail:** los servicios gratuitos de Render bloquean el envío directo por SMTP (puertos 465/587).
  - Usá **«Borradores en Gmail»**: los mails quedan en tu carpeta Borradores, con el CV adjunto, y los mandás vos. Funciona por IMAP (puerto 993), que no está en la lista de bloqueados.
  - El envío automático necesita un plan pago de Render.
- **Railway:** también funciona con el `Procfile`, pero no tiene plan gratis permanente y bloquea SMTP en los planes Free, Trial y Hobby.
- **Neon gratis:** 1 GB por proyecto. Alcanza para muchísimos lugares y CVs.

## Seguridad y privacidad
- **Aislamiento:** cada usuario tiene su propio esquema en la base. Una consulta no puede mezclar datos de dos personas.
- **Contraseñas de las cuentas:** se guardan con hash scrypt. Las sesiones son cookies firmadas.
- **Credenciales de Gmail y Google:** se guardan cifradas con `SECRET_KEY`.
- **El administrador:** quien administra el hosting (vos) controla esa clave. Por eso cada amigo tiene que usar una **contraseña de aplicación** de Gmail, que se revoca cuando quiera, y **nunca** su contraseña real.
- **Borrar la cuenta:** cualquiera puede borrar su cuenta y todos sus datos desde *Configuración → Mi cuenta*.
- **Repositorio:** mantenelo **privado** y no compartas el código de invitación públicamente.

## Probar la versión web en tu PC
```bash
python wsgi.py          # http://127.0.0.1:8000  (usa SQLite en datos/web/, sin instalar nada)
```
La versión de escritorio de siempre sigue funcionando igual: `iniciar_silencioso.vbs` o `python app_postulador.py`.
