"""Canales (tubos) definidos por el Tracker: un recuadro por tubo y su línea de conteo."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_LINEA = ("linea_y", "linea_conteo_y", "line_y", "y_linea")


class ErrorCanales(Exception):
    """Error con un mensaje pensado para mostrar al usuario."""


@dataclass(frozen=True)
class Canal:
    id: str
    x1: float
    y1: float
    x2: float
    y2: float
    linea_y: float


def _numero(valor, nombre, canal):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorCanales(f"Canal {canal}: «{nombre}» debe ser un número.")
    return float(valor)


def _canal_desde_dict(id_canal, d):
    if not isinstance(d, dict):
        raise ErrorCanales(f"Canal {id_canal}: se esperaba un objeto con el recuadro.")
    if all(k in d for k in ("x1", "y1", "x2", "y2")):
        x1, y1, x2, y2 = (_numero(d[k], k, id_canal) for k in ("x1", "y1", "x2", "y2"))
    elif all(k in d for k in ("x", "y", "w", "h")):
        x, y, w, h = (_numero(d[k], k, id_canal) for k in ("x", "y", "w", "h"))
        x1, y1, x2, y2 = x, y, x + w, y + h
    else:
        raise ErrorCanales(
            f"Canal {id_canal}: falta el recuadro (x1,y1,x2,y2 o x,y,w,h)."
        )
    if x2 <= x1 or y2 <= y1:
        raise ErrorCanales(f"Canal {id_canal}: el recuadro tiene tamaño cero o negativo.")

    valor_linea = next((d[k] for k in _LINEA if d.get(k) is not None), None)
    linea = (y1 + y2) / 2 if valor_linea is None else _numero(valor_linea, "linea_y", id_canal)
    if not y1 <= linea <= y2:
        raise ErrorCanales(f"Canal {id_canal}: la línea de conteo queda fuera del recuadro.")
    return Canal(str(id_canal), x1, y1, x2, y2, linea)


def cargar_canales(ruta):
    """Lee el archivo de canales del Tracker. Devuelve {id_canal: Canal}."""
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorCanales(f"No se pudo leer el archivo de canales: {exc}") from exc

    bruto = datos.get("canales") if isinstance(datos, dict) else datos
    if isinstance(bruto, dict):
        items = [(str(k), v) for k, v in bruto.items()]
    elif isinstance(bruto, list):
        items = [
            (str(v.get("canal", v.get("id", n))) if isinstance(v, dict) else str(n), v)
            for n, v in enumerate(bruto, start=1)
        ]
    else:
        raise ErrorCanales("El archivo debe tener una sección «canales».")
    if not items:
        raise ErrorCanales("El archivo no define ningún canal.")

    canales = {}
    for id_canal, d in items:
        if id_canal in canales:
            raise ErrorCanales(f"El canal {id_canal} aparece repetido.")
        canales[id_canal] = _canal_desde_dict(id_canal, d)
    return canales