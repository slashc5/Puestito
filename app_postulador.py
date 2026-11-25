#!/usr/bin/env python3
"""Abre Postuladorsito (interfaz visual).

    python app_postulador.py              -> ventana propia (si tenés pywebview) o navegador
    python app_postulador.py --navegador  -> forzar navegador
    python app_postulador.py --red        -> también accesible desde el celular en tu Wi-Fi
"""
import sys
from pathlib import Path

# Abierto con pythonw / iniciar_silencioso.vbs no hay consola: los mensajes van a un archivo de log.
if sys.stdout is None or sys.stderr is None:
    log = Path(__file__).resolve().parent / "datos" / "postuladorsito.log"
    log.parent.mkdir(exist_ok=True)
    sys.stdout = sys.stderr = open(log, "a", encoding="utf-8", buffering=1)

from app.servidor_ui import main

if __name__ == "__main__":
    main()
