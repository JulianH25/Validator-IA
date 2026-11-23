"""Convierte una carpeta de frames (JPEG/PNG) en un video MP4."""

from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp"}


class ErrorFrames(Exception):
    """Error con un mensaje pensado para mostrar al usuario."""


def _clave_natural(ruta: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", ruta.name)]


def listar_frames(carpeta):
    """Frames de la carpeta, ordenados por nombre (0002 antes que 0010)."""
    base = Path(carpeta)
    if not base.is_dir():
        raise ErrorFrames("La carpeta elegida no existe.")
    frames = sorted(
        (p for p in base.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONES),
        key=_clave_natural,
    )
    if not frames:
        raise ErrorFrames("La carpeta no tiene imágenes (.jpg, .jpeg, .png o .bmp).")
    return frames


def numeros_faltantes(frames, limite=10):
    """Números que faltan en la numeración (p. ej. 2038 si va 2037 → 2039).

    Devuelve (cantidad_total, primeros_faltantes). Si los nombres no son
    numéricos no se puede saber y devuelve (0, []).
    """
    if not all(p.stem.isdigit() for p in frames):
        return 0, []
    numeros = [int(p.stem) for p in frames]
    faltan = []
    total = 0
    for anterior, actual in zip(numeros, numeros[1:]):
        hueco = actual - anterior - 1
        if hueco > 0:
            total += hueco
            if len(faltan) < limite:
                faltan.extend(range(anterior + 1, min(actual, anterior + 1 + limite - len(faltan))))
    return total, faltan


def _leer(ruta: Path):
    # imdecode + fromfile evita problemas de cv2.imread con rutas con tildes en Windows.
    imagen = cv2.imdecode(np.fromfile(str(ruta), dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        raise ErrorFrames(f"No se pudo leer la imagen «{ruta.name}».")
    return imagen


def frames_a_video(carpeta, destino, fps, progreso=None):
    """Crea `destino` (.mp4) con los frames de `carpeta` en orden.

    progreso(i, total) se llama cada cierto número de frames.
    Devuelve un dict con: frames, ancho, alto, fps, faltantes, primeros_faltantes.
    """
    if not fps or fps <= 0:
        raise ErrorFrames("Los cuadros por segundo deben ser mayores que 0.")
    frames = listar_frames(carpeta)
    destino = Path(destino)
    if destino.suffix.lower() != ".mp4":
        raise ErrorFrames("El video debe guardarse como .mp4.")

    primero = _leer(frames[0])
    alto, ancho = primero.shape[:2]

    temporal = destino.with_name(destino.stem + ".tmp.mp4")
    escritor = cv2.VideoWriter(
        str(temporal), cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (ancho, alto)
    )
    if not escritor.isOpened():
        raise ErrorFrames("No se pudo crear el archivo de video (¿hay permiso de escritura?).")

    try:
        for i, ruta in enumerate(frames):
            imagen = primero if i == 0 else _leer(ruta)
            if imagen.shape[:2] != (alto, ancho):
                raise ErrorFrames(
                    f"«{ruta.name}» mide {imagen.shape[1]}x{imagen.shape[0]} y el primer "
                    f"frame mide {ancho}x{alto}. Todos deben tener el mismo tamaño."
                )
            escritor.write(imagen)
            if progreso is not None and (i % 20 == 0 or i == len(frames) - 1):
                progreso(i + 1, len(frames))
        escritor.release()
        temporal.replace(destino)
    except BaseException:
        escritor.release()
        temporal.unlink(missing_ok=True)
        raise

    faltantes, primeros = numeros_faltantes(frames)
    return {
        "frames": len(frames),
        "ancho": ancho,
        "alto": alto,
        "fps": float(fps),
        "faltantes": faltantes,
        "primeros_faltantes": primeros,
    }