from pathlib import Path

import pytest

from visor_video.correcciones import EventoConteo, RegistroCorrecciones
from visor_video.persistencia import (
    ErrorPersistencia,
    cargar_proyecto,
    describir_operacion,
    guardar_proyecto,
    registro_a_dict,
    registro_desde_dict,
)


def registro_editado():
    r = RegistroCorrecciones(
        [
            EventoConteo(1, "1", 10, "A"),
            EventoConteo(2, "1", 20, "B"),
            EventoConteo(3, "2", 30, "C"),
        ],
        total_cuadros=200,
    )
    r.agregar("2", 40)
    r.mover(1, "2", 50)
    r.eliminar(2)
    r.deshacer()
    return r


def test_registro_roundtrip_conserva_estado_historial_y_deshacer():
    original = registro_editado()
    restaurado = registro_desde_dict(registro_a_dict(original))

    assert restaurado.eventos() == original.eventos()
    assert restaurado.conteos() == original.conteos()
    assert restaurado.historial == original.historial
    assert restaurado.puede_deshacer == original.puede_deshacer
    assert restaurado.hay_cambios == original.hay_cambios

    restaurado.deshacer()
    original.deshacer()
    assert restaurado.eventos() == original.eventos()


def test_guardar_no_modifica_csv_original(tmp_path):
    csv = tmp_path / "tracker.csv"
    csv.write_text("frame,track_id,x1,y1,x2,y2,canal\n0,A,1,2,3,4,1\n", encoding="utf-8")
    antes = csv.read_bytes()
    proyecto = tmp_path / "sesion.validator.json"

    guardar_proyecto(proyecto, registro_editado(), csvs=[csv])

    assert proyecto.exists()
    assert csv.read_bytes() == antes


def test_guardar_y_reabrir_restaura_conteos_rutas_y_vista(tmp_path):
    video = tmp_path / "video.mp4"
    csv1 = tmp_path / "tracker_tubo1.csv"
    csv2 = tmp_path / "tracker_tubo2.csv"
    for archivo in (video, csv1, csv2):
        archivo.write_bytes(b"prueba")

    r = registro_editado()
    proyecto = tmp_path / "sesion.validator.json"
    guardar_proyecto(
        proyecto,
        r,
        video=video,
        csvs=[csv1, csv2],
        canales_csv={str(csv1): "1", str(csv2): "2"},
        cuadro=57,
        filtro="Tubo 2",
        lineas_conteo={"1": 280, "2": 300},
    )

    cargado = cargar_proyecto(proyecto)
    assert Path(cargado.video) == video.resolve()
    assert tuple(Path(ruta) for ruta in cargado.csvs) == (csv1.resolve(), csv2.resolve())
    assert cargado.canales_csv[str(csv1.resolve())] == "1"
    assert cargado.cuadro == 57
    assert cargado.filtro == "Tubo 2"
    assert cargado.lineas_conteo == {"1": 280.0, "2": 300.0}
    assert cargado.registro.conteos() == r.conteos()
    assert cargado.registro.historial == r.historial


def test_historial_simple_indica_accion_y_frame():
    r = RegistroCorrecciones([EventoConteo(1, "1", 10, "A")], total_cuadros=100)
    r.mover(1, "2", 20)
    texto = describir_operacion(r.historial[-1])
    assert "Mover" in texto
    assert "T1 frame 11" in texto
    assert "T2 frame 21" in texto


def test_archivo_invalido_da_error(tmp_path):
    ruta = tmp_path / "malo.json"
    ruta.write_text('{"tipo":"otro","version":1}', encoding="utf-8")
    with pytest.raises(ErrorPersistencia):
        cargar_proyecto(ruta)


def test_se_puede_seguir_editando_despues_de_reabrir():
    original = registro_editado()
    restaurado = registro_desde_dict(registro_a_dict(original))
    ids_antes = {e.id for e in restaurado.eventos()}
    nuevo = restaurado.agregar("1", 70)
    assert nuevo.id not in ids_antes
    assert restaurado.historial[-1].tipo == "AGREGAR"
