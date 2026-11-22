import csv
import os
import re
from collections import defaultdict
from dataclasses import dataclass

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


class ErrorSinCanal(ErrorResultados):
    """El archivo no tiene columna de canal (típico: un archivo por tubo)."""


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


def _buscar_columnas(encabezado, canal_defecto=None):
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

    faltan = [
        k for k in ("frame", "id", "canal")
        if columnas[k] is None and not (k == "canal" and canal_defecto is not None)
    ]
    if columnas["formato_caja"] is None:
        faltan.append("caja (x1,y1,x2,y2 o x,y,w,h)")
    if faltan:
        mensaje = (
            "Al archivo le faltan columnas: " + ", ".join(faltan) + ".\n"
            "Columnas encontradas: " + ", ".join(encabezado)
        )
        if faltan == ["canal"]:
            raise ErrorSinCanal(mensaje)
        raise ErrorResultados(mensaje)
    return columnas


def cargar_csv(ruta, canal_defecto=None):
    """Lee el CSV del Tracker y devuelve un objeto Resultados.

    Si el archivo no trae columna de canal (un archivo por tubo), todas
    sus filas se asignan a `canal_defecto`.
    """
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
            col = _buscar_columnas(lector.fieldnames, canal_defecto)

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
                        canal=(str(canal_defecto) if col["canal"] is None
                               else str(fila[col["canal"]]).strip()),
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


def canal_desde_nombre(ruta):
    """Intenta leer el tubo del nombre del archivo.

    'tracking_tubo1.csv' -> '1', 'canal_2.csv' -> '2', 'salida_t2.csv' -> '2'.
    Devuelve None si el nombre no lo dice.
    """
    nombre = os.path.splitext(os.path.basename(str(ruta)))[0].lower()
    m = re.search(r"(?<![a-z])(?:tubo|tube|canal|channel|ch|t)[ _\-]?(\d+)(?!\d)", nombre)
    return m.group(1) if m else None


def cargar_varios(rutas, resolver_canal=None):
    """Carga uno o varios CSV del Tracker y los junta en un solo Resultados.

    Soporta los dos casos:
      - un archivo con los dos tubos (columna de canal), o
      - un archivo por tubo (sin columna de canal).

    Para un archivo sin columna de canal, el tubo se toma del nombre del
    archivo; si el nombre no lo dice, se llama a `resolver_canal(ruta)`
    (en el visor, pregunta al usuario). Cada canal debe venir de un solo
    archivo.
    """
    rutas = list(rutas)
    if not rutas:
        raise ErrorResultados("No se eligió ningún archivo.")
    varios = len(rutas) > 1
    detecciones = []
    origen = {}  # canal -> nombre de archivo
    for ruta in rutas:
        nombre = os.path.basename(str(ruta))
        try:
            try:
                parcial = cargar_csv(ruta)
            except ErrorSinCanal:
                canal = canal_desde_nombre(ruta)
                if canal is None and resolver_canal is not None:
                    canal = resolver_canal(ruta)
                if canal is None:
                    raise ErrorResultados(
                        "El archivo no tiene columna de canal y no se pudo saber "
                        "a qué tubo corresponde. Agrega la columna 'canal' o "
                        "nombra el archivo, por ejemplo, tracking_tubo1.csv."
                    )
                parcial = cargar_csv(ruta, canal_defecto=canal)
        except ErrorResultados as exc:
            raise ErrorResultados(f"{nombre}: {exc}" if varios else str(exc))
        for canal in parcial.canales:
            if canal in origen:
                raise ErrorResultados(
                    f"El canal {canal} viene en «{origen[canal]}» y también en "
                    f"«{nombre}». Cada tubo debe venir de un solo archivo."
                )
            origen[canal] = nombre
        detecciones.extend(parcial.detecciones)
    return Resultados(detecciones)

    return salida