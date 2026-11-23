"""Guardado y recuperación de proyectos del Validator."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from .correcciones import EventoConteo, Operacion, RegistroCorrecciones

VERSION_PROYECTO = 2
TIPO_PROYECTO = "validator-ia"


class ErrorPersistencia(Exception):
    pass


@dataclass
class ProyectoCargado:
    video: str | None
    archivos_json: tuple[str, ...]
    canales_json: dict[str, str]
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
    archivos_json=(),
    canales_json=None,
    cuadro=0,
    filtro="Todos (T1 + T2)",
    lineas_conteo=None,
    canales_archivo=None
):
    if registro is None:
        raise ErrorPersistencia("No hay resultados ni correcciones para guardar.")

    destino = Path(ruta)
    if destino.suffix.lower() != ".json":
        raise ErrorPersistencia("El proyecto debe guardarse como archivo JSON.")
    fuentes = tuple(archivos_json)
    asignaciones = canales_json or {}
    for fuente in fuentes:
        if Path(fuente).suffix.lower() != ".json":
            raise ErrorPersistencia("Los resultados del proyecto deben ser archivos JSON (.json).")
    if any(Path(r).suffix.lower() != ".json" for r in asignaciones):
        raise ErrorPersistencia("Las asignaciones de tubo deben corresponder a archivos JSON.")
    if canales_archivo and Path(canales_archivo).suffix.lower() != ".json":
        raise ErrorPersistencia("La configuración de canales debe ser un archivo JSON.")
    datos = {
        "tipo": TIPO_PROYECTO,
        "version": VERSION_PROYECTO,
        "guardado_en": datetime.now().isoformat(timespec="seconds"),
        "video": str(Path(video).resolve()) if video else None,
        "archivos_json": [str(Path(r).resolve()) for r in fuentes],
        "canales_json": {str(Path(k).resolve()): str(v) for k, v in (asignaciones or {}).items()},
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
    if Path(ruta).suffix.lower() != ".json":
        raise ErrorPersistencia("Solo se admiten proyectos JSON (.json).")
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorPersistencia(f"No se pudo abrir el proyecto: {exc}") from exc

    if not isinstance(datos, dict):
        raise ErrorPersistencia("El proyecto JSON no tiene una estructura válida.")
    if datos.get("tipo") != TIPO_PROYECTO:
        raise ErrorPersistencia("El archivo no corresponde a un proyecto Validator-IA.")
    if datos.get("version") != VERSION_PROYECTO:
        raise ErrorPersistencia("La versión del proyecto no es compatible.")

    try:
        fuentes = tuple(str(r) for r in datos["archivos_json"])
        asignaciones = {str(k): str(v) for k, v in datos["canales_json"].items()}
        if any(Path(r).suffix.lower() != ".json" for r in fuentes):
            raise ErrorPersistencia("El proyecto hace referencia a resultados que no son JSON.")
        if any(Path(r).suffix.lower() != ".json" for r in asignaciones):
            raise ErrorPersistencia("El proyecto contiene asignaciones a archivos que no son JSON.")
        ruta_canales = datos.get("canales_archivo")
        if ruta_canales and Path(ruta_canales).suffix.lower() != ".json":
            raise ErrorPersistencia("La configuración de canales del proyecto no es JSON.")
        return ProyectoCargado(
            video=datos.get("video"),
            archivos_json=fuentes,
            canales_json=asignaciones,
            cuadro=max(0, int(datos.get("cuadro", 0))),
            filtro=str(datos.get("filtro", "Todos (T1 + T2)")),
            lineas_conteo={str(k): float(v) for k, v in datos.get("lineas_conteo", {}).items()},
            registro=registro_desde_dict(datos["correcciones"]),
            canales_archivo=ruta_canales,
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

def exportar_conteo_json(ruta, registro, fps=None):
    """Exporta los eventos corregidos a JSON sin cambiar los archivos de origen."""
    if registro is None:
        raise ErrorPersistencia("No hay conteos para exportar.")
    destino = Path(ruta)
    if destino.suffix.lower() != ".json":
        raise ErrorPersistencia("La exportación de conteos debe ser un archivo JSON.")
    datos = {
        "tipo": "conteo-validator-ia",
        "version": 1,
        "exportado_en": datetime.now().isoformat(timespec="seconds"),
        "conteos": registro.conteos(),
        "total": registro.total,
        "eventos": [
            {
                "canal": e.canal,
                "frame": e.cuadro,
                "tiempo_s": round(e.cuadro / fps, 3) if fps and fps > 0 else None,
                "id_pez": e.id_pez,
                "origen": e.origen,
            }
            for e in registro.eventos()
        ],
    }
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
        temporal.replace(destino)
    except OSError as exc:
        temporal.unlink(missing_ok=True)
        raise ErrorPersistencia(f"No se pudo exportar el conteo: {exc}") from exc
    return destino
