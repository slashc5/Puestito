"""Punto de entrada de la versión web de Postuladorsito.

En el hosting (Render, Railway…):   gunicorn wsgi:application --workers 1 --threads 8 --timeout 120
En tu PC, para probar la versión web: python wsgi.py   → http://127.0.0.1:8000

Variables de entorno:
  SECRET_KEY         obligatoria en el hosting (firma las sesiones y cifra las credenciales de cada usuario)
  DATABASE_URL       PostgreSQL (por ejemplo, Neon). Sin ella usa SQLite en datos/web/ (solo para probar)
  CODIGO_INVITACION  opcional pero recomendada: solo se registra quien conozca este código
  PORT               la pone el hosting
"""
import os

from app.servidor_ui import crear_app, servidor_wsgi

application = crear_app(web=True)

if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    print(f"Postuladorsito (versión web) en http://{host}:{puerto}  ·  base: "
          f"{'PostgreSQL' if os.environ.get('DATABASE_URL') else 'SQLite en datos/web/'}")
    servidor_wsgi(host, puerto, application).serve_forever()
