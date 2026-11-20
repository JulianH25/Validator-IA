import ast
from pathlib import Path

from visor_video.panel_correcciones import PanelCorrecciones


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
