"""Importa los archivos crudos de un tracker y los deja en el formato común v1."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import re
import sys


class ErrorImportacion(Exception):
    """Error con un mensaje pensado para mostrar al usuario."""


# ---------------------------------------------------------------- conversión (formato común v1)

def num_canal(texto):
    """'canal_1' / 'tubo_2' / '3' -> '1' / '2' / '3'."""
    m = re.search(r"(\d+)\s*$", str(texto))
    return m.group(1) if m else str(texto).strip()


def leer_csv(ruta):
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def leer_json(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8-sig"))


def _detecciones(filas, desfase):
    salida = []
    for f in filas:
        salida.append({
            "cuadro": int(float(f["cuadro"])) + desfase,
            "canal": num_canal(f["canal"]),
            "id": str(f["id"]).strip(),
            "x1": round(float(f["x1"]), 1),
            "y1": round(float(f["y1"]), 1),
            "x2": round(float(f["x2"]), 1),
            "y2": round(float(f["y2"]), 1),
            "conf": round(float(f["conf"]), 4) if f.get("conf") not in (None, "") else None,
            "timestamp_ms": int(round(float(f["tiempo_s"]) * 1000)),
            "contado": False,
        })
    salida.sort(key=lambda d: (d["cuadro"], d["canal"], d["id"]))
    return salida


def _marcar_eventos(detecciones, eventos):
    """Marca como contada la detección de cada evento. Devuelve los que no calzan."""
    indice = {}
    for d in detecciones:
        indice.setdefault((d["canal"], d["id"], d["cuadro"]), d)
    sin_deteccion = []
    for e in eventos:
        d = indice.get((e["canal"], e["id"], e["cuadro"]))
        if d is None:
            sin_deteccion.append(e)
        else:
            d["contado"] = True
    return sin_deteccion


def _armar(video, canales, detecciones, eventos):
    sin = _marcar_eventos(detecciones, eventos)
    if sin:
        print(f"ADVERTENCIA: {len(sin)} evento(s) sin detección en su cuadro "
              f"(no se verán como conteo en el Validador): "
              + ", ".join(f"T{e['canal']} id {e['id']} cuadro {e['cuadro']}" for e in sin),
              file=sys.stderr)
    return {
        "formato": "v1",
        "video": video,
        "canales": canales,
        "detecciones": detecciones,
        "eventos": eventos,
    }


# ---------------------------------------------------------------- tracker A

def desde_tracker_a(tray, conteos, canales, meta, desfase=0):
    detecciones = _detecciones(leer_csv(tray), desfase)

    eventos = [{
        "cuadro": int(float(f["cuadro"])) + desfase,
        "canal": num_canal(f["canal"]),
        "id": str(f["id"]).strip(),
        "tiempo_s": round(float(f["tiempo_s"]), 3),
    } for f in leer_csv(conteos)]
    eventos.sort(key=lambda e: (e["cuadro"], e["canal"], e["id"]))

    c = leer_json(canales)
    lista = []
    for ch in c["canales"]:
        if ch.get("activo") is False:
            continue
        x1, y1, x2, y2 = (float(v) for v in ch["caja"])
        # linea_b = línea de conteo, como fracción de la altura de la caja del tubo.
        linea_y = y1 + float(ch["linea_b"]) * (y2 - y1)
        lista.append({
            "id": num_canal(ch["id"]),
            "nombre": ch.get("nombre") or f"Tubo {num_canal(ch['id'])}",
            "caja": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            "linea_y": round(linea_y, 1),
        })

    m = leer_json(meta)
    video = {
        "archivo": Path(str(m.get("video", c.get("video", {}).get("archivo", "")))).name,
        "fps": float(m["fps"]),
        "ancho": int(m["ancho"]),
        "alto": int(m["alto"]),
        "cuadros": int(m["cuadros"]),
    }
    return _armar(video, lista, detecciones, eventos)


# ---------------------------------------------------------------- tracker B

def desde_tracker_b(resultados, detecciones_csv, desfase=0):
    r = leer_json(resultados)
    v = r["video"]
    ancho, alto = int(v["ancho"]), int(v["alto"])

    lista = []
    for ch in r["canales"]:
        if ch.get("seleccionado") is False:
            continue
        xs = [p[0] * ancho for p in ch["poligono"]]
        ys = [p[1] * alto for p in ch["poligono"]]
        linea_y = sum(p[1] for p in ch["linea"]) / len(ch["linea"]) * alto
        lista.append({
            "id": num_canal(ch["id"]),
            "nombre": ch.get("nombre") or f"Tubo {num_canal(ch['id'])}",
            "caja": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
            "linea_y": round(linea_y, 1),
        })

    detecciones = _detecciones(leer_csv(detecciones_csv), desfase)
    eventos = [{
        "cuadro": int(e["cuadro"]) + desfase,
        "canal": num_canal(e["canal"]),
        "id": str(e["id"]).strip(),
        "tiempo_s": round(float(e["tiempo_s"]), 3),
    } for e in r["eventos"]]
    eventos.sort(key=lambda e: (e["cuadro"], e["canal"], e["id"]))

    video = {
        "archivo": Path(str(v["archivo"]).replace("\\", "/")).name,
        "fps": float(v["fps"]),
        "ancho": ancho,
        "alto": alto,
        "cuadros": v.get("cuadros"),  # el tracker B no lo informa
    }
    return _armar(video, lista, detecciones, eventos)


# ---------------------------------------------------------------- tracker C

def desde_tracker_c(ruta):
    d = leer_json(ruta)
    s = d["secuencia"]

    lista = []
    for ch in d["canales"]:
        if ch.get("activo") is False:
            continue
        x1, y1, x2, y2 = (float(v) for v in ch["caja"])
        lista.append({
            "id": num_canal(ch["id"]),
            "nombre": ch.get("nombre") or f"Tubo {num_canal(ch['id'])}",
            "caja": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            "linea_y": round(float(ch["linea_b_y"]), 1),
        })

    detecciones = []
    for c in d["cuadros"]:
        for t in c.get("trayectorias", []):
            detecciones.append({
                "cuadro": int(c["cuadro"]),
                "canal": num_canal(t["canal"]),
                "id": str(t["id"]).strip(),
                "x1": round(float(t["x1"]), 1),
                "y1": round(float(t["y1"]), 1),
                "x2": round(float(t["x2"]), 1),
                "y2": round(float(t["y2"]), 1),
                "conf": t.get("conf"),
                "timestamp_ms": int(round(float(c["tiempo_s"]) * 1000)),
                "contado": False,
            })
    detecciones.sort(key=lambda x: (x["cuadro"], x["canal"], x["id"]))

    eventos = [{
        "cuadro": int(e["cuadro"]),
        "canal": num_canal(e["canal"]),
        "id": str(e["id"]).strip(),
        "tiempo_s": round(float(e["tiempo_s"]), 3),
    } for e in d["conteo"]["eventos"]]
    eventos.sort(key=lambda e: (e["cuadro"], e["canal"], e["id"]))

    video = {
        "archivo": Path(str(s["video"]).replace("\\", "/")).name,
        "fps": float(s["fps"]),
        "ancho": int(s["ancho"]),
        "alto": int(s["alto"]),
        "cuadros": int(s["cuadros"]),
    }
    return _armar(video, lista, detecciones, eventos)


def necesita_conversion(rutas):
    """True si hay CSV del tracker o un JSON que aún no está en formato común."""
    return any(
        Path(r).suffix.lower() == ".csv" or _clasificar(r) == "tracker_c"
        for r in rutas
    )


# ---------------------------------------------------------------- detección de archivos


def _encabezado_csv(ruta):
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        return [c.strip().lower() for c in next(csv.reader(f), [])]


def _json(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _clasificar(ruta):
    """'trayectorias', 'conteos', 'detecciones', 'canales', 'meta', 'resultados' o None."""
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    if ext == ".csv":
        try:
            cols = set(_encabezado_csv(ruta))
        except (OSError, UnicodeError, csv.Error):
            return None
        if "conteo" in cols:
            return "conteos"
        if {"cuadro", "canal", "x1", "y1", "x2", "y2"} <= cols:
            return "trayectorias" if "id" in cols else "detecciones"
        return None
    if ext == ".json":
        d = _json(ruta)
        if not isinstance(d, dict):
            return None
        if d.get("formato") == "tracker-resultados" and "cuadros" in d:
            return "tracker_c"
        canales = d.get("canales")
        if isinstance(d.get("eventos"), list) and isinstance(canales, list) and "video" in d:
            return "resultados"
        if isinstance(canales, list) and canales and isinstance(canales[0], dict) and "caja" in canales[0]:
            return "canales"
        if "fps" in d and "cuadros" in d:
            return "meta"
    return None


def clasificar(rutas):
    por_rol = {}
    for r in rutas:
        rol = _clasificar(r)
        if rol is None:
            raise ErrorImportacion(f"No reconozco el archivo «{Path(r).name}» como salida del tracker.")
        if rol in por_rol:
            raise ErrorImportacion(f"Hay dos archivos de tipo «{rol}»: «{Path(por_rol[rol]).name}» y «{Path(r).name}».")
        por_rol[rol] = r
    return por_rol


def convertir(rutas, destino=None):
    """Convierte los archivos elegidos al formato común y devuelve la ruta del JSON creado.

    Tracker A: trayectorias.csv + conteos.csv + canales.json + meta.json
    Tracker B: resultados.json + CSV de detecciones con id
    """
    rutas = [str(r) for r in rutas]
    roles = clasificar(rutas)


    if "tracker_c" in roles:
        if len(roles) > 1:
            raise ErrorImportacion("El JSON del tracker ya trae todo: selecciónalo solo.")
        try:
            datos = desde_tracker_c(roles["tracker_c"])
        except (KeyError, ValueError, TypeError, OSError) as exc:
            raise ErrorImportacion(f"No se pudo convertir la salida del tracker: {exc!r}") from exc
        referencia = roles["tracker_c"]
    elif "resultados" in roles:
        tray = roles.get("trayectorias") or roles.get("detecciones")
        if tray is None:
            raise ErrorImportacion("Falta el CSV de detecciones junto a resultados.json.")
        try:
            datos = desde_tracker_b(roles["resultados"], tray)
        except (KeyError, ValueError, TypeError, OSError) as exc:
            raise ErrorImportacion(f"No se pudo convertir la salida del tracker: {exc!r}") from exc
        referencia = roles["resultados"]
    else:
        faltan = [n for n in ("trayectorias", "conteos", "canales", "meta") if n not in roles]
        if faltan:
            raise ErrorImportacion(
                "Faltan archivos del tracker: " + ", ".join(f"{n}" for n in faltan) + ".\n"
                "Selecciona juntos trayectorias.csv, conteos.csv, canales.json y meta.json."
            )
        try:
            datos = desde_tracker_a(roles["trayectorias"], roles["conteos"],
                                    roles["canales"], roles["meta"])
        except (KeyError, ValueError, TypeError, OSError) as exc:
            raise ErrorImportacion(f"No se pudo convertir la salida del tracker: {exc!r}") from exc
        referencia = roles["trayectorias"]

    if not datos["detecciones"]:
        raise ErrorImportacion("Los archivos del tracker no tienen detecciones.")
    if destino is None:
        nombre = Path(datos["video"]["archivo"]).stem or "tracker"
        destino = Path(referencia).with_name(f"formato_comun_{nombre}.json")
    destino = Path(destino)
    try:
        destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as exc:
        raise ErrorImportacion(f"No se pudo guardar el archivo convertido: {exc}") from exc
    return destino