"""Prueba del panel real con una pantalla virtual (xvfb)."""
import tkinter as tk
import pytest
from unittest import mock

from visor_video import panel_correcciones as pc
from visor_video.correcciones import EventoConteo


@pytest.fixture
def panel():
    try:
        raiz = tk.Tk()
    except tk.TclError:
        pytest.skip("sin pantalla")
    estado = {"canal": None, "cuadro": 5}
    p = pc.PanelCorrecciones(
        raiz, obtener_canal=lambda: estado["canal"], obtener_cuadro=lambda: estado["cuadro"],
        obtener_total=lambda: 200, ir_a_frame=lambda c: estado.setdefault("salto", c),
    )
    p.pack()
    p.cargar([EventoConteo(1, "1", 10, "A"), EventoConteo(2, "1", 50, "B"), EventoConteo(3, "2", 30, "C")])
    p._estado_test = estado
    yield p
    raiz.destroy()


def color(p, fila):
    return p._lista.itemcget(fila, "foreground")


def test_eliminar_muestra_la_fila_en_rojo_y_sigue_en_la_lista(panel):
    panel._lista.selection_set(1)
    panel.eliminar()
    assert panel._lista.size() == 3
    assert "✕" in panel._lista.get(1)
    assert color(panel, 1) == pc.RED
    assert color(panel, 0) in ("", None) or color(panel, 0) != pc.RED


def test_agregar_muestra_la_fila_en_verde(panel):
    panel._estado_test["canal"] = "2"
    panel.agregar()
    assert panel._lista.size() == 2  # filtro tubo 2: el original + el nuevo
    textos = [panel._lista.get(i) for i in range(panel._lista.size())]
    fila = next(i for i, t in enumerate(textos) if t.startswith("+"))
    assert color(panel, fila) == pc.GREEN


def test_mover_muestra_amarillo_con_origen_y_destino(panel):
    panel._lista.selection_set(0)
    with mock.patch.object(pc, "_DialogoEvento") as d:
        d.return_value.resultado = ("2", 99)
        panel.mover()
    textos = [panel._lista.get(i) for i in range(panel._lista.size())]
    fila = next(i for i, t in enumerate(textos) if t.startswith("↔"))
    assert color(panel, fila) == pc.AMBER
    assert "T1 00011" in textos[fila] and "T2 00100" in textos[fila]


def test_deshacer_quita_el_color(panel):
    panel._lista.selection_set(1)
    panel.eliminar()
    panel.deshacer()
    assert "✕" not in panel._lista.get(1)
    assert color(panel, 1) != pc.RED


def test_no_se_puede_eliminar_ni_mover_un_conteo_ya_eliminado(panel):
    panel._lista.selection_set(1)
    panel.eliminar()
    with mock.patch.object(pc.messagebox, "showinfo") as info:
        panel.eliminar()
        panel.mover()
    assert info.call_count == 2
    assert panel.registro.total == 2  # no se tocó nada más


def test_doble_clic_en_eliminado_salta_a_su_cuadro(panel):
    panel._lista.selection_set(1)
    panel.eliminar()
    panel._lista.selection_clear(0, "end")
    panel._lista.selection_set(1)
    panel._saltar()
    assert panel._estado_test["salto"] == 50


def test_contador_no_cuenta_los_eliminados(panel):
    panel._lista.selection_set(0)
    panel.eliminar()
    assert "T1:1" in panel._conteos.cget("text") and "Total:2" in panel._conteos.cget("text")