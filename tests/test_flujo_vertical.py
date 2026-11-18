from visor_video.alertas import ConfiguracionAlertas, MotorAlertas
from visor_video.resultados import Deteccion
from visor_video.visor_video import _titulo_alerta


def pez(frame, identificador, y, canal="1", x=160):
    return Deteccion(frame, identificador, x, y, x + 50, y + 36, canal)


def tipos(datos, config=None):
    return MotorAlertas(config).analizar(datos)


def test_descenso_normal_no_produce_alerta_contraria():
    datos = [pez(i, "101", 80 + 6 * i) for i in range(15)]
    assert not any(a.tipo == "MOVIMIENTO_CONTRARIO" for a in tipos(datos))


def test_pequeno_ruido_vertical_es_tolerado():
    datos = [pez(0, "101", 100), pez(1, "101", 92), pez(2, "101", 106)]
    assert not any(a.tipo == "MOVIMIENTO_CONTRARIO" for a in tipos(datos))


def test_retroceso_vertical_genera_alerta_en_cuadro_correcto():
    datos = [pez(0, "101", 130), pez(1, "101", 145), pez(2, "101", 116), pez(3, "101", 126)]
    alertas = [a for a in tipos(datos) if a.tipo == "MOVIMIENTO_CONTRARIO"]
    assert len(alertas) == 1
    assert (alertas[0].cuadro, alertas[0].canal, alertas[0].ids_pez) == (2, "1", ("101",))
    assert alertas[0].detalles["retroceso_y_px"] == 29
    assert _titulo_alerta(alertas[0]) == "Movimiento hacia arriba"


def test_ascensos_consecutivos_producen_una_sola_alerta():
    datos = [pez(0, "201", 170, "2"), pez(1, "201", 146, "2"), pez(2, "201", 122, "2")]
    assert len([a for a in tipos(datos) if a.tipo == "MOVIMIENTO_CONTRARIO"]) == 1


def test_linea_no_es_alarma_por_cruce_normal_hacia_abajo():
    config = ConfiguracionAlertas(lineas_conteo_y_px={"2": 240})
    datos = [pez(i, "201", 190 + i * 12, "2") for i in range(8)]
    assert not any(a.tipo == "INICIO_BAJO_LINEA" for a in tipos(datos, config))


def test_primer_avistamiento_bajo_linea_si_es_alerta():
    config = ConfiguracionAlertas(lineas_conteo_y_px={"2": 240})
    datos = [pez(i, "201", 130 + i * 4, "2") for i in range(12)]
    datos += [pez(i, "302", 280 + (i - 5) * 5, "2", x=690) for i in range(5, 11)]
    bajo = [a for a in tipos(datos, config) if a.tipo == "INICIO_BAJO_LINEA"]
    assert len(bajo) == 1
    assert (bajo[0].cuadro, bajo[0].canal, bajo[0].ids_pez) == (5, "2", ("302",))


def test_no_se_compara_movimiento_si_faltan_cuadros():
    datos = [pez(0, "101", 250), pez(4, "101", 100)]
    assert not any(a.tipo == "MOVIMIENTO_CONTRARIO" for a in tipos(datos))
