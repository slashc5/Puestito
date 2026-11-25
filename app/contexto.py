"""Contexto por hilo: qué usuario está atendiendo cada pedido y a dónde va lo que se imprime.

- En la versión local (una sola persona) no hay usuario: todo usa los archivos de la carpeta.
- En la versión web, cada pedido HTTP y cada tarea en segundo plano corre «como» un usuario,
  y Config()/DB()/almacén usan solo los datos de esa persona.
"""
import contextlib
import io
import sys
import threading

_local = threading.local()


def usuario_actual():
    return getattr(_local, "usuario", None)


@contextlib.contextmanager
def como(usuario):
    anterior = usuario_actual()
    _local.usuario = usuario
    try:
        yield usuario
    finally:
        _local.usuario = anterior


# ---------------------------------------------------------------- salida por hilo
class _Despachador(io.TextIOBase):
    """Reemplaza a sys.stdout: lo que imprime un hilo con «captura» va a su propio buffer.

    Así dos usuarios buscando a la vez no mezclan sus mensajes (redirect_stdout es global y no sirve).
    """
    def __init__(self, original):
        self.original = original

    def write(self, s):
        destino = getattr(_local, "captura", None)
        if destino is not None:
            destino(s)
        elif self.original:
            try:
                self.original.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
        try:
            if self.original:
                self.original.flush()
        except Exception:
            pass


def instalar_despachador():
    if not isinstance(sys.stdout, _Despachador):
        sys.stdout = _Despachador(sys.stdout)


@contextlib.contextmanager
def capturar(funcion_escribir):
    """Todo lo que se imprima en este hilo dentro del bloque se manda a funcion_escribir(texto)."""
    instalar_despachador()
    anterior = getattr(_local, "captura", None)
    _local.captura = funcion_escribir
    try:
        yield
    finally:
        _local.captura = anterior
