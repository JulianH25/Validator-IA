import ast
from pathlib import Path
from types import SimpleNamespace

from visor_video.panel_correcciones import PanelCorrecciones
from visor_video.correcciones import EventoConteo, RegistroCorrecciones
from visor_video.resultados import Deteccion
import visor_video.visor_video as visor


SRC = Path(__file__).parents[1] / "src" / "visor_video" / "visor_video.py"


def test_no_hay_funciones_duplicadas_de_carga():
    arbol = ast.parse(SRC.read_text(encoding="utf-8"))
    nombres = [n.name for n in arbol.body if isinstance(n, ast.FunctionDef)]
    assert nombres.count("_preguntar_tubo") == 1
    assert nombres.count("cargar_resultados") == 1


def test_agregar_sin_resultados_no_accede_al_registro():
    panel = object.__new__(PanelCorrecciones)
    panel._hay_registro = lambda: False
    PanelCorrecciones.agregar(panel)


def test_mover_sin_resultados_no_accede_al_registro():
    panel = object.__new__(PanelCorrecciones)
    panel._hay_registro = lambda: False
    PanelCorrecciones.mover(panel)


def test_dialogo_conserva_objeto_de_ventana_padre():
    fuente = (Path(__file__).parents[1] / "src" / "visor_video" / "panel_correcciones.py").read_text(encoding="utf-8")
    assert "self._padre_ventana = padre.winfo_toplevel()" in fuente
    assert "raiz = self.transient()" not in fuente

def test_eliminar_correccion_actualiza_conteo():
    eventos = [
        EventoConteo(1, "1", 10, "A"),
        EventoConteo(2, "1", 11, "A"),
        EventoConteo(3, "1", 50, "B"),
        EventoConteo(4, "1", 80, "F"),
        EventoConteo(5, "2", 36, "C"),
        EventoConteo(6, "2", 60, "D"),
    ]

    registro = RegistroCorrecciones(eventos, canales=("1", "2"))

    assert registro.conteos() == {"1": 4, "2": 2}
    assert registro.total == 6

    registro.eliminar(2)

    assert registro.conteos() == {"1": 3, "2": 2}
    assert registro.total == 5


def test_deshacer_restaura_conteo():
    eventos = [
        EventoConteo(1, "1", 10, "A"),
        EventoConteo(2, "1", 11, "A"),
        EventoConteo(3, "1", 50, "B"),
        EventoConteo(4, "1", 80, "F"),
        EventoConteo(5, "2", 36, "C"),
        EventoConteo(6, "2", 60, "D"),
    ]

    registro = RegistroCorrecciones(eventos, canales=("1", "2"))

    registro.eliminar(2)

    assert registro.conteos() == {"1": 3, "2": 2}

    registro.deshacer()

    assert registro.conteos() == {"1": 4, "2": 2}
    assert registro.total == 6


def test_mover_actualiza_conteos():
    eventos = [
        EventoConteo(1, "1", 10, "A"),
        EventoConteo(2, "1", 11, "A"),
        EventoConteo(3, "1", 50, "B"),
        EventoConteo(4, "1", 80, "F"),
        EventoConteo(5, "2", 36, "C"),
        EventoConteo(6, "2", 60, "D"),
    ]

    registro = RegistroCorrecciones(eventos, canales=("1", "2"))

    registro.mover(3, canal="2", cuadro=90)

    assert registro.conteos() == {"1": 3, "2": 3}
    assert registro.total == 6


def test_agregar_actualiza_conteos():
    eventos = [
        EventoConteo(1, "1", 10, "A"),
        EventoConteo(2, "1", 11, "A"),
        EventoConteo(3, "1", 50, "B"),
        EventoConteo(4, "1", 80, "F"),
        EventoConteo(5, "2", 36, "C"),
        EventoConteo(6, "2", 60, "D"),
    ]

    registro = RegistroCorrecciones(eventos, canales=("1", "2"))

    registro.agregar("1", 100, "NUEVO")

    assert registro.conteos() == {"1": 5, "2": 2}
    assert registro.total == 7


def test_detecciones_corregidas_reflejan_eliminacion():
    eventos = [
        EventoConteo(1, "1", 10, "A"),
        EventoConteo(2, "1", 11, "A"),
    ]

    registro = RegistroCorrecciones(eventos, canales=("1", "2"))

    registro.eliminar(2)

    visor.resultados = SimpleNamespace(
        detecciones=[
            Deteccion(10, "A", 10, 10, 20, 20, "1", contado=True),
            Deteccion(11, "A", 11, 10, 20, 20, "1", contado=True),
        ]
    )

    visor.panel_correcciones = SimpleNamespace(registro=registro)

    detecciones = visor._detecciones_con_correcciones()

    assert len(detecciones) == 2
    assert detecciones[0].contado is True
    assert detecciones[1].contado is False


def test_deshacer_restaurar_deteccion_contada():
    eventos = [
        EventoConteo(1, "1", 10, "A"),
        EventoConteo(2, "1", 11, "A"),
    ]

    registro = RegistroCorrecciones(eventos, canales=("1", "2"))

    registro.eliminar(2)
    registro.deshacer()

    visor.resultados = SimpleNamespace(
        detecciones=[
            Deteccion(10, "A", 10, 10, 20, 20, "1", contado=True),
            Deteccion(11, "A", 10, 10, 20, 20, "1", contado=True),
        ]
    )

    visor.panel_correcciones = SimpleNamespace(registro=registro)

    detecciones = visor._detecciones_con_correcciones()

    assert all(d.contado for d in detecciones)


def test_actualizar_alertas_usa_detecciones_corregidas(monkeypatch):
    llamadas = []

    class MotorFalso:
        def analizar(self, detecciones):
            llamadas.append(list(detecciones))
            return []

    visor.motor_alertas = MotorFalso()

    visor.resultados = SimpleNamespace(
        detecciones=[
            Deteccion(10, "A", 10, 10, 20, 20, "1", contado=True),
            Deteccion(11, "A", 10, 10, 20, 20, "1", contado=True),
        ]
    )

    registro = RegistroCorrecciones(
        [
            EventoConteo(1, "1", 10, "A"),
            EventoConteo(2, "1", 11, "A"),
        ],
        canales=("1", "2"),
    )

    registro.eliminar(2)

    visor.panel_correcciones = SimpleNamespace(registro=registro)
    visor.texto_alertas = None
    visor.alerta_seleccionada = None

    monkeypatch.setattr(visor, "_construir_tarjetas", lambda: None)
    monkeypatch.setattr(visor, "_dibujar_timeline", lambda: None)

    visor.actualizar_alertas()

    assert len(llamadas) == 1

    detecciones = llamadas[0]

    assert detecciones[0].contado is True
    assert detecciones[1].contado is False