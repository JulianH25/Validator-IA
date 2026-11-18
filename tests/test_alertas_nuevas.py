import json

import pytest

from visor_video.alertas import ConfiguracionAlertas, MotorAlertas, cargar_lineas_conteo
from visor_video.resultados import Deteccion
from visor_video.visor_video import _titulo_alerta


def det(cuadro, pez, y=100, canal="1"):
    return Deteccion(
        cuadro=cuadro, id_pez=pez, x1=100, y1=y,
        x2=145, y2=y + 30, canal=canal,
    )


def test_identifica_pez_de_un_solo_cuadro():
    datos = [det(i, "A", 100 + 4 * i) for i in range(6)] + [det(3, "B", 190)]
    alertas = MotorAlertas().analizar(datos)
    unicas = [a for a in alertas if a.tipo == "APARICION_UN_CUADRO"]
    assert len(unicas) == 1
    assert unicas[0].cuadro == 3
    assert unicas[0].ids_pez == ("B",)


def test_detecciones_repetidas_en_mismo_frame_siguen_siendo_una_aparicion():
    datos = [det(0, "A"), det(1, "A"), det(1, "B"), det(1, "B")]
    alertas = MotorAlertas().analizar(datos)
    assert len([a for a in alertas if a.tipo == "APARICION_UN_CUADRO"]) == 1


def test_sin_linea_no_emite_alertas_por_posicion():
    datos = [det(1, "A", 300), det(2, "A", 310)]
    alertas = MotorAlertas().analizar(datos)
    assert not any(a.tipo == "INICIO_BAJO_LINEA" for a in alertas)


def test_primera_aparicion_debajo_de_linea_configurada():
    config = ConfiguracionAlertas(lineas_conteo_y_px={"1": 250.0})
    datos = [det(i, "A", 100 + 4 * i) for i in range(6)]
    datos += [det(i, "B", 275 + 4 * (i - 3)) for i in range(3, 6)]
    alertas = MotorAlertas(config).analizar(datos)
    bajo = [a for a in alertas if a.tipo == "INICIO_BAJO_LINEA"]
    assert len(bajo) == 1
    assert (bajo[0].cuadro, bajo[0].ids_pez, bajo[0].canal) == (3, ("B",), "1")
    assert bajo[0].detalles["linea_y_px"] == 250


def test_primera_aparicion_arriba_o_exactamente_en_linea_no_alarma():
    config = ConfiguracionAlertas(lineas_conteo_y_px={"1": 200})
    datos = [det(3, "A", 150), det(4, "A", 190)]
    datos += [det(4, "B", 185), det(5, "B", 190)]
    alertas = MotorAlertas(config).analizar(datos)
    assert not any(a.tipo == "INICIO_BAJO_LINEA" for a in alertas)


def test_lineas_se_aplican_a_cada_tubo_independientemente():
    config = ConfiguracionAlertas(lineas_conteo_y_px={"2": 230})
    datos = [det(3, "A", 280, "1"), det(4, "A", 280, "1")]
    datos += [det(3, "B", 280, "2"), det(4, "B", 280, "2")]
    alertas = MotorAlertas(config).analizar(datos)
    bajo = [a for a in alertas if a.tipo == "INICIO_BAJO_LINEA"]
    assert len(bajo) == 1 and bajo[0].canal == "2"


def test_lee_configuracion_nula_y_numerica(tmp_path):
    ruta = tmp_path / "lineas_conteo.json"
    ruta.write_text(json.dumps({"lineas_conteo_y_px": {"1": None, "2": 250}}), encoding="utf-8")
    assert cargar_lineas_conteo(ruta) == {"2": 250.0}


def test_rechaza_configuracion_invalida(tmp_path):
    ruta = tmp_path / "lineas_conteo.json"
    ruta.write_text(json.dumps({"lineas_conteo_y_px": {"1": -20}}), encoding="utf-8")
    with pytest.raises(ValueError):
        cargar_lineas_conteo(ruta)


def test_titulos_nuevos_visibles_en_panel():
    class Alerta:
        def __init__(self, tipo):
            self.tipo = tipo

    assert _titulo_alerta(Alerta("APARICION_UN_CUADRO")) == "ID en un solo frame"
    assert _titulo_alerta(Alerta("INICIO_BAJO_LINEA")) == "Aparición bajo la línea"
