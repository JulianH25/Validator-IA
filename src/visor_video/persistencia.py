"""Guardado y recuperación de proyectos del Validator."""

from __future__ import annotations
import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from .correcciones import EventoConteo, Operacion, RegistroCorrecciones

VERSION_PROYECTO = 1
TIPO_PROYECTO = "validator-ia"


class ErrorPersistencia(Exception):
    pass


@dataclass
class ProyectoCargado:
    video: str | None
    csvs: tuple[str, ...]
    canales_csv: dict[str, str]
    cuadro: int
    filtro: str
    lineas_conteo: dict[str, float]
    registro: RegistroCorrecciones
    canales_archivo: str | None = None


def _evento_a_dict(evento: EventoConteo | None):
    if evento is None:
        return None
    return {
        "id": evento.id,
        "canal": evento.canal,
        "cuadro": evento.cuadro,
        "id_pez": evento.id_pez,
        "origen": evento.origen,
    }


def _evento_desde_dict(datos):
    if datos is None:
        return None
    try:
        return EventoConteo(
            id=int(datos["id"]),
            canal=str(datos["canal"]),
            cuadro=int(datos["cuadro"]),
            id_pez=None if datos.get("id_pez") is None else str(datos["id_pez"]),
            origen=str(datos.get("origen", "tracker")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorPersistencia("Hay un evento de conteo inválido en el proyecto.") from exc


def _operacion_a_dict(op: Operacion):
    return {
        "numero": op.numero,
        "tipo": op.tipo,
        "evento_id": op.evento_id,
        "antes": _evento_a_dict(op.antes),
        "despues": _evento_a_dict(op.despues),
        "momento": op.momento,
        "revierte": op.revierte,
    }


def _operacion_desde_dict(datos):
    try:
        return Operacion(
            numero=int(datos["numero"]),
            tipo=str(datos["tipo"]),
            evento_id=int(datos["evento_id"]),
            antes=_evento_desde_dict(datos.get("antes")),
            despues=_evento_desde_dict(datos.get("despues")),
            momento=str(datos["momento"]),
            revierte=None if datos.get("revierte") is None else int(datos["revierte"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorPersistencia("Hay una operación inválida en el historial.") from exc


def registro_a_dict(registro: RegistroCorrecciones):
    pila = [registro.historial[i].numero for i in registro._pila]
    return {
        "canales": list(registro.canales),
        "total_cuadros": registro.total_cuadros,
        "original": [_evento_a_dict(e) for e in registro.original],
        "actuales": [_evento_a_dict(e) for e in registro.eventos()],
        "historial": [_operacion_a_dict(op) for op in registro.historial],
        "pila_deshacer": pila,
        "siguiente_id": registro._siguiente_id,
    }


def registro_desde_dict(datos):
    try:
        canales = tuple(str(c) for c in datos["canales"])
        total = datos.get("total_cuadros")
        total = None if total is None else int(total)
        original = [_evento_desde_dict(e) for e in datos["original"]]
        actuales = [_evento_desde_dict(e) for e in datos["actuales"]]
        operaciones = [_operacion_desde_dict(op) for op in datos.get("historial", [])]
        pila_numeros = [int(n) for n in datos.get("pila_deshacer", [])]
        siguiente_id = int(datos["siguiente_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorPersistencia("El estado de correcciones del proyecto no es válido.") from exc

    registro = RegistroCorrecciones(original, canales=canales, total_cuadros=total)
    actuales_por_id = {e.id: e for e in actuales}
    if len(actuales_por_id) != len(actuales):
        raise ErrorPersistencia("El proyecto tiene ids de conteo repetidos.")

    por_numero = {op.numero: i for i, op in enumerate(operaciones)}
    if len(por_numero) != len(operaciones) or any(n not in por_numero for n in pila_numeros):
        raise ErrorPersistencia("El historial de deshacer del proyecto no es válido.")

    registro._actuales = actuales_por_id
    registro._operaciones = operaciones
    registro._pila = [por_numero[n] for n in pila_numeros]
    registro._siguiente_id = max(siguiente_id, max(actuales_por_id, default=0) + 1)
    return registro


def guardar_proyecto(
    ruta,
    registro,
    *,
    video=None,
    csvs=(),
    canales_csv=None,
    cuadro=0,
    filtro="Todos (T1 + T2)",
    lineas_conteo=None,
    canales_archivo=None
):
    if registro is None:
        raise ErrorPersistencia("No hay resultados ni correcciones para guardar.")

    destino = Path(ruta)
    datos = {
        "tipo": TIPO_PROYECTO,
        "version": VERSION_PROYECTO,
        "guardado_en": datetime.now().isoformat(timespec="seconds"),
        "video": str(Path(video).resolve()) if video else None,
        "csvs": [str(Path(r).resolve()) for r in csvs],
        "canales_csv": {str(Path(k).resolve()): str(v) for k, v in (canales_csv or {}).items()},
        "cuadro": int(cuadro),
        "filtro": str(filtro),
        "lineas_conteo": {str(k): float(v) for k, v in (lineas_conteo or {}).items()},
        "correcciones": registro_a_dict(registro),
        "canales_archivo": str(Path(canales_archivo).resolve()) if canales_archivo else None,
    }

    temporal = destino.with_suffix(destino.suffix + ".tmp")
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(destino)
    except OSError as exc:
        try:
            temporal.unlink(missing_ok=True)
        except OSError:
            pass
        raise ErrorPersistencia(f"No se pudo guardar el proyecto: {exc}") from exc
    return destino


def cargar_proyecto(ruta):
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorPersistencia(f"No se pudo abrir el proyecto: {exc}") from exc

    if datos.get("tipo") != TIPO_PROYECTO:
        raise ErrorPersistencia("El archivo no corresponde a un proyecto Validator-IA.")
    if datos.get("version") != VERSION_PROYECTO:
        raise ErrorPersistencia("La versión del proyecto no es compatible.")

    try:
        return ProyectoCargado(
            video=datos.get("video"),
            csvs=tuple(str(r) for r in datos.get("csvs", [])),
            canales_csv={str(k): str(v) for k, v in datos.get("canales_csv", {}).items()},
            cuadro=max(0, int(datos.get("cuadro", 0))),
            filtro=str(datos.get("filtro", "Todos (T1 + T2)")),
            lineas_conteo={str(k): float(v) for k, v in datos.get("lineas_conteo", {}).items()},
            registro=registro_desde_dict(datos["correcciones"]),
            canales_archivo=datos.get("canales_archivo"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorPersistencia("El archivo de proyecto está incompleto.") from exc


def describir_operacion(op: Operacion):
    hora = op.momento.split("T", 1)[-1]
    if op.tipo == "MOVER" and op.antes and op.despues:
        return (
            f"{hora}  Mover  T{op.antes.canal} frame {op.antes.cuadro + 1}"
            f" → T{op.despues.canal} frame {op.despues.cuadro + 1}"
        )
    evento = op.despues or op.antes
    ubicacion = f"T{evento.canal} frame {evento.cuadro + 1}" if evento else ""
    if op.tipo == "DESHACER":
        return f"{hora}  Deshacer operación #{op.revierte}  {ubicacion}".strip()
    nombres = {"AGREGAR": "Agregar", "ELIMINAR": "Eliminar"}
    return f"{hora}  {nombres.get(op.tipo, op.tipo.title())}  {ubicacion}".strip()

def exportar_conteo_csv(ruta, registro, fps=None):
    """Escribe el conteo final (con correcciones) en un CSV, un evento por fila.

    `frame` usa base 0, igual que el CSV del Tracker. `tiempo_s` se calcula solo si se da `fps`.
    """
    if registro is None:
        raise ErrorPersistencia("No hay conteos para exportar.")
    destino = Path(ruta)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(["canal", "frame", "tiempo_s", "id_pez", "origen"])
            for e in registro.eventos():
                tiempo = f"{e.cuadro / fps:.3f}" if fps else ""
                escritor.writerow([e.canal, e.cuadro, tiempo, e.id_pez or "", e.origen])
    except OSError as exc:
        raise ErrorPersistencia(f"No se pudo exportar el conteo: {exc}") from exc
    return destino