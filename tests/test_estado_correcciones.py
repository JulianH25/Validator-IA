from visor_video.correcciones import (
    ESTADO_AGREGADO, ESTADO_ELIMINADO, ESTADO_MOVIDO, ESTADO_NORMAL,
    EventoConteo, RegistroCorrecciones,
)


def registro():
    return RegistroCorrecciones(
        [EventoConteo(1, "1", 10, "A"), EventoConteo(2, "1", 50, "B"), EventoConteo(3, "2", 30, "C")],
        total_cuadros=200,
    )


def estados(r, canal=None):
    return [(e.id, est) for e, est, _ in r.filas(canal)]


def test_sin_cambios_todo_normal():
    assert estados(registro()) == [(1, ESTADO_NORMAL), (2, ESTADO_NORMAL), (3, ESTADO_NORMAL)]


def test_agregar_aparece_como_agregado():
    r = registro()
    nuevo = r.agregar("2", 80)
    assert (nuevo.id, ESTADO_AGREGADO) in estados(r)
    assert r.estado(nuevo.id) == ESTADO_AGREGADO


def test_eliminar_sigue_en_la_lista_como_eliminado_pero_no_cuenta():
    r = registro()
    r.eliminar(2)
    assert (2, ESTADO_ELIMINADO) in estados(r)
    assert 2 not in [e.id for e in r.eventos()]
    assert r.conteos() == {"1": 1, "2": 1} and r.total == 2


def test_eliminado_conserva_su_posicion_original_en_el_orden():
    r = registro()
    r.eliminar(2)
    assert [i for i, _ in estados(r, "1")] == [1, 2]


def test_deshacer_eliminar_vuelve_a_normal():
    r = registro()
    r.eliminar(2)
    r.deshacer()
    assert r.estado(2) == ESTADO_NORMAL
    assert estados(r) == [(1, ESTADO_NORMAL), (2, ESTADO_NORMAL), (3, ESTADO_NORMAL)]


def test_deshacer_agregar_lo_quita_de_la_lista():
    r = registro()
    nuevo = r.agregar("1", 99)
    r.deshacer()
    assert r.estado(nuevo.id) is None
    assert nuevo.id not in [e.id for e, _, _ in r.filas()]


def test_mover_aparece_como_movido_con_posicion_anterior():
    r = registro()
    r.mover(1, canal="2", cuadro=120)
    (e, est, previo), = [f for f in r.filas() if f[0].id == 1]
    assert est == ESTADO_MOVIDO
    assert (e.canal, e.cuadro) == ("2", 120)
    assert (previo.canal, previo.cuadro) == ("1", 10)


def test_mover_y_volver_al_lugar_original_es_normal():
    r = registro()
    r.mover(1, cuadro=11)
    r.mover(1, cuadro=10)
    assert r.estado(1) == ESTADO_NORMAL


def test_agregar_y_luego_eliminar_no_deja_rastro_en_la_lista():
    r = registro()
    nuevo = r.agregar("1", 20)
    r.eliminar(nuevo.id)
    assert r.estado(nuevo.id) is None
    assert len(r.filas()) == 3


def test_filtro_por_canal_incluye_eliminados_de_ese_canal():
    r = registro()
    r.eliminar(3)
    assert estados(r, "2") == [(3, ESTADO_ELIMINADO)]
    assert [i for i, _ in estados(r, "1")] == [1, 2]