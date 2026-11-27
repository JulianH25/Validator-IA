import json
from pathlib import Path

import pytest

from visor_video.resultados import ErrorResultados, cargar_json, cargar_varios
from visor_video.canales import cargar_canales
from visor_video.correcciones import EventoConteo, RegistroCorrecciones
from visor_video.persistencia import cargar_proyecto, exportar_conteo_json, guardar_proyecto
from visor_video import visor_video as visor


def guardar(tmp_path, nombre, datos):
    ruta = tmp_path / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


def deteccion(frame, ident, canal=None):
    d = {"frame": frame, "track_id": ident, "x1": 10, "y1": 20, "x2": 50, "y2": 60}
    if canal is not None:
        d["canal"] = canal
    return d


def test_configuracion_unificada_carga_detecciones_y_canales(tmp_path):
    ruta = guardar(tmp_path, "configuracion.json", {
        "detecciones": [deteccion(0, "101", "1"), deteccion(1, "201", "2")],
        "canales": {
            "1": {"x1": 0, "y1": 0, "x2": 100, "y2": 200, "linea_y": 120},
            "2": {"x1": 200, "y1": 0, "x2": 300, "y2": 200, "linea_y": 120},
        },
    })
    r = cargar_varios([ruta])
    assert r.canales == ["1", "2"]
    assert r.en_cuadro(0, "1")[0].id_pez == "101"
    assert set(cargar_canales(ruta)) == {"1", "2"}


def test_json_en_lista_con_xywh_y_sin_canal_resuelve_por_nombre(tmp_path):
    ruta = guardar(tmp_path, "tracker_tubo2.json", [
        {"cuadro": 5, "id": 7, "x": 10, "y": 20, "w": 30, "h": 40}
    ])
    r = cargar_varios([ruta])
    d = r.en_cuadro(5, "2")[0]
    assert (d.x1, d.y1, d.x2, d.y2) == (10, 20, 40, 60)


def test_json_sin_canal_resuelto_mediante_dialogo(tmp_path):
    ruta = guardar(tmp_path, "salida.json", {"detecciones": [deteccion(10, "A")]})
    r = cargar_varios([ruta], resolver_canal=lambda r: "1")
    assert r.canales == ["1"]


def test_dos_archivos_json_rechaza_tubo_repetido(tmp_path):
    a = guardar(tmp_path, "a_tubo1.json", [deteccion(1, "A")])
    b = guardar(tmp_path, "b_tubo1.json", [deteccion(1, "B")])
    with pytest.raises(ErrorResultados, match="canal 1"):
        cargar_varios([a, b])


@pytest.mark.parametrize("contenido", [
    "{json roto",
    json.dumps({"canales": {"1": {}}}),
    json.dumps({"detecciones": []}),
    json.dumps({"detecciones": ["valor incorrecto"]}),
    json.dumps({"detecciones": [deteccion("abc", "A", "1")]}),
])
def test_json_invalido_muestra_error(tmp_path, contenido):
    ruta = tmp_path / "salida.json"
    ruta.write_text(contenido, encoding="utf-8")
    with pytest.raises(ErrorResultados):
        cargar_json(ruta)


def test_json_lee_tiempo_y_eventos_contados(tmp_path):
    fila = deteccion(10, "A", "1")
    fila.update({"timestamp_ms": 1200, "contado": True})
    ruta = guardar(tmp_path, "datos.json", {"detecciones": [fila]})
    resultado = cargar_json(ruta)
    assert resultado.detecciones[0].timestamp_ms == 1200
    assert resultado.detecciones[0].contado is True


def test_exportar_conteo_json_sin_modificar_archivos(tmp_path):
    fuente = guardar(tmp_path, "tracker.json", {"detecciones": [deteccion(0, "A", "1")]})
    antes = fuente.read_bytes()
    registro = RegistroCorrecciones([EventoConteo(1, "1", 10, "A")], total_cuadros=100)
    registro.agregar("2", 30, "B")
    salida = tmp_path / "conteo_final.json"
    exportar_conteo_json(salida, registro, fps=30)
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["total"] == 2
    assert datos["conteos"] == {"1": 1, "2": 1}
    assert datos["eventos"][0]["tiempo_s"] == 0.333
    assert fuente.read_bytes() == antes


