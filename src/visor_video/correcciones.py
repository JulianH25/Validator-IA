"""Registro de correcciones manuales de conteo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

ORIGEN_TRACKER = "tracker"
ORIGEN_MANUAL = "manual"

AGREGAR = "AGREGAR"
ELIMINAR = "ELIMINAR"
MOVER = "MOVER"
DESHACER = "DESHACER"


class ErrorCorreccion(Exception):
    """Error con un mensaje pensado para mostrar al usuario."""


@dataclass(frozen=True)
class EventoConteo:
    id: int
    canal: str
    cuadro: int
    id_pez: str | None = None
    origen: str = ORIGEN_TRACKER


@dataclass(frozen=True)
class Operacion:
    numero: int
    tipo: str
    evento_id: int
    antes: EventoConteo | None
    despues: EventoConteo | None
    momento: str
    revierte: int | None = None


def _clave_canal(canal: str):
    return (0, int(canal), "") if canal.isdigit() else (1, 0, canal)


def _clave_evento(e: EventoConteo):
    return (_clave_canal(e.canal), e.cuadro, e.id)


class RegistroCorrecciones:
    def __init__(self, eventos=(), canales=("1", "2"), total_cuadros=None):
        self.canales = tuple(str(c) for c in canales)
        self.total_cuadros = total_cuadros
        self._original = tuple(sorted(eventos, key=_clave_evento))
        self._actuales = {e.id: e for e in self._original}
        if len(self._actuales) != len(self._original):
            raise ErrorCorreccion("Hay eventos de conteo con id repetido.")
        self._siguiente_id = max(self._actuales, default=0) + 1
        self._operaciones: list[Operacion] = []
        self._pila: list[int] = []

    @property
    def original(self):
        return self._original

    @property
    def historial(self):
        return tuple(self._operaciones)

    @property
    def puede_deshacer(self):
        return bool(self._pila)

    @property
    def hay_cambios(self):
        return tuple(sorted(self._actuales.values(), key=_clave_evento)) != self._original

    def evento(self, evento_id):
        try:
            return self._actuales[evento_id]
        except KeyError:
            raise ErrorCorreccion("Ese conteo ya no existe.")

    def eventos(self, canal=None):
        """Eventos actuales ordenados por canal y cuadro."""
        lista = [e for e in self._actuales.values() if canal is None or e.canal == canal]
        return sorted(lista, key=_clave_evento)

    def conteo(self, canal):
        return sum(1 for e in self._actuales.values() if e.canal == canal)

    def conteos(self):
        """{canal: cantidad}; un canal sin conteos muestra 0."""
        return {c: self.conteo(c) for c in self.canales}

    @property
    def total(self):
        return len(self._actuales)

    def _validar(self, canal, cuadro):
        canal = str(canal).strip()
        if canal not in self.canales:
            raise ErrorCorreccion(
                f"El canal «{canal}» no existe. Canales válidos: {', '.join(self.canales)}."
            )
        if isinstance(cuadro, bool) or not isinstance(cuadro, int):
            raise ErrorCorreccion("El cuadro debe ser un número entero.")
        if cuadro < 0:
            raise ErrorCorreccion("El cuadro debe ser 1 o mayor.")
        if self.total_cuadros is not None and cuadro >= self.total_cuadros:
            raise ErrorCorreccion(
                f"El cuadro {cuadro + 1} está fuera del video (1 a {self.total_cuadros})."
            )
        return canal, cuadro

    def _registrar(self, tipo, antes, despues, revierte=None):
        evento_id = (despues or antes).id
        if despues is None:
            self._actuales.pop(evento_id, None)
        else:
            self._actuales[evento_id] = despues
        op = Operacion(
            numero=len(self._operaciones) + 1,
            tipo=tipo,
            evento_id=evento_id,
            antes=antes,
            despues=despues,
            momento=datetime.now().isoformat(timespec="seconds"),
            revierte=revierte,
        )
        self._operaciones.append(op)
        return op

    def agregar(self, canal, cuadro, id_pez=None):
        canal, cuadro = self._validar(canal, cuadro)
        nuevo = EventoConteo(self._siguiente_id, canal, cuadro, id_pez, ORIGEN_MANUAL)
        self._siguiente_id += 1
        op = self._registrar(AGREGAR, None, nuevo)
        self._pila.append(op.numero - 1)
        return nuevo

    def eliminar(self, evento_id):
        antes = self.evento(evento_id)
        op = self._registrar(ELIMINAR, antes, None)
        self._pila.append(op.numero - 1)
        return antes

    def mover(self, evento_id, canal=None, cuadro=None):
        antes = self.evento(evento_id)
        canal_nuevo = antes.canal if canal is None else canal
        cuadro_nuevo = antes.cuadro if cuadro is None else cuadro
        canal_nuevo, cuadro_nuevo = self._validar(canal_nuevo, cuadro_nuevo)
        if (canal_nuevo, cuadro_nuevo) == (antes.canal, antes.cuadro):
            raise ErrorCorreccion("El conteo ya está en ese canal y cuadro.")
        despues = EventoConteo(antes.id, canal_nuevo, cuadro_nuevo, antes.id_pez, antes.origen)
        op = self._registrar(MOVER, antes, despues)
        self._pila.append(op.numero - 1)
        return despues

    def deshacer(self):
        """Revierte la última operación. Devuelve la operación DESHACER o None."""
        if not self._pila:
            return None
        original = self._operaciones[self._pila.pop()]
        return self._registrar(
            DESHACER, original.despues, original.antes, revierte=original.numero
        )


def eventos_desde_resultados(resultados):
    """Eventos de conteo iniciales a partir de lo que entrega el Tracker.

    - Si el CSV marca filas como contadas (columna `contado`), cada fila
      contada es un evento (así un conteo duplicado se puede eliminar).
    - Si el CSV no trae esa información, se cuenta un evento por pez, en
      el último cuadro en que aparece. Ajustar aquí cuando se acuerde el
      formato común con el Tracker.
    """
    contadas = [d for d in resultados.detecciones if d.contado]
    if not contadas:
        ultimas = {}
        for d in resultados.detecciones:
            clave = (d.canal, d.id_pez)
            if clave not in ultimas or d.cuadro > ultimas[clave].cuadro:
                ultimas[clave] = d
        contadas = list(ultimas.values())
    contadas.sort(key=lambda d: (_clave_canal(d.canal), d.cuadro, d.id_pez))
    return [
        EventoConteo(i, d.canal, d.cuadro, d.id_pez, ORIGEN_TRACKER)
        for i, d in enumerate(contadas, start=1)
    ]