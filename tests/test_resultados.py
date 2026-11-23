import json

import pytest

from visor_video.resultados import ErrorResultados, cargar_json, etiqueta_canal


def guardar(tmp_path, nombre, datos):
    ruta = tmp_path / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


BASE = [
    {"frame": 0, "track_id": 1, "x1": 10, "y1": 10, "x2": 50, "y2": 40, "canal": "1"},
    {"frame": 0, "track_id": 2, "x1": 10, "y1": 100, "x2": 50, "y2": 140, "canal": "2"},
    {"frame": 1, "track_id": 1, "x1": 10, "y1": 20, "x2": 50, "y2": 50, "canal": "1"},
    {"frame": 1, "track_id": 3, "x1": 10, "y1": 200, "x2": 50, "y2": 240, "canal": "10"},
]


def test_agrupa_por_canal_y_cuadro(tmp_path):
    r = cargar_json(guardar(tmp_path, "datos.json", {"detecciones": BASE}))
    assert r.canales == ["1", "2", "10"]
    assert [d.id_pez for d in r.en_cuadro(0, "2")] == ["2"]
    assert r.en_cuadro(1, "2") == []
    assert len(r.en_cuadro(0)) == 2
    assert r.ultimo_cuadro == 1
    assert r.peces_por_canal() == {"1": 1, "2": 1, "10": 1}


def test_alias_xywh(tmp_path):
    ruta = guardar(tmp_path, "tubo2.json", [{"cuadro": 5, "id": 7, "x": 10, "y": 20, "w": 30, "h": 40, "tubo": "2"}])
    d = cargar_json(ruta).en_cuadro(5, "2")[0]
    assert (d.x1, d.y1, d.x2, d.y2) == (10, 20, 40, 60)


def test_campos_faltantes(tmp_path):
    ruta = guardar(tmp_path, "sin_canal.json", [{"frame": 0, "track_id": "1", "x1": 1, "y1": 1, "x2": 2, "y2": 2}])
    with pytest.raises(ErrorResultados, match="canal"):
        cargar_json(ruta)


def test_valor_invalido_indica_deteccion(tmp_path):
    filas = [BASE[0], {**BASE[0], "frame": "abc"}]
    ruta = guardar(tmp_path, "incorrecto.json", {"detecciones": filas})
    with pytest.raises(ErrorResultados, match="Detección 2"):
        cargar_json(ruta)


def test_archivo_sin_detecciones_o_inexistente(tmp_path):
    with pytest.raises(ErrorResultados):
        cargar_json(guardar(tmp_path, "vacio.json", {"detecciones": []}))
    with pytest.raises(ErrorResultados):
        cargar_json(tmp_path / "no_existe.json")


def test_etiquetas():
    assert etiqueta_canal("2") == "Tubo 2"
    assert etiqueta_canal("Norte") == "Norte"
