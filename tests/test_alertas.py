from visor_video.alertas import MotorAlertas
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


def test_detecta_perdida_y_reaparicion():
    datos = [
        d(20, "A", 100, 100, 160, 140),
        d(24, "A", 100, 120, 160, 160),
    ]
    alertas = MotorAlertas().analizar(datos)
    assert any(a.tipo == "PERDIDA_SEGUIMIENTO" and a.cuadro == 21 for a in alertas)


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
