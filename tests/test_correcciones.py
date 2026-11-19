import pytest

from visor_video.correcciones import (
    AGREGAR, DESHACER, ELIMINAR, MOVER, ORIGEN_MANUAL,
    ErrorCorreccion, EventoConteo, RegistroCorrecciones, eventos_desde_resultados,
)
from visor_video.resultados import Deteccion, Resultados


def registro():
    eventos = [
        EventoConteo(1, "1", 10, "A"),
        EventoConteo(2, "1", 50, "B"),
        EventoConteo(3, "2", 30, "C"),
    ]
    return RegistroCorrecciones(eventos, total_cuadros=200)


def test_conteos_iniciales_y_canal_vacio_en_cero():
    r = RegistroCorrecciones([EventoConteo(1, "1", 5, "A")], total_cuadros=100)
    assert r.conteos() == {"1": 1, "2": 0}
    assert r.total == 1


def test_agregar_actualiza_lista_y_conteo():
    r = registro()
    nuevo = r.agregar("2", 80)
    assert nuevo.origen == ORIGEN_MANUAL and nuevo.id_pez is None
    assert r.conteo("2") == 2 and r.total == 4
    assert nuevo in r.eventos("2")


def test_eliminar_quita_de_la_lista():
    r = registro()
    r.eliminar(2)
    assert [e.id for e in r.eventos("1")] == [1]
    assert r.conteos() == {"1": 1, "2": 1}


def test_mover_cambia_canal_y_momento():
    r = registro()
    r.mover(1, canal="2", cuadro=120)
    e = r.evento(1)
    assert (e.canal, e.cuadro, e.id_pez) == ("2", 120, "A")
    assert r.conteos() == {"1": 1, "2": 2}


def test_deshacer_agregar_revierte_caja_falsa():
    r = registro()
    antes = r.eventos()
    r.agregar("1", 99)
    assert r.deshacer() is not None
    assert r.eventos() == antes and not r.hay_cambios


def test_deshacer_eliminar_restaura_el_mismo_evento():
    r = registro()
    original = r.evento(2)
    r.eliminar(2)
    r.deshacer()
    assert r.evento(2) == original


def test_deshacer_mover_restaura_posicion():
    r = registro()
    original = r.evento(3)
    r.mover(3, canal="1", cuadro=7)
    r.deshacer()
    assert r.evento(3) == original


def test_deshacer_varias_veces_en_orden_inverso():
    r = registro()
    r.agregar("1", 20)
    r.eliminar(1)
    r.mover(3, cuadro=31)
    r.deshacer()
    assert r.evento(3).cuadro == 30
    r.deshacer()
    assert r.evento(1).cuadro == 10
    r.deshacer()
    assert r.total == 3 and not r.hay_cambios
    assert r.deshacer() is None and not r.puede_deshacer


def test_ids_no_se_reutilizan_tras_deshacer():
    r = registro()
    a = r.agregar("1", 20)
    r.deshacer()
    b = r.agregar("1", 21)
    assert b.id != a.id


def test_historial_conserva_todo_incluido_deshacer():
    r = registro()
    r.agregar("1", 20)
    r.eliminar(1)
    r.deshacer()
    assert [o.tipo for o in r.historial] == [AGREGAR, ELIMINAR, DESHACER]
    assert r.historial[-1].revierte == 2
    assert len(r.original) == 3  # el original no cambia


def test_validaciones():
    r = registro()
    with pytest.raises(ErrorCorreccion):
        r.agregar("3", 10)
    with pytest.raises(ErrorCorreccion):
        r.agregar("1", -1)
    with pytest.raises(ErrorCorreccion):
        r.agregar("1", 200)          # el video tiene 200 cuadros (0..199)
    with pytest.raises(ErrorCorreccion):
        r.eliminar(999)
    with pytest.raises(ErrorCorreccion):
        r.mover(1, canal="1", cuadro=10)   # sin cambios
    assert not r.hay_cambios and not r.historial  # los errores no dejan rastro


def det(cuadro, pez, canal="1", contado=False):
    return Deteccion(cuadro, pez, 0, cuadro, 40, cuadro + 30, canal, contado=contado)


def test_eventos_desde_filas_contadas():
    res = Resultados([det(0, "A", contado=False), det(1, "A", contado=True),
                      det(1, "B", "2", contado=True)])
    ev = eventos_desde_resultados(res)
    assert [(e.canal, e.cuadro, e.id_pez) for e in ev] == [("1", 1, "A"), ("2", 1, "B")]


def test_eventos_sin_columna_contado_uno_por_pez_en_su_ultimo_cuadro():
    res = Resultados([det(0, "A"), det(5, "A"), det(2, "B", "2")])
    ev = eventos_desde_resultados(res)
    assert [(e.canal, e.cuadro, e.id_pez) for e in ev] == [("1", 5, "A"), ("2", 2, "B")]