def test_proyecto_v2_guarda_json_y_recupera_registro(tmp_path):
    fuente = guardar(tmp_path, "tracker.json", {"detecciones": [deteccion(0, "A", "1")]})
    registro = RegistroCorrecciones([EventoConteo(1, "1", 0, "A")])
    registro.agregar("2", 1, "B")
    destino = tmp_path / "proyecto.validator.json"
    guardar_proyecto(destino, registro, archivos_json=[fuente], canales_json={str(fuente): "1"})
    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert datos["version"] == 2
    assert "archivos_json" in datos
    assert "csvs" not in datos
    proyecto = cargar_proyecto(destino)
    assert proyecto.archivos_json == (str(fuente.resolve()),)
    assert proyecto.canales_json[str(fuente.resolve())] == "1"
    assert proyecto.registro.conteos() == registro.conteos()


def test_proyecto_antiguo_no_se_acepta(tmp_path):
    registro = RegistroCorrecciones([EventoConteo(1, "1", 0, "A")])
    fuente = guardar(tmp_path, "datos.json", {"detecciones": [deteccion(0, "A", "1")]})
    proyecto = tmp_path / "viejo.validator.json"
    guardar_proyecto(proyecto, registro, archivos_json=[fuente])
    datos = json.loads(proyecto.read_text(encoding="utf-8"))
    datos["version"] = 1
    proyecto.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(Exception, match="versión"):
        cargar_proyecto(proyecto)


def test_solo_json_rechaza_archivos_de_otro_formato(tmp_path):
    fuente = tmp_path / "tracker.csv"
    fuente.write_text("frame,track_id,x1,y1,x2,y2,canal\n0,A,1,2,3,4,1\n", encoding="utf-8")
    with pytest.raises(ErrorResultados, match="JSON"):
        cargar_json(fuente)
    with pytest.raises(ErrorResultados, match="JSON"):
        cargar_varios([fuente])
    registro = RegistroCorrecciones([EventoConteo(1, "1", 0, "A")])
    with pytest.raises(Exception, match="JSON"):
        guardar_proyecto(tmp_path / "sesion.validator.json", registro, archivos_json=[fuente])


def test_proyecto_rechaza_referencias_antiguas(tmp_path):
    registro = RegistroCorrecciones([EventoConteo(1, "1", 0, "A")])
    fuente = guardar(tmp_path, "datos.json", {"detecciones": [deteccion(0, "A", "1")]})
    destino = tmp_path / "antiguo.validator.json"
    guardar_proyecto(destino, registro, archivos_json=[fuente])
    datos = json.loads(destino.read_text(encoding="utf-8"))
    datos["archivos_json"] = [str(tmp_path / "datos.csv")]
    destino.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(Exception, match="JSON"):
        cargar_proyecto(destino)


def test_boton_cargar_configuracion_unificada(monkeypatch, tmp_path):
    ruta = guardar(tmp_path, "configuracion.json", {
        "detecciones": [deteccion(0, "A", "1")],
        "canales": {"1": {"x1": 0, "y1": 0, "x2": 80, "y2": 150}},
    })
    llamadas = []
    monkeypatch.setattr(visor.filedialog, "askopenfilenames", lambda **kw: (str(ruta),))
    monkeypatch.setattr(visor, "_cargar_resultados_desde_rutas", lambda rutas: llamadas.append("datos") or True)
    monkeypatch.setattr(visor, "_cargar_canales_desde_ruta", lambda ruta: llamadas.append("canales") or True)
    visor.cargar_resultados()
    assert llamadas == ["datos", "canales"]


def test_boton_cargar_configuracion_solo_canales(monkeypatch, tmp_path):
    ruta = guardar(tmp_path, "canales.json", {"canales": {"1": {"x1": 0, "y1": 0, "x2": 80, "y2": 150}}})
    llamadas = []
    monkeypatch.setattr(visor.filedialog, "askopenfilenames", lambda **kw: (str(ruta),))
    monkeypatch.setattr(visor, "_cargar_resultados_desde_rutas", lambda rutas: llamadas.append("datos") or True)
    monkeypatch.setattr(visor, "_cargar_canales_desde_ruta", lambda ruta: llamadas.append("canales") or True)
    visor.cargar_resultados()
    assert llamadas == ["canales"]


def test_interfaz_ofrece_configuracion_json():
    codigo = (Path(__file__).parents[1] / "src/visor_video/visor_video.py").read_text(encoding="utf-8")
    assert '"Cargar configuración"' in codigo
    assert '"Exportar configuración"' in codigo
    assert 'initialfile="conteo_final.json"' in codigo
