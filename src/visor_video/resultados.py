"""Lectura y agrupación de detecciones de dos tubos con caída vertical.

Formato esperado (CSV, una fila por pez detectado en un cuadro):

    frame,track_id,x1,y1,x2,y2,canal
    0,1,100,50,180,90,1
    0,2,300,60,390,110,2

- frame: número de cuadro, empezando en 0 (ver PRIMER_CUADRO).
- track_id: identificador de seguimiento del pez.
- x1,y1,x2,y2: caja en píxeles del video original (y aumenta hacia abajo).
  Alternativa: x,y,w,h (esquina superior izquierda, ancho y alto).
- canal: tubo al que pertenece (1 o 2 en el visor actual).
- timestamp_ms (opcional): tiempo del evento en milisegundos.
- contado (opcional): indica si la fila corresponde a un evento de conteo.

El formato común con el Tracker aún no está acordado, por eso se aceptan
varios nombres de columna (ver ALIAS) y los separadores "," ";" y tabulador.
Si el formato final cambia, solo hay que tocar este archivo.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass


import cv2

# Cambiar a 1 si el tracker numera desde 1.
PRIMER_CUADRO = 0

ALIAS = {
    "frame": ("frame", "cuadro", "frame_id", "n_frame", "nframe"),
    "id": ("track_id", "id", "id_pez", "pez_id", "tid", "track"),
    "x1": ("x1", "xmin", "x_min", "left", "izquierda"),
    "y1": ("y1", "ymin", "y_min", "top", "arriba"),
    "x2": ("x2", "xmax", "x_max", "right", "derecha"),
    "y2": ("y2", "ymax", "y_max", "bottom", "abajo"),
    "x": ("x",),
    "y": ("y",),
    "w": ("w", "width", "ancho"),
    "h": ("h", "height", "alto"),
    "canal": ("canal", "channel", "tubo", "tube", "canal_id"),
    "timestamp": ("timestamp_ms", "tiempo_ms", "timestamp", "time_ms"),
    "contado": ("contado", "counted", "evento_conteo", "es_conteo"),
}


class ErrorResultados(Exception):
    """Error de lectura con un mensaje pensado para mostrar al usuario."""


@dataclass(frozen=True)
class Deteccion:
    cuadro: int
    id_pez: str
    x1: int
    y1: int
    x2: int
    y2: int
    canal: str
    timestamp_ms: int | None = None
    contado: bool = False


def etiqueta_canal(canal):
    """'2' -> 'Tubo 2'. Si el canal ya es un nombre, lo deja igual."""
    return f"Tubo {canal}" if str(canal).isdigit() else str(canal)


def _clave_canal(canal):
    return (0, int(canal), "") if canal.isdigit() else (1, 0, canal)


class Resultados:
    """Detecciones indexadas por canal y por cuadro."""

    def __init__(self, detecciones):
        self.detecciones = list(detecciones)
        self._indice = defaultdict(lambda: defaultdict(list))
        for d in self.detecciones:
            self._indice[d.canal][d.cuadro].append(d)

    @property
    def canales(self):
        return sorted(self._indice, key=_clave_canal)

    @property
    def ultimo_cuadro(self):
        if not self.detecciones:
            return -1
        return max(d.cuadro for d in self.detecciones)

    def en_cuadro(self, cuadro, canal=None):
        """Detecciones de un cuadro. canal=None devuelve todos los tubos."""
        if canal is None:
            resultado = []
            for por_cuadro in self._indice.values():
                resultado.extend(por_cuadro.get(cuadro, []))
            return resultado
        return list(self._indice.get(canal, {}).get(cuadro, []))

    def peces_por_canal(self):
        """Cantidad de identificadores distintos vistos en cada canal."""
        return {
            canal: len({d.id_pez for lista in por_cuadro.values() for d in lista})
            for canal, por_cuadro in self._indice.items()
        }


def _buscar_columnas(encabezado):
    normal = {nombre.strip().lower(): nombre for nombre in encabezado}

    def buscar(clave):
        for alias in ALIAS[clave]:
            if alias in normal:
                return normal[alias]
        return None

    columnas = {k: buscar(k) for k in ("frame", "id", "canal")}
    columnas["timestamp"] = buscar("timestamp")
    columnas["contado"] = buscar("contado")
    if buscar("x1") and buscar("y1") and buscar("x2") and buscar("y2"):
        columnas.update({k: buscar(k) for k in ("x1", "y1", "x2", "y2")})
        columnas["formato_caja"] = "esquinas"
    elif buscar("x") and buscar("y") and buscar("w") and buscar("h"):
        columnas.update({k: buscar(k) for k in ("x", "y", "w", "h")})
        columnas["formato_caja"] = "xywh"
    else:
        columnas["formato_caja"] = None

    faltan = [k for k in ("frame", "id", "canal") if columnas[k] is None]
    if columnas["formato_caja"] is None:
        faltan.append("caja (x1,y1,x2,y2 o x,y,w,h)")
    if faltan:
        raise ErrorResultados(
            "Al archivo le faltan columnas: " + ", ".join(faltan) + ".\n"
            "Columnas encontradas: " + ", ".join(encabezado)
        )
    return columnas


def cargar_csv(ruta):
    """Lee el CSV del Tracker y devuelve un objeto Resultados."""
    try:
        with open(ruta, newline="", encoding="utf-8-sig") as archivo:
            muestra = archivo.read(4096)
            archivo.seek(0)
            try:
                dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t")
            except csv.Error:
                dialecto = csv.excel
            lector = csv.DictReader(archivo, dialect=dialecto)
            if not lector.fieldnames:
                raise ErrorResultados("El archivo está vacío.")
            col = _buscar_columnas(lector.fieldnames)

            detecciones = []
            for n_linea, fila in enumerate(lector, start=2):
                try:
                    cuadro = int(float(fila[col["frame"]])) - PRIMER_CUADRO
                    if col["formato_caja"] == "esquinas":
                        x1, y1, x2, y2 = (
                            int(float(fila[col[k]])) for k in ("x1", "y1", "x2", "y2")
                        )
                    else:
                        x, y, w, h = (
                            float(fila[col[k]]) for k in ("x", "y", "w", "h")
                        )
                        x1, y1, x2, y2 = int(x), int(y), int(x + w), int(y + h)
                except (ValueError, TypeError, KeyError):
                    raise ErrorResultados(
                        f"Línea {n_linea}: hay un valor que no es un número "
                        "o falta un dato."
                    )
                timestamp_ms = None
                if col["timestamp"] is not None:
                    valor_tiempo = str(fila.get(col["timestamp"], "")).strip()
                    if valor_tiempo:
                        try:
                            timestamp_ms = int(float(valor_tiempo))
                        except ValueError:
                            raise ErrorResultados(
                                f"Línea {n_linea}: el tiempo no es un número válido."
                            )

                contado = False
                if col["contado"] is not None:
                    valor_contado = str(fila.get(col["contado"], "")).strip().lower()
                    contado = valor_contado in {
                        "1", "true", "si", "sí", "yes", "y", "conteo", "counted"
                    }

                detecciones.append(
                    Deteccion(
                        cuadro=cuadro,
                        id_pez=str(fila[col["id"]]).strip(),
                        x1=x1, y1=y1, x2=x2, y2=y2,
                        canal=str(fila[col["canal"]]).strip(),
                        timestamp_ms=timestamp_ms,
                        contado=contado,
                    )
                )
    except OSError as error:
        raise ErrorResultados(f"No se pudo abrir el archivo: {error}")
    except UnicodeDecodeError:
        raise ErrorResultados("El archivo no está en texto UTF-8 válido.")

    if not detecciones:
        raise ErrorResultados("El archivo no tiene detecciones.")
    return Resultados(detecciones)


def _color_de_id(id_pez):
    """Color BGR estable para cada pez, para distinguirlos entre cuadros."""
    semilla = sum(ord(c) for c in id_pez) * 47
    return (60 + semilla % 196, 60 + (semilla // 3) % 196, 60 + (semilla // 7) % 196)


def dibujar_cajas(cuadro, detecciones):
    """Dibuja las cajas sobre una copia del cuadro (BGR) y la devuelve."""
    salida = cuadro.copy()
    grosor = max(2, salida.shape[1] // 400)
    escala = max(0.6, salida.shape[1] / 1400)
    for d in detecciones:
        color = _color_de_id(d.id_pez)
        cv2.rectangle(salida, (d.x1, d.y1), (d.x2, d.y2), color, grosor)
        cv2.putText(
            salida,
            f"ID {d.id_pez}",
            (d.x1, max(15, d.y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            escala,
            color,
            grosor,
        )
    return salida