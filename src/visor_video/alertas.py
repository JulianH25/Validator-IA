"""Alertas sobre detecciones de salmones que descienden por dos tubos."""
from collections import defaultdict
import json
from pathlib import Path
from dataclasses import dataclass, field
from itertools import combinations
from math import hypot


@dataclass(frozen=True)
class Alerta:
    tipo: str
    cuadro: int
    canal: str
    mensaje: str
    ids_pez: tuple[str, ...] = ()
    detalles: dict = field(default_factory=dict)


@dataclass
class ConfiguracionAlertas:
    iou_minimo: float = 0.30
    distancia_centros_max_px: float = 28.0

    max_cuadros_faltantes: int = 1
    lineas_conteo_y_px: dict[str, float] = field(default_factory=dict)


class MotorAlertas:
    def __init__(self, config=None):
        self.config = config or ConfiguracionAlertas()

    def analizar(self, detecciones):
        detecciones = list(detecciones)
        alertas = []
        alertas.extend(self._detectar_peces_juntos(detecciones))
        alertas.extend(self._detectar_perdidas_seguimiento(detecciones))
        alertas.extend(self._detectar_aparicion_un_cuadro(detecciones))
        alertas.extend(self._detectar_inicio_bajo_linea(detecciones))
        return sorted(alertas, key=lambda a: (a.cuadro, a.tipo, str(a.canal)))

    @staticmethod
    def _bbox(d):
        return float(d.x1), float(d.y1), float(d.x2), float(d.y2)

    @classmethod
    def _iou(cls, a, b):
        ax1, ay1, ax2, ay2 = cls._bbox(a)
        bx1, by1, bx2, by2 = cls._bbox(b)

        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        ancho = max(0.0, ix2 - ix1)
        alto = max(0.0, iy2 - iy1)
        interseccion = ancho * alto

        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - interseccion
        return interseccion / union if union > 0 else 0.0

    @classmethod
    def _distancia_centros(cls, a, b):
        ax1, ay1, ax2, ay2 = cls._bbox(a)
        bx1, by1, bx2, by2 = cls._bbox(b)
        centro_a = ((ax1 + ax2) / 2, (ay1 + ay2) / 2)
        centro_b = ((bx1 + bx2) / 2, (by1 + by2) / 2)
        return hypot(centro_a[0] - centro_b[0], centro_a[1] - centro_b[1])

    def _detectar_peces_juntos(self, detecciones):
        por_cuadro_canal = defaultdict(list)
        for d in detecciones:
            por_cuadro_canal[(d.cuadro, d.canal)].append(d)

        candidatas = []
        for (cuadro, canal), grupo in por_cuadro_canal.items():
            for a, b in combinations(grupo, 2):
                if a.id_pez == b.id_pez:
                    continue

                iou = self._iou(a, b)
                distancia = self._distancia_centros(a, b)
                if (
                    iou >= self.config.iou_minimo
                    or distancia <= self.config.distancia_centros_max_px
                ):
                    ids = tuple(sorted((a.id_pez, b.id_pez)))
                    candidatas.append(
                        Alerta(
                            tipo="PECES_JUNTOS",
                            cuadro=cuadro,
                            canal=canal,
                            ids_pez=ids,
                            mensaje=(
                                f"Peces muy juntos - cuadro {cuadro + 1} - "
                                f"Tubo {canal} - IDs {ids[0]} y {ids[1]}"
                            ),
                            detalles={
                                "iou": round(iou, 4),
                                "distancia_centros_px": round(distancia, 2),
                            },
                        )
                    )

        candidatas.sort(key=lambda a: (str(a.canal), a.ids_pez, a.cuadro))
        resultado = []
        ultimo_por_pareja = {}
        for alerta in candidatas:
            clave = (str(alerta.canal), alerta.ids_pez)
            ultimo = ultimo_por_pareja.get(clave)
            if ultimo is None or alerta.cuadro > ultimo + 1:
                resultado.append(alerta)
            ultimo_por_pareja[clave] = alerta.cuadro
        return resultado

    def _detectar_perdidas_seguimiento(self, detecciones):
        por_track = defaultdict(set)
        for d in detecciones:
            por_track[(d.canal, d.id_pez)].add(d.cuadro)

        alertas = []
        for (canal, id_pez), cuadros_set in por_track.items():
            cuadros = sorted(cuadros_set)
            for anterior, actual in zip(cuadros, cuadros[1:]):
                faltantes = actual - anterior - 1
                if faltantes > self.config.max_cuadros_faltantes:
                    cuadro_alerta = anterior + 1
                    alertas.append(
                        Alerta(
                            tipo="PERDIDA_SEGUIMIENTO",
                            cuadro=cuadro_alerta,
                            canal=canal,
                            ids_pez=(id_pez,),
                            mensaje=(
                                f"Posible pérdida de seguimiento - cuadro "
                                f"{cuadro_alerta + 1} - Tubo {canal} - ID {id_pez}"
                            ),
                            detalles={
                                "ultimo_cuadro_visible": anterior,
                                "cuadro_reaparicion": actual,
                                "cuadros_faltantes": faltantes,
                            },
                        )
                    )
        return alertas

    def _detectar_aparicion_un_cuadro(self, detecciones):
        por_pez = defaultdict(set)
        for d in detecciones:
            por_pez[(d.canal, d.id_pez)].add(d.cuadro)

        alertas = []
        if not detecciones:
            return alertas
        inicio = min(d.cuadro for d in detecciones)
        fin = max(d.cuadro for d in detecciones)

        for (canal, id_pez), cuadros in por_pez.items():
            if len(cuadros) != 1:
                continue
            cuadro = next(iter(cuadros))
            alertas.append(
                Alerta(
                    tipo="APARICION_UN_CUADRO",
                    cuadro=cuadro,
                    canal=canal,
                    ids_pez=(id_pez,),
                    mensaje=(f"ID visible en un solo cuadro - cuadro {cuadro + 1} - "
                             f"Tubo {canal} - ID {id_pez}"),
                    detalles={"en_borde_datos": cuadro in (inicio, fin)},
                )
            )
        return alertas

    def _detectar_inicio_bajo_linea(self, detecciones):
        primeras = defaultdict(list)
        for d in detecciones:
            primeras[(d.canal, d.id_pez)].append(d)

        alertas = []
        for (canal, id_pez), registros in primeras.items():
            y_linea = self.config.lineas_conteo_y_px.get(str(canal))
            if y_linea is None:
                continue
            primer_cuadro = min(d.cuadro for d in registros)
            primeras_detecciones = [d for d in registros if d.cuadro == primer_cuadro]
            centro_y = max((d.y1 + d.y2) / 2 for d in primeras_detecciones)
            # En la imagen, hacia abajo corresponde a Y creciente.
            if centro_y <= y_linea:
                continue
            alertas.append(
                Alerta(
                    tipo="INICIO_BAJO_LINEA",
                    cuadro=primer_cuadro,
                    canal=canal,
                    ids_pez=(id_pez,),
                    mensaje=(f"Primera aparición bajo la línea - cuadro "
                             f"{primer_cuadro + 1} - Tubo {canal} - ID {id_pez}"),
                    detalles={"centro_y_px": centro_y, "linea_y_px": y_linea,
                              "inicio_video": primer_cuadro == 0},
                )
            )
        return alertas


def cargar_lineas_conteo(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        return {}
    with ruta.open(encoding="utf-8") as archivo:
        config = json.load(archivo)
    lineas = config.get("lineas_conteo_y_px")
    if not isinstance(lineas, dict):
        raise ValueError("Se esperaba 'lineas_conteo_y_px' como objeto.")
    resultado = {}
    for tubo in ("1", "2"):
        valor = lineas.get(tubo)
        if valor is None:
            continue
        if (isinstance(valor, bool) or not isinstance(valor, (int, float))
                or not 0 <= valor < float("inf")):
            raise ValueError(f"La línea del tubo {tubo} debe ser un número en píxeles.")
        resultado[tubo] = float(valor)
    return resultado
