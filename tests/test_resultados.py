
import os
import tempfile

import numpy as np
import pytest

from visor_video.resultados import (
    ErrorResultados, cargar_csv, dibujar_cajas, etiqueta_canal,
)


def escribir(texto):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    f.write(texto)
    f.close()
    return f.name


BASE = (
    "frame,track_id,x1,y1,x2,y2,canal\n"
    "0,1,10,10,50,40,1\n"
    "0,2,10,100,50,140,2\n"
    "1,1,20,10,60,40,1\n"
    "1,3,10,200,50,240,10\n"
)


def test_agrupa_por_canal_y_cuadro():
    r = cargar_csv(escribir(BASE))
    assert r.canales == ["1", "2", "10"]          # orden natural
    assert [d.id_pez for d in r.en_cuadro(0, "2")] == ["2"]
    assert r.en_cuadro(1, "2") == []              # tubo sin peces en ese cuadro
    assert len(r.en_cuadro(0)) == 2               # todos los tubos
    assert r.ultimo_cuadro == 1
    assert r.peces_por_canal() == {"1": 1, "2": 1, "10": 1}


def test_separador_punto_y_coma_y_alias_xywh():
    r = cargar_csv(escribir("cuadro;id;x;y;w;h;tubo\n5;7;10;20;30;40;2\n"))
    d = r.en_cuadro(5, "2")[0]
    assert (d.x1, d.y1, d.x2, d.y2) == (10, 20, 40, 60)


def test_columnas_faltantes():
    with pytest.raises(ErrorResultados, match="canal"):
        cargar_csv(escribir("frame,track_id,x1,y1,x2,y2\n0,1,1,1,2,2\n"))


def test_valor_invalido_indica_linea():
    with pytest.raises(ErrorResultados, match="Línea 3"):
        cargar_csv(escribir(
            "frame,track_id,x1,y1,x2,y2,canal\n0,1,1,1,2,2,1\nabc,1,1,1,2,2,1\n"))


def test_archivo_sin_filas_o_inexistente():
    with pytest.raises(ErrorResultados):
        cargar_csv(escribir("frame,track_id,x1,y1,x2,y2,canal\n"))
    with pytest.raises(ErrorResultados):
        cargar_csv("/no/existe.csv")


def test_etiquetas():
    assert etiqueta_canal("2") == "Tubo 2"
    assert etiqueta_canal("Norte") == "Norte"


def test_dibujar_solo_las_cajas_dadas_y_no_modifica_original():
    r = cargar_csv(escribir(BASE))
    cuadro = np.zeros((300, 400, 3), dtype=np.uint8)
    salida = dibujar_cajas(cuadro, r.en_cuadro(0, "2"))
    assert cuadro.sum() == 0                       # original intacto
    assert salida[100:141, 10:51].sum() > 0        # caja del tubo 2 dibujada
    assert salida[10:41, 10:51].sum() == 0         # caja del tubo 1 ausente