"""Detección de posibles anomalías en los resultados del tracker.

El motor trabaja con las detecciones ya cargadas por ``resultados.py`` y no
modifica ni el video ni el CSV original. Cada alerta conserva el número de
cuadro interno (base 0) para que el visor pueda saltar directamente a él.
"""
from collections import defaultdict
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
    # Umbrales provisionales para detectar peces sospechosamente cercanos.
    iou_minimo: float = 0.30
    distancia_centros_max_px: float = 28.0

    # Si el mismo ID reaparece después de más cuadros faltantes, se avisa.
    max_cuadros_faltantes: int = 1

    # Ventana provisional para dos eventos de conteo del mismo pez.
    ventana_duplicado_ms: int = 100
    ventana_duplicado_cuadros: int = 3


class MotorAlertas:
    def __init__(self, config=None):
        self.config = config or ConfiguracionAlertas()

    def analizar(self, detecciones):
        detecciones = list(detecciones)
        alertas = []
        alertas.extend(self._detectar_peces_juntos(detecciones))
        alertas.extend(self._detectar_perdidas_seguimiento(detecciones))
        alertas.extend(self._detectar_duplicados(detecciones))
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

        # No repetir la misma pareja en cada cuadro consecutivo.
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

    def _detectar_duplicados(self, detecciones):
        alertas = []

        # Caso 1: el mismo ID aparece repetido dentro del mismo cuadro y tubo.
        por_cuadro = defaultdict(list)
        for d in detecciones:
            por_cuadro[(d.canal, d.cuadro, d.id_pez)].append(d)

        for (canal, cuadro, id_pez), grupo in por_cuadro.items():
            if len(grupo) > 1:
                alertas.append(
                    Alerta(
                        tipo="POSIBLE_DUPLICADO",
                        cuadro=cuadro,
                        canal=canal,
                        ids_pez=(id_pez,),
                        mensaje=(
                            f"Posible duplicado - cuadro {cuadro + 1} - "
                            f"Tubo {canal} - ID {id_pez}"
                        ),
                        detalles={"detecciones_mismo_cuadro": len(grupo)},
                    )
                )

        # Caso 2: si el tracker entrega eventos de conteo, comparar sus tiempos.
        eventos = defaultdict(list)
        for d in detecciones:
            if getattr(d, "contado", False):
                eventos[(d.canal, d.id_pez)].append(d)

        for (canal, id_pez), items in eventos.items():
            items.sort(
                key=lambda d: (
                    getattr(d, "timestamp_ms", None)
                    if getattr(d, "timestamp_ms", None) is not None
                    else d.cuadro,
                    d.cuadro,
                )
            )
            for anterior, actual in zip(items, items[1:]):
                t_anterior = getattr(anterior, "timestamp_ms", None)
                t_actual = getattr(actual, "timestamp_ms", None)

                if t_anterior is not None and t_actual is not None:
                    delta = t_actual - t_anterior
                    es_duplicado = 0 <= delta <= self.config.ventana_duplicado_ms
                    detalle = {"delta_ms": delta}
                else:
                    delta_cuadros = actual.cuadro - anterior.cuadro
                    es_duplicado = 0 <= delta_cuadros <= self.config.ventana_duplicado_cuadros
                    detalle = {"delta_cuadros": delta_cuadros}

                if es_duplicado:
                    # Evitar duplicar una alerta que ya salió por mismo cuadro.
                    if any(
                        a.tipo == "POSIBLE_DUPLICADO"
                        and a.cuadro == actual.cuadro
                        and a.canal == canal
                        and a.ids_pez == (id_pez,)
                        for a in alertas
                    ):
                        continue
                    alertas.append(
                        Alerta(
                            tipo="POSIBLE_DUPLICADO",
                            cuadro=actual.cuadro,
                            canal=canal,
                            ids_pez=(id_pez,),
                            mensaje=(
                                f"Posible duplicado - cuadro {actual.cuadro + 1} - "
                                f"Tubo {canal} - ID {id_pez}"
                            ),
                            detalles=detalle,
                        )
                    )

        return alertas
