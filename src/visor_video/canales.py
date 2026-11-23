"""Canales (tubos) definidos por el Tracker: un recuadro por tubo y su línea de conteo."""

from __future__ import annotations

import json
import re
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


def _id_canal(valor):
    """'canal_1' / 'tubo_2' / 'Tubo 2' / '2' -> '1' / '2' / '2' / '2'."""
    texto = str(valor).strip()
    m = re.search(r"(\d+)\s*$", texto)
    return m.group(1) if m else texto


def _numero(valor, nombre, canal):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorCanales(f"Canal {canal}: «{nombre}» debe ser un número.")
    return float(valor)


def _canal_desde_dict(id_canal, d):
    if not isinstance(d, dict):
        raise ErrorCanales(f"Canal {id_canal}: se esperaba un objeto con el recuadro.")
    if "caja" in d:
        caja = d["caja"]
        if not isinstance(caja, (list, tuple)) or len(caja) != 4:
            raise ErrorCanales(f"Canal {id_canal}: «caja» debe ser [x1, y1, x2, y2].")
        x1, y1, x2, y2 = (_numero(v, "caja", id_canal) for v in caja)
    elif all(k in d for k in ("x1", "y1", "x2", "y2")):
        x1, y1, x2, y2 = (_numero(d[k], k, id_canal) for k in ("x1", "y1", "x2", "y2"))
    elif all(k in d for k in ("x", "y", "w", "h")):
        x, y, w, h = (_numero(d[k], k, id_canal) for k in ("x", "y", "w", "h"))
        x1, y1, x2, y2 = x, y, x + w, y + h
    else:
        raise ErrorCanales(
            f"Canal {id_canal}: falta el recuadro (caja, x1,y1,x2,y2 o x,y,w,h)."
        )
    if x2 <= x1 or y2 <= y1:
        raise ErrorCanales(f"Canal {id_canal}: el recuadro tiene tamaño cero o negativo.")

    valor_linea = next((d[k] for k in _LINEA if d.get(k) is not None), None)
    linea = (y1 + y2) / 2 if valor_linea is None else _numero(valor_linea, "linea_y", id_canal)
    if not y1 <= linea <= y2:
        raise ErrorCanales(f"Canal {id_canal}: la línea de conteo queda fuera del recuadro.")
    return Canal(id_canal, x1, y1, x2, y2, linea)


def cargar_canales(ruta):
    """Lee los canales de un JSON (formato común v1 o archivo solo de canales)."""
    if Path(ruta).suffix.lower() != ".json":
        raise ErrorCanales("La configuración de canales debe ser un archivo JSON.")
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorCanales(f"No se pudo leer el archivo de canales: {exc}") from exc

    bruto = datos.get("canales") if isinstance(datos, dict) else datos
    if isinstance(bruto, dict):
        items = [(_id_canal(k), v) for k, v in bruto.items()]
    elif isinstance(bruto, list):
        items = [
            (_id_canal(v.get("canal", v.get("id", n))) if isinstance(v, dict) else str(n), v)
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