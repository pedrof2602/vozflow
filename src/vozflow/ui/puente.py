"""Lleva lo que pasa en los hilos del dictado al hilo de la interfaz.

``Aplicacion`` avisa desde sus propios hilos; Qt solo deja tocar las ventanas desde el principal.
Emitir una señal desde otro hilo la entrega, en cola, en el hilo del receptor.
"""

from PySide6.QtCore import QObject, Signal


class Puente(QObject):
    estado = Signal(object)
    """Un ``EstadoDelDictado``."""
    aviso = Signal(str)
    abrir_pagina = Signal(str)
    """Pide mostrar una página de los ajustes (por ejemplo, si las teclas no se pudieron tomar)."""
