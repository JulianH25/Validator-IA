"""Alertas sobre detecciones de salmones que descienden por dos tubos."""
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
    iou_minimo: float = 0.30
    distancia_centros_max_px: float = 28.0

    # Cambio de ID: un track termina y otro empieza cerca, poco después.
    max_cuadros_cambio_id: int = 15
    max_dx_cambio_id_px: float = 60.0
    max_dy_cambio_id_px: float = 150.0    # hacia abajo (sentido del flujo)
    retroceso_max_px: float = 40.0        # tolerancia hacia arriba

    # Reutilización de ID: el mismo ID aparece de nuevo como si fuera otro pez.
    hueco_reuso_id: int = 30              # hueco (cuadros) que separa dos peces
    hueco_reuso_tras_linea: int = 5       # idem, si el primero ya pasó la línea
    lineas_conteo_y_px: dict[str, float] = field(default_factory=dict)


class MotorAlertas:
    def __init__(self, config=None):
        self.config = config or ConfiguracionAlertas()

    def analizar(self, detecciones):
        detecciones = list(detecciones)
        alertas = []
        alertas.extend(self._detectar_peces_juntos(detecciones))
        alertas.extend(self._detectar_perdidas_seguimiento(detecciones))
        alertas.extend(self._detectar_id_reutilizado(detecciones))
        alertas.extend(self._detectar_aparicion_un_cuadro(detecciones))
        alertas.extend(self._detectar_inicio_bajo_linea(detecciones))
        return sorted(alertas, key=lambda a: (a.cuadro, a.tipo, str(a.canal)))

    # ------------------------------------------------------------ geometría

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
    def _centro(cls, d):
        x1, y1, x2, y2 = cls._bbox(d)
        return (x1 + x2) / 2, (y1 + y2) / 2

    @classmethod
    def _distancia_centros(cls, a, b):
        ax, ay = cls._centro(a)
        bx, by = cls._centro(b)
        return hypot(ax - bx, ay - by)

    # ------------------------------------------------------------ segmentos

    def _segmentos(self, detecciones):
        """Parte cada (canal, id) en tramos continuos: [(canal, id, n, [dets])].

        ByteTrack puede reutilizar un ID para un pez distinto. Un hueco separa
        dos tramos (dos peces) cuando:
          - es largo (más de `hueco_reuso_id` cuadros), o
          - el tramo anterior terminó pasada la línea de conteo y el hueco es
            de `hueco_reuso_tras_linea` cuadros o más (un pez que ya salió no
            puede volver con el mismo ID).
        `n` es el número de tramo dentro del ID (0 = primero).
        """
        cfg = self.config
        por_track = defaultdict(list)
        for d in detecciones:
            por_track[(d.canal, d.id_pez)].append(d)

        segmentos = []
        for (canal, id_pez), dets in por_track.items():
            dets.sort(key=lambda d: d.cuadro)
            y_linea = cfg.lineas_conteo_y_px.get(str(canal))
            actual, n = [dets[0]], 0
            for previa, d in zip(dets, dets[1:]):
                hueco = d.cuadro - previa.cuadro - 1
                tras_linea = (
                    y_linea is not None
                    and self._centro(previa)[1] > y_linea
                    and hueco >= cfg.hueco_reuso_tras_linea
                )
                if hueco > cfg.hueco_reuso_id or tras_linea:
                    segmentos.append((canal, id_pez, n, actual))
                    n += 1
                    actual = []
                actual.append(d)
            segmentos.append((canal, id_pez, n, actual))
        return segmentos

    # ------------------------------------------------------------ alertas

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
        """Cambio de ID: un track termina antes de la línea y otro ID empieza
        cerca, poco después, en el mismo tubo."""
        cfg = self.config
        por_canal = defaultdict(dict)
        for canal, id_pez, n, dets in self._segmentos(detecciones):
            por_canal[canal][(id_pez, n)] = dets

        alertas = []
        for canal, tracks in por_canal.items():
            y_linea = cfg.lineas_conteo_y_px.get(str(canal))
            extremos = {k: (dets[0], dets[-1]) for k, dets in tracks.items()}

            usados = set()
            for k_a, (_, fin_a) in sorted(extremos.items(), key=lambda kv: kv[1][1].cuadro):
                id_a = k_a[0]
                cx_a, cy_a = self._centro(fin_a)
                if y_linea is not None and cy_a > y_linea:
                    continue  # terminó pasada la línea: salida normal

                mejor = None
                for k_b, (ini_b, _) in extremos.items():
                    # Mismo ID: lo cubre ID_REUTILIZADO.
                    if k_b == k_a or k_b in usados or k_b[0] == id_a:
                        continue
                    hueco = ini_b.cuadro - fin_a.cuadro
                    if not 1 <= hueco <= cfg.max_cuadros_cambio_id:
                        continue
                    cx_b, cy_b = self._centro(ini_b)
                    dx, dy = abs(cx_b - cx_a), cy_b - cy_a
                    if (dx > cfg.max_dx_cambio_id_px
                            or dy > cfg.max_dy_cambio_id_px
                            or dy < -cfg.retroceso_max_px):
                        continue
                    costo = (hueco, dx + abs(dy))
                    if mejor is None or costo < mejor[0]:
                        mejor = (costo, k_b, ini_b)

                if mejor is None:
                    continue
                _, k_b, ini_b = mejor
                id_b = k_b[0]
                usados.add(k_b)
                alertas.append(
                    Alerta(
                        tipo="PERDIDA_SEGUIMIENTO",
                        cuadro=ini_b.cuadro,
                        canal=canal,
                        ids_pez=(id_a, id_b),
                        mensaje=(
                            f"Posible cambio de ID - cuadro {ini_b.cuadro + 1} - "
                            f"Tubo {canal} - ID {id_a} → ID {id_b}"
                        ),
                        detalles={
                            "ultimo_cuadro_id_anterior": fin_a.cuadro,
                            "cuadro_id_nuevo": ini_b.cuadro,
                            "cuadros_de_hueco": ini_b.cuadro - fin_a.cuadro,
                        },
                    )
                )
        return alertas

    def _detectar_id_reutilizado(self, detecciones):
        """El mismo ID reaparece como si fuera otro pez."""
        segmentos = {(c, i, n): dets for c, i, n, dets in self._segmentos(detecciones)}
        alertas = []
        for (canal, id_pez, n), dets in segmentos.items():
            if n == 0:
                continue
            previo = segmentos[(canal, id_pez, n - 1)]
            inicio = dets[0].cuadro
            alertas.append(
                Alerta(
                    tipo="ID_REUTILIZADO",
                    cuadro=inicio,
                    canal=canal,
                    ids_pez=(id_pez,),
                    mensaje=(f"ID reutilizado - cuadro {inicio + 1} - "
                             f"Tubo {canal} - ID {id_pez}"),
                    detalles={"fin_pez_anterior": previo[-1].cuadro,
                              "inicio_pez_nuevo": inicio},
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
        """Pez cuya primera aparición (por tramo, no por ID) está bajo la línea."""
        alertas = []
        for canal, id_pez, n, dets in self._segmentos(detecciones):
            y_linea = self.config.lineas_conteo_y_px.get(str(canal))
            if y_linea is None:
                continue
            primer_cuadro = dets[0].cuadro
            primeras = [d for d in dets if d.cuadro == primer_cuadro]
            centro_y = max((d.y1 + d.y2) / 2 for d in primeras)
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
                              "inicio_video": primer_cuadro == 0,
                              "id_reutilizado": n > 0},
                )
            )
        return alertas