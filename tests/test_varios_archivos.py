import json

import pytest

from visor_video.resultados import ErrorResultados, canal_desde_nombre, cargar_varios

CON_CANAL = [
    {"frame": 0, "track_id": 1, "x1": 10, "y1": 10, "x2": 50, "y2": 40, "canal": "1"},
    {"frame": 0, "track_id": 2, "x1": 10, "y1": 100, "x2": 50, "y2": 140, "canal": "2"},
]
SIN_CANAL = [
    {"frame": 0, "track_id": 7, "x1": 10, "y1": 10, "x2": 50, "y2": 40},
    {"frame": 1, "track_id": 7, "x1": 10, "y1": 20, "x2": 50, "y2": 50},
]


def archivo(tmp_path, nombre, datos):
    ruta = tmp_path / nombre
    ruta.write_text(json.dumps({"detecciones": datos}), encoding="utf-8")
    return ruta


def test_un_archivo_con_los_dos_tubos(tmp_path):
    r = cargar_varios([archivo(tmp_path, "tracking.json", CON_CANAL)])
    assert r.canales == ["1", "2"]


def test_un_archivo_por_tubo_con_canal_en_el_nombre(tmp_path):
    a = archivo(tmp_path, "tracking_tubo1.json", SIN_CANAL)
    b = archivo(tmp_path, "tracking_tubo2.json", SIN_CANAL)
    r = cargar_varios([a, b])
    assert r.canales == ["1", "2"]
    assert len(r.en_cuadro(0, "1")) == 1 and len(r.en_cuadro(0, "2")) == 1
    assert r.peces_por_canal() == {"1": 1, "2": 1}


def test_nombre_sin_tubo_pregunta_al_usuario(tmp_path):
    a = archivo(tmp_path, "salida.json", SIN_CANAL)
    r = cargar_varios([a], resolver_canal=lambda ruta: "2")
    assert r.canales == ["2"]


def test_nombre_sin_tubo_y_sin_respuesta_da_error_claro(tmp_path):
    a = archivo(tmp_path, "salida.json", SIN_CANAL)
    with pytest.raises(ErrorResultados, match="tubo"):
        cargar_varios([a], resolver_canal=lambda ruta: None)


def test_mismo_canal_en_dos_archivos_se_rechaza(tmp_path):
    a = archivo(tmp_path, "a_tubo1.json", SIN_CANAL)
    b = archivo(tmp_path, "b_tubo1.json", SIN_CANAL)
    with pytest.raises(ErrorResultados, match="canal 1"):
        cargar_varios([a, b])


def test_error_en_un_archivo_indica_cual(tmp_path):
    a = archivo(tmp_path, "bueno_tubo1.json", SIN_CANAL)
    b = archivo(tmp_path, "malo_tubo2.json", [{"frame": "abc", "track_id": 1, "x1": 1, "y1": 1, "x2": 2, "y2": 2}])
    with pytest.raises(ErrorResultados, match="malo_tubo2.json"):
        cargar_varios([a, b])


def test_mezcla_archivo_con_canal_y_archivo_sin_canal(tmp_path):
    a = archivo(tmp_path, "t1.json", [{"frame": 0, "track_id": 1, "x1": 1, "y1": 1, "x2": 2, "y2": 2, "canal": "1"}])
    b = archivo(tmp_path, "tubo_2.json", SIN_CANAL)
    assert cargar_varios([a, b]).canales == ["1", "2"]


def test_canal_desde_nombre():
    assert canal_desde_nombre("/x/tracking_tubo1.json") == "1"
    assert canal_desde_nombre("canal-2.json") == "2"
    assert canal_desde_nombre("salida_T2.JSON") == "2"
    assert canal_desde_nombre("ch1.json") == "1"
    assert canal_desde_nombre("report1.json") is None
    assert canal_desde_nombre("salida.json") is None
