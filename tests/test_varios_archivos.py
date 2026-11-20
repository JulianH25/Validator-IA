import pytest

from visor_video.resultados import (
    ErrorResultados, canal_desde_nombre, cargar_csv, cargar_varios,
)

CON_CANAL = (
    "frame,track_id,x1,y1,x2,y2,canal\n"
    "0,1,10,10,50,40,1\n"
    "0,2,10,100,50,140,2\n"
)
SIN_CANAL = "frame,track_id,x1,y1,x2,y2\n0,7,10,10,50,40\n1,7,10,20,50,50\n"


def archivo(tmp_path, nombre, texto):
    ruta = tmp_path / nombre
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def test_un_archivo_con_los_dos_tubos(tmp_path):
    r = cargar_varios([archivo(tmp_path, "tracking.csv", CON_CANAL)])
    assert r.canales == ["1", "2"]


def test_un_archivo_por_tubo_con_canal_en_el_nombre(tmp_path):
    a = archivo(tmp_path, "tracking_tubo1.csv", SIN_CANAL)
    b = archivo(tmp_path, "tracking_tubo2.csv", SIN_CANAL)
    r = cargar_varios([a, b])
    assert r.canales == ["1", "2"]
    assert len(r.en_cuadro(0, "1")) == 1 and len(r.en_cuadro(0, "2")) == 1
    assert r.peces_por_canal() == {"1": 1, "2": 1}  # mismo id 7, canales distintos


def test_nombre_sin_tubo_pregunta_al_usuario(tmp_path):
    a = archivo(tmp_path, "salida.csv", SIN_CANAL)
    r = cargar_varios([a], resolver_canal=lambda ruta: "2")
    assert r.canales == ["2"]


def test_nombre_sin_tubo_y_sin_respuesta_da_error_claro(tmp_path):
    a = archivo(tmp_path, "salida.csv", SIN_CANAL)
    with pytest.raises(ErrorResultados, match="tubo"):
        cargar_varios([a], resolver_canal=lambda ruta: None)


def test_mismo_canal_en_dos_archivos_se_rechaza(tmp_path):
    a = archivo(tmp_path, "a_tubo1.csv", SIN_CANAL)
    b = archivo(tmp_path, "b_tubo1.csv", SIN_CANAL)
    with pytest.raises(ErrorResultados, match="canal 1"):
        cargar_varios([a, b])


def test_error_en_un_archivo_indica_cual(tmp_path):
    a = archivo(tmp_path, "bueno_tubo1.csv", SIN_CANAL)
    b = archivo(tmp_path, "malo_tubo2.csv", "frame,track_id,x1,y1,x2,y2\nabc,1,1,1,2,2\n")
    with pytest.raises(ErrorResultados, match="malo_tubo2.csv"):
        cargar_varios([a, b])


def test_mezcla_archivo_con_canal_y_archivo_sin_canal(tmp_path):
    a = archivo(tmp_path, "t1.csv", "frame,track_id,x1,y1,x2,y2,canal\n0,1,1,1,2,2,1\n")
    b = archivo(tmp_path, "tubo_2.csv", SIN_CANAL)
    assert cargar_varios([a, b]).canales == ["1", "2"]


def test_canal_desde_nombre():
    assert canal_desde_nombre("/x/tracking_tubo1.csv") == "1"
    assert canal_desde_nombre("canal-2.csv") == "2"
    assert canal_desde_nombre("salida_T2.CSV") == "2"
    assert canal_desde_nombre("ch1.csv") == "1"
    assert canal_desde_nombre("report1.csv") is None   # 't1' dentro de una palabra
    assert canal_desde_nombre("salida.csv") is None