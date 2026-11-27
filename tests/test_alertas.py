from visor_video.alertas import ConfiguracionAlertas, MotorAlertas
from visor_video.resultados import Deteccion

def d(cuadro, pez, x1, y1, x2, y2, canal="1", timestamp_ms=None, contado=False):
    return Deteccion(
        cuadro=cuadro,
        id_pez=pez,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        canal=canal,
        timestamp_ms=timestamp_ms,
        contado=contado,
    )


def test_detecta_peces_muy_juntos():
    datos = [
        d(10, "A", 100, 100, 160, 140),
        d(10, "B", 115, 100, 175, 140),
    ]
    alertas = MotorAlertas().analizar(datos)
    assert any(a.tipo == "PECES_JUNTOS" and a.cuadro == 10 for a in alertas)


def _pez(id_pez, cuadros, canal="1", x=100):
    return [d(c, id_pez, x, 100 + 10 * (c - 20), x + 60, 140 + 10 * (c - 20), canal)
            for c in cuadros]


def test_track_recien_nacido_no_es_perdida():
    # Aparece 1 cuadro, desaparece 2 y vuelve: está entrando, no se perdió.
    datos = [d(296, "18", 100, 10, 160, 50), d(300, "18", 100, 20, 160, 60)]
    alertas = MotorAlertas().analizar(datos)
    assert not any(a.tipo == "PERDIDA_SEGUIMIENTO" for a in alertas)


def test_mismo_id_en_dos_tubos_no_se_mezcla():
    # ID 18 en tubo 1 y en tubo 2: cada track se evalúa por separado.
    datos = [d(c, "18", 100, 10, 160, 50, canal="1") for c in (10, 11, 12)]
    datos += [d(296, "18", 100, 10, 160, 50, canal="2"),
              d(300, "18", 100, 20, 160, 60, canal="2")]
    alertas = MotorAlertas().analizar(datos)
    assert not any(a.tipo == "PERDIDA_SEGUIMIENTO" for a in alertas)


def test_no_emite_alerta_duplicado_en_mismo_cuadro():
    datos = [
        d(30, "A", 100, 100, 160, 140),
        d(30, "A", 102, 101, 162, 141),
    ]
    alertas = MotorAlertas().analizar(datos)
    assert not any(a.tipo == "POSIBLE_DUPLICADO" for a in alertas)


def test_no_emite_alerta_por_conteos_cercanos():
    datos = [
        d(40, "A", 100, 100, 160, 140, timestamp_ms=1000, contado=True),
        d(42, "A", 100, 110, 160, 150, timestamp_ms=1070, contado=True),
    ]
    alertas = MotorAlertas().analizar(datos)
    assert not any(a.tipo == "POSIBLE_DUPLICADO" for a in alertas)


def test_no_repite_pareja_junta_en_cuadros_consecutivos():
    datos = [
        d(50, "A", 100, 100, 160, 140),
        d(50, "B", 115, 100, 175, 140),
        d(51, "A", 102, 100, 162, 140),
        d(51, "B", 117, 100, 177, 140),
    ]
    alertas = [a for a in MotorAlertas().analizar(datos) if a.tipo == "PECES_JUNTOS"]
    assert len(alertas) == 1


def test_json_acepta_tiempo_y_evento_de_conteo(tmp_path):
    import json
    from visor_video.resultados import cargar_json

    ruta = tmp_path / "tracker.json"
    ruta.write_text(json.dumps({"detecciones": [
        {"frame": 10, "track_id": "A", "x1": 10, "y1": 10, "x2": 50, "y2": 40, "canal": "1", "timestamp_ms": 1000, "contado": True},
        {"frame": 12, "track_id": "A", "x1": 20, "y1": 10, "x2": 60, "y2": 40, "canal": "1", "timestamp_ms": 1070, "contado": True},
    ]}), encoding="utf-8")
    r = cargar_json(ruta)
    assert r.detecciones[0].timestamp_ms == 1000
    assert r.detecciones[0].contado is True
    assert not any(a.tipo == "POSIBLE_DUPLICADO" for a in MotorAlertas().analizar(r.detecciones))


def test_ir_a_frame_actualiza_el_reproductor(monkeypatch):
    from visor_video import visor_video as app

    monkeypatch.setattr(app, "video", object())
    monkeypatch.setattr(app, "total_cuadros", 100)
    monkeypatch.setattr(app, "cuadro_actual", 0)
    monkeypatch.setattr(app, "mostrar_cuadro", lambda: None)

    app.ir_a_frame(42)
    assert app.cuadro_actual == 42

def test_id_reutilizado_bajo_la_linea_da_dos_alertas():
    config = ConfiguracionAlertas(lineas_conteo_y_px={"1": 150.0})
    datos = _pez("13", range(20, 26))                       # pez anterior, sale bajo la línea
    datos += [d(c, "13", 100, 260 + 4 * (c - 60), 160, 300 + 4 * (c - 60))
              for c in range(60, 64)]                        # pez nuevo, mismo ID, bajo la línea
    alertas = MotorAlertas(config).analizar(datos)
    tipos_60 = {a.tipo for a in alertas if a.cuadro == 60}
    assert {"ID_REUTILIZADO", "INICIO_BAJO_LINEA"} <= tipos_60


def test_id_reutilizado_por_hueco_largo_sin_linea():
    datos = _pez("5", range(20, 24)) + _pez("5", range(80, 84))
    alertas = MotorAlertas().analizar(datos)
    reuso = [a for a in alertas if a.tipo == "ID_REUTILIZADO"]
    assert len(reuso) == 1 and reuso[0].cuadro == 80


def test_hueco_corto_del_mismo_pez_no_es_reuso():
    datos = _pez("A", (20, 21, 22, 26))
    assert not any(a.tipo == "ID_REUTILIZADO" for a in MotorAlertas().analizar(datos))