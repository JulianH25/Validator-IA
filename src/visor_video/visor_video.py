"""Visor de auditoría de salmones con caída vertical por dos tubos."""

from __future__ import annotations

import math
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from dataclasses import replace
from collections import Counter

import cv2
from PIL import Image, ImageTk

try:
    from .resultados import ErrorResultados, cargar_varios
    from .alertas import MotorAlertas
    from .frames_a_video import ErrorFrames, frames_a_video, listar_frames
    from .canales import ErrorCanales, cargar_canales
    from .correcciones import eventos_desde_resultados
    from .panel_correcciones import PanelCorrecciones
    from .persistencia import ErrorPersistencia, cargar_proyecto, exportar_conteo_json, guardar_proyecto
    from .importar_tracker import ErrorImportacion, convertir as convertir_tracker, necesita_conversion
    from .login import VentanaLogin
    from .database import guardar_correccion, obtener_usuario
    from . import sesion
except ImportError:
    from resultados import ErrorResultados, cargar_varios
    from alertas import MotorAlertas
    from frames_a_video import ErrorFrames, frames_a_video, listar_frames
    from canales import ErrorCanales, cargar_canales
    from correcciones import eventos_desde_resultados
    from panel_correcciones import PanelCorrecciones
    from persistencia import ErrorPersistencia, cargar_proyecto, exportar_conteo_json, guardar_proyecto
    from importar_tracker import ErrorImportacion, convertir as convertir_tracker, necesita_conversion
    from login import VentanaLogin
    from database import guardar_correccion, obtener_usuario
    import sesion


BG = "#181A1F"
PANEL = "#21252B"
PANEL_ALT = "#292E37"
BORDER = "#3A3F4B"
VIDEO_BG = "#111923"
BLUE = "#3B82F6"
GREEN = "#10B981"
RED = "#EF4444"
AMBER = "#F59E0B"
WHITE = "#F3F4F6"
MUTED = "#9CA3AF"
MONO = "Consolas"
UI = "Segoe UI"
TUBOS = ("1", "2")
TODOS = "Todos (T1 + T2)"
FILTROS = {TODOS: None, "Tubo 1": "1", "Tubo 2": "2"}

video = None
cuadro_actual = 0
total_cuadros = 0
resultados = None
etiqueta_a_canal = {}
alertas_detectadas = []
todas_las_alertas = []
motor_alertas = MotorAlertas()

# Canales (recuadro y línea de conteo de cada tubo) que entrega el Tracker.
canales_actuales = {}
ruta_canales_actual = None

ventana = None
visor = None
menu_canal = None
texto_cuadro = None
texto_tiempo = None
texto_conteo = None
texto_alertas = None
texto_video = None
texto_configuracion = None
timeline = None
panel_tarjetas = None
canvas_alertas = None
boton_play = None
estado_visor = None
estado_lineas = None
usuario_actual = None

panel_correcciones = None

ruta_video_actual = None
rutas_json_actuales = ()
canales_json_actuales = {}
ruta_proyecto_actual = None

alerta_seleccionada = None
alertas_revisadas = set()
detalles_tarjetas = []
boton_revisada = None
frames_tarjetas = []
reproduciendo = False
reproduccion_after = None
fps_video = 30.0
ultima_dimension = (0, 0)


def actualizar_desde_correcciones():
    """Refresca la vista después de una corrección de conteo."""
    actualizar_alertas()
    mostrar_cuadro()


def _boton(padre, texto, accion, principal=False, compacto=False):
    bg = BLUE if principal else PANEL_ALT
    hover = "#2563EB" if principal else BORDER
    boton = tk.Button(
        padre, text=texto, command=accion, font=(UI, 9, "bold"),
        bg=bg, fg=WHITE, activebackground=hover, activeforeground=WHITE,
        relief="flat", borderwidth=0, cursor="hand2",
        padx=12 if compacto else 17, pady=8 if compacto else 10,
        highlightthickness=0,
    )
    boton.bind("<Enter>", lambda e: boton.configure(bg=hover))
    boton.bind("<Leave>", lambda e: boton.configure(bg=bg))
    return boton


def _etiqueta(padre, texto, color=WHITE, fuente=None, **kwargs):
    return tk.Label(padre, text=texto, bg=padre.cget("bg"), fg=color,
                    font=fuente or (UI, 10), **kwargs)


def _abrir_video_desde_ruta(ruta):
    global video, cuadro_actual, total_cuadros, fps_video, ruta_video_actual
    nuevo_video = cv2.VideoCapture(str(ruta))
    if not nuevo_video.isOpened():
        return False

    detener_reproduccion()
    if video is not None:
        video.release()
    video = nuevo_video
    ruta_video_actual = str(Path(ruta).resolve())
    total_cuadros = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(video.get(cv2.CAP_PROP_FPS))
    fps_video = fps if math.isfinite(fps) and fps > 0 else 30.0
    cuadro_actual = 0
    if texto_video is not None:
        texto_video.configure(text=f"VIDEO  {os.path.basename(str(ruta))[:31]}", fg=GREEN)
    if estado_visor is not None:
        estado_visor.configure(text="VIDEO CARGADO", fg=GREEN)

    if panel_correcciones is not None and panel_correcciones.registro is not None:
        panel_correcciones.registro.total_cuadros = total_cuadros or None

    if resultados is not None and total_cuadros and resultados.ultimo_cuadro >= total_cuadros:
        messagebox.showwarning(
            "Revisa los archivos",
            f"Los resultados llegan al cuadro {resultados.ultimo_cuadro + 1}, "
            f"pero el video tiene {total_cuadros} cuadros. ¿Son del mismo video?",
        )
    mostrar_cuadro()
    _dibujar_timeline()
    return True


def _cargar_video_desde_frames():
    ruta_img = filedialog.askopenfilename(
        title="Elige cualquier frame de la carpeta",
        filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp"), ("Todos", "*.*")],
    )
    if not ruta_img:
        return
    carpeta = str(Path(ruta_img).parent)
    
    try:
        n = len(listar_frames(carpeta))
    except ErrorFrames as exc:
        messagebox.showerror("Carpeta de frames", str(exc))
        return

    fps = simpledialog.askfloat(
        "Cuadros por segundo",
        f"Se encontraron {n} frames.\n¿A cuántos cuadros por segundo se grabó? (ej. 50)",
        initialvalue=50.0, minvalue=1.0, maxvalue=240.0, parent=ventana,
    )
    if fps is None:
        return

    base = Path(carpeta)
    destino = base.parent / f"{base.name}.mp4"
    if destino.exists():
        respuesta = messagebox.askyesnocancel(
            "Video existente",
            f"Ya existe «{destino.name}».\n\n"
            "Sí  =  usarlo\nNo  =  crearlo de nuevo\nCancelar  =  salir",
        )
        if respuesta is None:
            return
        if respuesta:
            if not _abrir_video_desde_ruta(destino):
                messagebox.showerror("No se pudo abrir", "No fue posible abrir el video.")
            return

    espera = tk.Toplevel(ventana)
    espera.title("Creando video")
    espera.configure(bg=PANEL, padx=20, pady=16)
    espera.resizable(False, False)
    espera.transient(ventana)
    _etiqueta(espera, f"Creando video con {n} frames…", WHITE).pack(anchor="w")
    barra = ttk.Progressbar(espera, length=320, maximum=n)
    barra.pack(pady=(10, 0))
    espera.update()
    espera.grab_set()

    def progreso(hecho, total):
        barra["value"] = hecho
        espera.update()

    try:
        info = frames_a_video(carpeta, destino, fps, progreso)
    except (ErrorFrames, OSError) as exc:
        espera.destroy()
        messagebox.showerror("No se pudo crear el video", str(exc))
        return
    espera.destroy()

    if info["faltantes"]:
        ejemplos = ", ".join(str(x) for x in info["primeros_faltantes"][:5])
        messagebox.showwarning(
            "Faltan frames en la numeración",
            f"Faltan {info['faltantes']} números en la carpeta (por ejemplo: {ejemplos}).\n\n"
            "El video los omite, así que desde ese punto el cuadro del video ya no "
            "coincide con el número del archivo. Confirma con quien hizo el tracker "
            "qué numeración usó.",
        )

    if not _abrir_video_desde_ruta(destino):
        messagebox.showerror("No se pudo abrir", "No fue posible abrir el video creado.")


def cargar_video():
    eleccion = messagebox.askyesnocancel(
        "Cargar video",
        "¿Qué quieres cargar?\n\n"
        "Sí  =  archivo de video (.mp4)\n"
        "No  =  carpeta de frames (se convierte a video)\n"
        "Cancelar  =  salir",
    )
    if eleccion is None:
        return
    if not eleccion:
        _cargar_video_desde_frames()
        return

    ruta = filedialog.askopenfilename(
        filetypes=[("Video MP4", "*.mp4"), ("Todos", "*.*")]
    )
    if not ruta:
        return
    if not _abrir_video_desde_ruta(ruta):
        messagebox.showerror("No se pudo abrir", "No fue posible abrir el video seleccionado.")


def _canales_no_admitidos(canales):
    """Identifica valores que no son Tubo 1 ni Tubo 2, sin perder datos."""
    return [str(canal) for canal in canales if str(canal) not in TUBOS]


def _preguntar_tubo(ruta):
    """Se usa cuando un archivo no trae canal ni lo dice el nombre."""
    respuesta = messagebox.askyesnocancel(
        "¿De qué tubo es este archivo?",
        f"«{os.path.basename(ruta)}» no indica el tubo.\n\n"
        "Sí  =  Tubo 1\nNo  =  Tubo 2\nCancelar  =  no cargar",
    )
    if respuesta is None:
        return None
    return "1" if respuesta else "2"


def _cargar_resultados_desde_rutas(rutas, canales_guardados=None, registro_restaurado=None,
                                   revisadas=None):
    global resultados, etiqueta_a_canal, rutas_json_actuales, canales_json_actuales
    rutas = tuple(str(Path(r).resolve()) for r in rutas)
    guardados = {str(Path(k).resolve()): str(v) for k, v in (canales_guardados or {}).items()}
    resueltos = {}

    def resolver(ruta):
        clave = str(Path(ruta).resolve())
        if clave in guardados:
            return guardados[clave]
        canal = _preguntar_tubo(ruta)
        if canal is not None:
            resueltos[clave] = canal
        return canal

    try:
        nuevos = cargar_varios(rutas, resolver_canal=resolver)
    except (ErrorResultados, OSError) as exc:
        messagebox.showerror("No se pudieron cargar los resultados", str(exc))
        return False

    no_admitidos = _canales_no_admitidos(nuevos.canales)
    if no_admitidos:
        messagebox.showerror(
            "Configuración incompatible",
            "Este visor está configurado únicamente para Tubo 1 y Tubo 2.\n"
            "Canales encontrados fuera de ese rango: " + ", ".join(no_admitidos) + ".\n"
            "Revisa el JSON o consulta con el responsable de los datos del tracker.",
        )
        return False

    resultados = nuevos
    rutas_json_actuales = rutas
    canales_json_actuales = dict(guardados)
    canales_json_actuales.update(resueltos)
    etiqueta_a_canal = {nombre: canal for nombre, canal in FILTROS.items() if canal is not None}
    menu_canal.configure(values=list(FILTROS), state="readonly")
    menu_canal.set(TODOS)
    if texto_configuracion is not None:
        nombre = os.path.basename(rutas[0]) if len(rutas) == 1 else f"{len(rutas)} archivos"
        texto_configuracion.configure(text=f"DATOS  {nombre[:31]}", fg=GREEN)

    if total_cuadros and resultados.ultimo_cuadro >= total_cuadros:
        messagebox.showwarning(
            "Revisa los archivos",
            f"Los resultados llegan al cuadro {resultados.ultimo_cuadro + 1}, "
            f"pero el video tiene {total_cuadros} cuadros. ¿Son del mismo video?",
        )

    if panel_correcciones is not None:
        if registro_restaurado is None:
            panel_correcciones.cargar(eventos_desde_resultados(nuevos))
        else:
            registro_restaurado.total_cuadros = total_cuadros or registro_restaurado.total_cuadros
            panel_correcciones.cargar_registro(registro_restaurado)
    alertas_revisadas.clear()
    alertas_revisadas.update(revisadas or ())
    actualizar_alertas()
    mostrar_cuadro()
    return True


def cargar_resultados():
    rutas = filedialog.askopenfilenames(
        title="Selecciona los archivos del tracker (CSV + JSON) o un JSON de formato común",
        filetypes=[("Archivos del tracker", "*.json *.csv"), ("JSON", "*.json"), ("CSV", "*.csv")],
    )
    if not rutas:
        return
    if necesita_conversion(rutas):
        try:
            convertido = convertir_tracker(rutas)
        except ErrorImportacion as exc:
            messagebox.showerror("No se pudo importar el tracker", str(exc))
            return
        rutas = (str(convertido),)
    if len(rutas) == 1:
        try:
            datos = json.loads(Path(rutas[0]).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            messagebox.showerror("Configuración inválida", str(exc))
            return
        if isinstance(datos, dict) and "canales" in datos and not any(
            k in datos for k in ("detecciones", "resultados")
        ):
            _cargar_canales_desde_ruta(rutas[0])
            return
    if _cargar_resultados_desde_rutas(rutas):
        for ruta in rutas:
            try:
                datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if isinstance(datos, dict) and "canales" in datos:
                _cargar_canales_desde_ruta(ruta)
                break


# ---------------------------------------------------------------- canales

def _aplicar_canales():
    """La línea de conteo de cada tubo sale de los canales que entrega el Tracker."""
    motor_alertas.config.lineas_conteo_y_px = {
        c: ch.linea_y for c, ch in canales_actuales.items()
    }
    _actualizar_estado_lineas()


def _cargar_canales_desde_ruta(ruta):
    global canales_actuales, ruta_canales_actual
    try:
        nuevos = cargar_canales(ruta)
    except ErrorCanales as exc:
        messagebox.showerror("No se pudieron cargar los canales", str(exc))
        return False
    ajenos = [c for c in nuevos if c not in TUBOS]
    if ajenos:
        messagebox.showerror(
            "Canales incompatibles",
            "Este visor solo admite Tubo 1 y Tubo 2. Canales encontrados: "
            + ", ".join(ajenos) + ".",
        )
        return False
    canales_actuales = nuevos
    ruta_canales_actual = str(Path(ruta).resolve())
    _aplicar_canales()
    actualizar_alertas()
    mostrar_cuadro()
    return True


def _actualizar_estado_lineas():
    if estado_lineas is None:
        return
    lineas = motor_alertas.config.lineas_conteo_y_px
    if not lineas:
        estado_lineas.configure(
            text="SIN CANALES DEL TRACKER · alerta de línea desactivada", fg=AMBER)
        return
    sin_linea = [t for t in TUBOS if t not in lineas]
    texto = ("CANALES SIN DEFINIR: " + ", ".join("T" + t for t in sin_linea)
             if sin_linea else "LÍNEAS DEL TRACKER: " + ", ".join(
                 f"T{t} y={lineas[t]:g}" for t in TUBOS))
    estado_lineas.configure(text=texto, fg=AMBER if sin_linea else GREEN)


def _dibujar_canales(cuadro):
    """Recuadro de cada tubo y su línea de conteo, tal como los define el Tracker."""
    activo = canal_elegido()
    for id_canal, ch in canales_actuales.items():
        if activo is not None and id_canal != activo:
            continue
        cv2.rectangle(cuadro, (int(ch.x1), int(ch.y1)), (int(ch.x2), int(ch.y2)),
                      (230, 200, 60), 1)
        y = int(ch.linea_y)
        cv2.line(cuadro, (int(ch.x1), y), (int(ch.x2), y), (0, 215, 255), 2)
        cv2.putText(cuadro, f"T{id_canal}", (int(ch.x1) + 4, int(ch.y1) + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 200, 60), 1, cv2.LINE_AA)
    return cuadro


# ---------------------------------------------------------------- proyecto

def guardar_proyecto_actual():
    global ruta_proyecto_actual
    if panel_correcciones is None or panel_correcciones.registro is None:
        messagebox.showinfo("Sin proyecto", "Carga los resultados antes de guardar el proyecto.")
        return

    ruta = ruta_proyecto_actual
    if not ruta:
        ruta = filedialog.asksaveasfilename(
            defaultextension=".validator.json",
            filetypes=[("Proyecto Validator", "*.validator.json"), ("JSON", "*.json")],
            initialfile="proyecto.validator.json",
        )
    if not ruta:
        return
    try:
        guardar_proyecto(
            ruta,
            panel_correcciones.registro,
            video=ruta_video_actual,
            archivos_json=rutas_json_actuales,
            canales_json=canales_json_actuales,
            cuadro=cuadro_actual,
            filtro=menu_canal.get() if menu_canal is not None else TODOS,
            lineas_conteo=motor_alertas.config.lineas_conteo_y_px,
            canales_archivo=ruta_canales_actual,
            alertas_revisadas=sorted(alertas_revisadas),
        )
    except ErrorPersistencia as exc:
        messagebox.showerror("No se pudo guardar", str(exc))
        return
    ruta_proyecto_actual = str(Path(ruta).resolve())
    messagebox.showinfo("Proyecto guardado", "Las correcciones y el historial quedaron guardados.")

def exportar_conteo():
    if panel_correcciones is None or panel_correcciones.registro is None:
        messagebox.showinfo("Sin resultados", "Carga los resultados antes de exportar el conteo.")
        return
    registro = panel_correcciones.registro
    ruta = filedialog.asksaveasfilename(
        defaultextension=".json",
        filetypes=[("JSON", "*.json")],
        initialfile="conteo_final.json",
    )
    if not ruta:
        return
    try:
        exportar_conteo_json(ruta, registro, fps=fps_video)
    except ErrorPersistencia as exc:
        messagebox.showerror("No se pudo exportar", str(exc))
        return
    conteos = registro.conteos()
    detalle = "\n".join(f"Tubo {c}: {n}" for c, n in conteos.items())
    messagebox.showinfo("Conteo exportado", f"{detalle}\nTotal: {registro.total}")

def abrir_proyecto_guardado():
    global resultados, etiqueta_a_canal, alerta_seleccionada, ruta_proyecto_actual
    global canales_actuales, ruta_canales_actual
    ruta = filedialog.askopenfilename(
        filetypes=[("Proyecto Validator", "*.validator.json"), ("JSON", "*.json")]
    )
    if not ruta:
        return
    try:
        proyecto = cargar_proyecto(ruta)
    except ErrorPersistencia as exc:
        messagebox.showerror("No se pudo abrir", str(exc))
        return

    faltantes = []
    if proyecto.video and not Path(proyecto.video).exists():
        faltantes.append(proyecto.video)
    faltantes.extend(r for r in proyecto.archivos_json if not Path(r).exists())
    if faltantes:
        messagebox.showerror(
            "Faltan archivos",
            "No se puede reabrir el proyecto porque faltan archivos de origen:\n\n"
            + "\n".join(faltantes[:5]),
        )
        return

    resultados = None
    etiqueta_a_canal = {}
    alerta_seleccionada = None
    alertas_revisadas.clear()
    alertas_revisadas.update(proyecto.alertas_revisadas)
    canales_actuales = {}
    ruta_canales_actual = None
    if panel_correcciones is not None:
        panel_correcciones.limpiar()

    if proyecto.video and not _abrir_video_desde_ruta(proyecto.video):
        messagebox.showerror("No se pudo abrir", "No fue posible abrir el video del proyecto.")
        return
    if proyecto.archivos_json and not _cargar_resultados_desde_rutas(
        proyecto.archivos_json, proyecto.canales_json, proyecto.registro,
        revisadas=proyecto.alertas_revisadas,
    ):
        return
    if not proyecto.archivos_json and panel_correcciones is not None:
        panel_correcciones.cargar_registro(proyecto.registro)

    if proyecto.canales_archivo and Path(proyecto.canales_archivo).exists():
        _cargar_canales_desde_ruta(proyecto.canales_archivo)
    else:
        # Proyecto sin archivo de canales (o el archivo ya no está): se usan
        # las líneas que quedaron guardadas en el proyecto.
        motor_alertas.config.lineas_conteo_y_px = dict(proyecto.lineas_conteo)
        _actualizar_estado_lineas()
        actualizar_alertas()

    if menu_canal is not None and proyecto.filtro in FILTROS:
        menu_canal.set(proyecto.filtro)
    if panel_correcciones is not None:
        panel_correcciones.refrescar()
    if video is not None and total_cuadros > 0:
        ir_a_frame(min(proyecto.cuadro, total_cuadros - 1))
    ruta_proyecto_actual = str(Path(ruta).resolve())


# ---------------------------------------------------------------- alertas

def _detecciones_con_correcciones():
    """Detecciones para el motor de alertas, según el estado actual de las correcciones.

    Una detección queda como contada si hay un evento de conteo vigente para su
    (canal, cuadro, id_pez). No modifica resultados.detecciones.
    Los conteos manuales no tienen id de pez, así que no generan alertas de duplicado.
    """
    if resultados is None:
        return []

    registro = panel_correcciones.registro if panel_correcciones is not None else None
    if registro is None:
        return list(resultados.detecciones)

    activos = Counter(
        (str(e.canal), int(e.cuadro), str(e.id_pez))
        for e in registro.eventos()
        if e.id_pez is not None
    )

    detecciones = []
    for d in resultados.detecciones:
        clave = (str(d.canal), int(d.cuadro), str(d.id_pez))
        if activos[clave] > 0:
            activos[clave] -= 1
            detecciones.append(d if d.contado else replace(d, contado=True))
        else:
            detecciones.append(replace(d, contado=False) if d.contado else d)
    return detecciones


def _filtrar_alertas():
    """Muestra solo las alertas del tubo elegido (o todas con «Todos»)."""
    global alertas_detectadas, alerta_seleccionada
    canal = canal_elegido()
    alertas_detectadas = [
        a for a in todas_las_alertas if canal is None or str(a.canal) == canal
    ]
    alerta_seleccionada = None
    _actualizar_contador_alertas()
    _construir_tarjetas()
    _actualizar_boton_revisada()
    _dibujar_timeline()


def _clave_alerta(alerta):
    return f"{alerta.tipo}|{alerta.canal}|{alerta.cuadro}|{','.join(alerta.ids_pez)}"


def _esta_revisada(alerta):
    return _clave_alerta(alerta) in alertas_revisadas


def _actualizar_contador_alertas():
    if texto_alertas is None:
        return
    total = len(alertas_detectadas)
    revisadas = sum(1 for a in alertas_detectadas if _esta_revisada(a))
    texto = f"{total} ALERTA{'S' if total != 1 else ''}"
    if revisadas:
        texto += f" · {revisadas} REVISADA{'S' if revisadas != 1 else ''}"
    texto_alertas.configure(text=texto)


def _actualizar_boton_revisada():
    if boton_revisada is None:
        return
    elegida = (alerta_seleccionada is not None
               and 0 <= alerta_seleccionada < len(alertas_detectadas)
               and _esta_revisada(alertas_detectadas[alerta_seleccionada]))
    boton_revisada.configure(text="↺  Quitar  R" if elegida else "✓  Revisada  R")


def _aplicar_estado_tarjeta(indice):
    if not 0 <= indice < min(len(detalles_tarjetas), len(alertas_detectadas)):
        return
    punto, titulo, marca = detalles_tarjetas[indice]
    alerta = alertas_detectadas[indice]
    revisada = _esta_revisada(alerta)
    punto.configure(fg=GREEN if revisada else _color_alerta(alerta))
    titulo.configure(fg=MUTED if revisada else WHITE)
    marca.configure(text="✓ REVISADA" if revisada else "")


def _registrar_revision(alerta):
    if sesion.usuario_id is None:
        return
    try:
        guardar_correccion(
            usuario_id=sesion.usuario_id,
            tipo_correccion="ALERTA_REVISADA",
            canal=str(alerta.canal),
            cuadro=alerta.cuadro,
            id_pez=",".join(alerta.ids_pez) or None,
        )
    except Exception as exc:
        messagebox.showwarning(
            "Historial",
            f"La alerta se marcó, pero no se pudo guardar en el historial local.\n\n{exc}",
        )


def alternar_revisada(evento=None):
    """Marca o desmarca como revisada la alerta seleccionada."""
    if alerta_seleccionada is None or not 0 <= alerta_seleccionada < len(alertas_detectadas):
        messagebox.showinfo("Selecciona una alerta", "Elige una alerta de la lista primero.")
        return
    alerta = alertas_detectadas[alerta_seleccionada]
    clave = _clave_alerta(alerta)
    if clave in alertas_revisadas:
        alertas_revisadas.discard(clave)
    else:
        alertas_revisadas.add(clave)
        _registrar_revision(alerta)
    _aplicar_estado_tarjeta(alerta_seleccionada)
    _actualizar_contador_alertas()
    _actualizar_boton_revisada()
    _dibujar_timeline()


def actualizar_alertas():
    """Calcula las alertas con las correcciones actuales y aplica el filtro de tubo."""
    global todas_las_alertas
    todas_las_alertas = (
        motor_alertas.analizar(_detecciones_con_correcciones())
        if resultados is not None
        else []
    )
    _filtrar_alertas()


def ir_a_frame(cuadro):
    """Navega a un índice de cuadro interno base 0 (se muestra base 1)."""
    global cuadro_actual
    if video is None:
        messagebox.showinfo("Carga un video", "Carga el video correspondiente para ir a una alerta.")
        return
    if total_cuadros <= 0:
        return
    cuadro_actual = max(0, min(int(cuadro), total_cuadros - 1))
    mostrar_cuadro()


def ir_a_alerta(evento=None):
    if alerta_seleccionada is not None and alerta_seleccionada < len(alertas_detectadas):
        ir_a_frame(alertas_detectadas[alerta_seleccionada].cuadro)


def canal_elegido():
    return etiqueta_a_canal.get(menu_canal.get()) if menu_canal is not None else None


def al_cambiar_canal(evento=None):
    if panel_correcciones is not None:
        panel_correcciones.refrescar(notificar=False)
    _filtrar_alertas()
    mostrar_cuadro()


def _color_alerta(alerta):
    return {
        "PECES_JUNTOS": RED,
        "PERDIDA_SEGUIMIENTO": AMBER,
        "APARICION_UN_CUADRO": AMBER,
        "INICIO_BAJO_LINEA": RED,
        "ID_REUTILIZADO": RED,
    }.get(alerta.tipo, RED)


def _titulo_alerta(alerta):
    return {
        "PECES_JUNTOS": "Peces muy juntos",
        "PERDIDA_SEGUIMIENTO": "Pérdida de seguimiento",
        "APARICION_UN_CUADRO": "ID en un solo frame",
        "INICIO_BAJO_LINEA": "Aparición bajo la línea",
        "ID_REUTILIZADO": "ID reutilizado",
    }.get(alerta.tipo, alerta.tipo.replace("_", " ").title())


def _dibujar_telemetria(cuadro, detecciones):
    """Cajas verdes para detecciones y rojas para IDs involucrados en alertas."""
    presentes = [a for a in alertas_detectadas if a.cuadro == cuadro_actual]
    ids_en_alerta = {(a.canal, identificador) for a in presentes for identificador in a.ids_pez}
    alto, ancho = cuadro.shape[:2]
    grosor = max(2, ancho // 450)
    escala = max(0.53, min(0.95, ancho / 1250))
    bgr_verde = (129, 185, 16)
    bgr_rojo = (68, 68, 239)
    bgr_blanco = (246, 244, 243)
    etiquetas_ocupadas = []
    for d in detecciones:
        es_alerta = (d.canal, d.id_pez) in ids_en_alerta
        color = bgr_rojo if es_alerta else bgr_verde
        cv2.rectangle(cuadro, (d.x1, d.y1), (d.x2, d.y2), color, grosor)
        texto = f"ID:{d.id_pez}" + ("  ! ALERTA" if es_alerta else "")
        (tw, th), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, escala, 1)
        y = min(max(d.y1 - 7, th + 8), max(th + 8, alto - 5))
        x = max(0, min(d.x1, ancho - tw - 10))
        # Evitar etiquetas superpuestas.
        candidatos = [y, d.y2 + th + 10, d.y1 - th - 21]
        for alternativa in candidatos:
            y2 = int(alternativa)
            rectangulo = (x, y2 - th - 7, x + tw + 9, y2 + 3)
            if rectangulo[1] < 0 or rectangulo[3] >= alto:
                continue
            if not any(not (rectangulo[2] < ocupado[0] or
                            rectangulo[0] > ocupado[2] or
                            rectangulo[3] < ocupado[1] or
                            rectangulo[1] > ocupado[3])
                       for ocupado in etiquetas_ocupadas):
                y = y2
                break
        rectangulo = (x, y - th - 7, x + tw + 9, y + 3)
        etiquetas_ocupadas.append(rectangulo)
        cv2.rectangle(cuadro, (x, y - th - 7), (x + tw + 9, y + 3), color, -1)
        cv2.putText(cuadro, texto, (x + 4, y - 2), cv2.FONT_HERSHEY_SIMPLEX,
                    escala, bgr_blanco, 1, cv2.LINE_AA)
    return cuadro


def _formatear_tiempo(cuadro):
    segundos = max(0.0, cuadro / fps_video)
    minutos = int(segundos // 60)
    return f"{minutos:02d}:{segundos % 60:05.2f}"


def _conteo_hasta_frame(cuadro):
    """Calcula el conteo acumulado hasta el cuadro actual.

    Usa el RegistroCorrecciones para que el contador de la pantalla
    refleje también altas, bajas y movimientos hechos por el usuario.
    """
    conteos = {canal: 0 for canal in TUBOS}
    if panel_correcciones is None or panel_correcciones.registro is None:
        return conteos

    registro = panel_correcciones.registro
    for evento in registro.eventos():
        if evento.cuadro <= cuadro and evento.canal in conteos:
            conteos[evento.canal] += 1
    return conteos


def _actualizar_contador():
    if texto_conteo is None:
        return

    conteos = _conteo_hasta_frame(cuadro_actual)
    total = sum(conteos.values())
    texto_conteo.configure(
        text=f"T1  {conteos["1"]:02d}   ·   T2  {conteos["2"]:02d}   ·   TOTAL  {total:02d}"
    )


def mostrar_cuadro():
    if video is None or visor is None:
        return
    video.set(cv2.CAP_PROP_POS_FRAMES, cuadro_actual)
    correcto, imagen_bgr = video.read()
    if not correcto:
        return

    if canales_actuales:
        imagen_bgr = _dibujar_canales(imagen_bgr)

    if resultados is not None:
        detecciones = resultados.en_cuadro(cuadro_actual, canal_elegido())
        imagen_bgr = _dibujar_telemetria(imagen_bgr, detecciones)

    imagen_rgb = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2RGB)
    imagen = Image.fromarray(imagen_rgb)
    ancho = max(300, visor.winfo_width() - 24)
    alto = max(220, visor.winfo_height() - 24)
    imagen.thumbnail((ancho, alto), Image.Resampling.LANCZOS)
    fotograma = ImageTk.PhotoImage(imagen)
    visor.configure(image=fotograma, text="")
    visor.image = fotograma

    if texto_cuadro is not None:
        texto_cuadro.configure(text=f"FRAME  {cuadro_actual + 1:,} / {total_cuadros:,}")
    if texto_tiempo is not None:
        texto_tiempo.configure(text=f"{_formatear_tiempo(cuadro_actual)} s")
    _actualizar_contador()
    _dibujar_timeline()
    _resaltar_tarjetas()


def _en_redimensionar_video(evento):
    global ultima_dimension
    dimension = (evento.width, evento.height)
    if dimension != ultima_dimension:
        ultima_dimension = dimension
        if video is not None:
            mostrar_cuadro()


def siguiente_cuadro():
    if video is not None and cuadro_actual < total_cuadros - 1:
        ir_a_frame(cuadro_actual + 1)


def anterior_cuadro():
    if video is not None and cuadro_actual > 0:
        ir_a_frame(cuadro_actual - 1)


def _primero():
    if video is not None:
        ir_a_frame(0)


def _siguiente_alerta():
    if not alertas_detectadas:
        return
    for indice, alerta in enumerate(alertas_detectadas):
        if alerta.cuadro > cuadro_actual:
            _seleccionar_alerta(indice, saltar=True)
            return
    _seleccionar_alerta(0, saltar=True)


def _paso_reproduccion():
    global reproduccion_after
    reproduccion_after = None
    if not reproduciendo:
        return
    if cuadro_actual >= total_cuadros - 1:
        detener_reproduccion()
        return
    siguiente_cuadro()
    reproduccion_after = ventana.after(max(10, int(1000 / fps_video)), _paso_reproduccion)


def detener_reproduccion():
    global reproduciendo, reproduccion_after
    reproduciendo = False
    if reproduccion_after is not None and ventana is not None:
        try:
            ventana.after_cancel(reproduccion_after)
        except tk.TclError:
            pass
        reproduccion_after = None
    if boton_play is not None:
        boton_play.configure(text="▶  Reproducir   SPACE")


def alternar_reproduccion():
    global reproduciendo
    if video is None or total_cuadros <= 0:
        return
    if reproduciendo:
        detener_reproduccion()
    else:
        if cuadro_actual >= total_cuadros - 1:
            ir_a_frame(0)
        reproduciendo = True
        if boton_play is not None:
            boton_play.configure(text="❚❚  Pausar   SPACE")
        _paso_reproduccion()


def _dibujar_timeline(evento=None):
    if timeline is None:
        return
    timeline.delete("all")
    ancho = max(10, timeline.winfo_width())
    alto = max(10, timeline.winfo_height())
    izquierda, derecha = 12, ancho - 12
    y = alto // 2
    timeline.create_line(izquierda, y, derecha, y, fill=BORDER, width=6, capstyle="round")
    if total_cuadros < 2:
        timeline.create_oval(izquierda-6, y-6, izquierda+6, y+6,
                             fill=MUTED, outline="")
        return
    factor = (derecha - izquierda) / (total_cuadros - 1)
    for alerta in alertas_detectadas:
        if 0 <= alerta.cuadro < total_cuadros:
            x = izquierda + alerta.cuadro * factor
            timeline.create_line(x, y-12, x, y+12,
                                 fill=GREEN if _esta_revisada(alerta) else RED, width=2)
    x_actual = izquierda + cuadro_actual * factor
    timeline.create_line(izquierda, y, x_actual, y, fill=BLUE, width=6)
    timeline.create_oval(x_actual-7, y-7, x_actual+7, y+7,
                         fill=WHITE, outline=BLUE, width=2)


def _seleccionar_en_timeline(evento):
    if video is None or total_cuadros <= 1:
        return
    margen = 12
    ancho = max(1, timeline.winfo_width() - 2 * margen)
    fraccion = max(0, min(1, (evento.x - margen) / ancho))
    ir_a_frame(round(fraccion * (total_cuadros - 1)))


def _limpiar_tarjetas():
    global frames_tarjetas, detalles_tarjetas
    if panel_tarjetas is not None:
        for hijo in panel_tarjetas.winfo_children():
            hijo.destroy()
    frames_tarjetas = []
    detalles_tarjetas = []


def _seleccionar_alerta(indice, saltar=False):
    global alerta_seleccionada
    if not 0 <= indice < len(alertas_detectadas):
        return
    alerta_seleccionada = indice
    _resaltar_tarjetas()
    _actualizar_boton_revisada()
    if saltar:
        detener_reproduccion()
        ir_a_frame(alertas_detectadas[indice].cuadro)


def _construir_tarjetas():
    if panel_tarjetas is None:
        return
    _limpiar_tarjetas()
    if not alertas_detectadas:
        vacio = tk.Frame(panel_tarjetas, bg=PANEL)
        vacio.pack(fill="both", expand=True, pady=45, padx=14)
        _etiqueta(vacio, "SIN ANOMALÍAS", MUTED, (UI, 11, "bold")).pack(pady=(8, 8))
        if resultados is None:
            texto = "Carga una configuración JSON para analizar los resultados."
        elif not motor_alertas.config.lineas_conteo_y_px:
            texto = ("No se detectaron anomalías. Sin canales del Tracker: "
                     "la alerta de línea está desactivada.")
        else:
            texto = "No se detectaron anomalías con los criterios actuales."
        _etiqueta(vacio, texto, MUTED, (UI, 9), wraplength=280,
                  justify="center").pack()
        return

    for indice, alerta in enumerate(alertas_detectadas):
        borde = tk.Frame(panel_tarjetas, bg=BORDER, padx=1, pady=1)
        borde.pack(fill="x", padx=(8, 12), pady=(0, 9))
        tarjeta = tk.Frame(borde, bg=PANEL_ALT, cursor="hand2", padx=11, pady=11)
        tarjeta.pack(fill="both")
        encabezado = tk.Frame(tarjeta, bg=PANEL_ALT)
        encabezado.pack(fill="x")
        n_frame = _etiqueta(encabezado, f"FRAME {alerta.cuadro + 1:05d}", WHITE,
                            (MONO, 10, "bold"))
        n_frame.pack(side="left")
        tk.Label(encabezado, text=f"TUBO {alerta.canal}", bg=PANEL_ALT,
                 fg=MUTED, font=(MONO, 9)).pack(side="right")
        segunda = tk.Frame(tarjeta, bg=PANEL_ALT)
        segunda.pack(fill="x", pady=(7, 0))
        punto = tk.Label(segunda, text="●", bg=PANEL_ALT, fg=_color_alerta(alerta),
                         font=(UI, 12))
        punto.pack(side="left")
        titulo = _etiqueta(segunda, _titulo_alerta(alerta), WHITE, (UI, 10, "bold"))
        titulo.pack(side="left", padx=(5, 0))
        marca = tk.Label(segunda, text="", bg=PANEL_ALT, fg=GREEN, font=(MONO, 8, "bold"))
        marca.pack(side="right")
        ids = ", ".join(alerta.ids_pez) if alerta.ids_pez else "—"
        _etiqueta(tarjeta, f"ID: {ids}", MUTED, (MONO, 9), anchor="w").pack(fill="x", pady=(4, 0))
        saltar = _etiqueta(tarjeta, "CLICK PARA SALTAR  ›", AMBER,
                           (UI, 8, "bold"), anchor="w")
        saltar.pack(fill="x", pady=(8, 0))
        for elemento in (borde, tarjeta, encabezado, segunda, n_frame, titulo, saltar):
            elemento.bind("<Button-1>", lambda e, i=indice: _seleccionar_alerta(i, True))
            elemento.bind("<MouseWheel>", _al_mousewheel)
        for hijo in list(segunda.winfo_children()) + list(encabezado.winfo_children()):
            hijo.bind("<Button-1>", lambda e, i=indice: _seleccionar_alerta(i, True))
            hijo.bind("<MouseWheel>", _al_mousewheel)
        frames_tarjetas.append((borde, tarjeta, alerta))
        detalles_tarjetas.append((punto, titulo, marca))
        _aplicar_estado_tarjeta(indice)
    _resaltar_tarjetas()


def _resaltar_tarjetas():
    for indice, (borde, tarjeta, alerta) in enumerate(frames_tarjetas):
        activo = (alerta.cuadro == cuadro_actual)
        elegido = indice == alerta_seleccionada
        borde.configure(bg=RED if activo else AMBER if elegido else BORDER)
        fondo = "#374151" if activo or elegido else PANEL_ALT
        tarjeta.configure(bg=fondo)
        for hijo in tarjeta.winfo_children():
            _cambiar_fondo(hijo, PANEL_ALT, fondo)


def _cambiar_fondo(widget, anterior, nuevo):
    try:
        if widget.cget("bg") in (anterior, "#374151"):
            widget.configure(bg=nuevo)
    except tk.TclError:
        pass
    for hijo in widget.winfo_children():
        _cambiar_fondo(hijo, anterior, nuevo)


def _al_mousewheel(evento):
    if canvas_alertas is None:
        return
    if evento.num == 4:
        canvas_alertas.yview_scroll(-2, "units")
    elif evento.num == 5:
        canvas_alertas.yview_scroll(2, "units")
    else:
        canvas_alertas.yview_scroll(-int(evento.delta / 120) * 3, "units")


def _tecla(evento):
    if isinstance(evento.widget, (tk.Entry, ttk.Combobox)):
        return
    tecla = evento.keysym.lower()
    if tecla == "space":
        alternar_reproduccion()
    elif tecla == "a":
        anterior_cuadro()
    elif tecla == "d":
        siguiente_cuadro()
    elif tecla == "r":
        alternar_revisada()


def _cerrar():
    detener_reproduccion()
    if video is not None:
        video.release()
    ventana.destroy()


def main(nombre_usuario=None):
    global ventana, visor, texto_cuadro, texto_tiempo, texto_conteo, texto_alertas
    global menu_canal, texto_video, texto_configuracion, timeline, boton_play
    global panel_tarjetas, canvas_alertas, estado_visor, estado_lineas
    global panel_correcciones, usuario_actual, boton_revisada

    usuario_actual = nombre_usuario

    ventana = tk.Tk()
    ventana.title("Visor de Auditoría - Tracker Salmones")
    ventana.geometry("1440x810")
    ventana.minsize(1050, 620)
    ventana.configure(bg=BG)

    estilo = ttk.Style(ventana)
    estilo.theme_use("clam")
    estilo.configure("Audit.TCombobox", padding=7, fieldbackground=PANEL_ALT,
                     background=PANEL_ALT, foreground=WHITE,
                     arrowcolor=BLUE, bordercolor=BLUE, lightcolor=BLUE,
                     darkcolor=BLUE, font=(UI, 10))
    estilo.map("Audit.TCombobox", fieldbackground=[("readonly", PANEL_ALT)],
               foreground=[("readonly", WHITE)], selectbackground=[("readonly", PANEL_ALT)],
               selectforeground=[("readonly", WHITE)])
    ventana.option_add("*TCombobox*Listbox.background", PANEL_ALT)
    ventana.option_add("*TCombobox*Listbox.foreground", WHITE)
    ventana.option_add("*TCombobox*Listbox.selectBackground", BLUE)

    barra = tk.Frame(ventana, bg=PANEL, height=71, highlightbackground=BORDER,
                     highlightthickness=1)
    barra.pack(fill="x", side="top")
    barra.pack_propagate(False)
    titulos = tk.Frame(barra, bg=PANEL)
    titulos.pack(side="left", fill="y", padx=(20, 12), pady=10)
    _etiqueta(titulos, "◈  VISOR DE AUDITORÍA", WHITE,
              (UI, 14, "bold")).pack(anchor="w")
    _etiqueta(titulos, "TRACKER SALMONES  /  2 TUBOS", MUTED,
              (UI, 8, "bold")).pack(anchor="w", pady=(3, 0))

    cargas = tk.Frame(barra, bg=PANEL)
    cargas.pack(side="left", fill="y", pady=12)
    texto_video = _etiqueta(cargas, "VIDEO  Sin cargar", MUTED,
                            (MONO, 8), anchor="w", width=33)
    texto_video.pack(anchor="w")
    texto_configuracion = _etiqueta(cargas, "DATOS  Sin cargar", MUTED,
                          (MONO, 8), anchor="w", width=33)
    texto_configuracion.pack(anchor="w", pady=(3, 0))

    _boton(barra, "Cargar video", cargar_video, compacto=True).pack(side="left", padx=(5, 6))
    _boton(barra, "Cargar configuración", cargar_resultados, compacto=True).pack(side="left", padx=(0, 6))
    _boton(barra, "Abrir proyecto", abrir_proyecto_guardado, compacto=True).pack(side="left", padx=(0, 6))
    _boton(barra, "Guardar proyecto", guardar_proyecto_actual, compacto=True).pack(side="left", padx=(0, 6))
    _boton(barra, "Exportar configuración", exportar_conteo, compacto=True).pack(side="left", padx=(0, 14))

    selector = tk.Frame(barra, bg=PANEL)
    selector.pack(side="right", padx=(4, 21), pady=10)
    _etiqueta(selector, "FILTRO DE TUBO", MUTED, (UI, 8, "bold")).pack(anchor="w")
    menu_canal = ttk.Combobox(selector, width=24, values=list(FILTROS), state="readonly",
                               style="Audit.TCombobox", font=(UI, 10, "bold"))
    menu_canal.set(TODOS)
    menu_canal.pack(pady=(3, 0))
    menu_canal.bind("<<ComboboxSelected>>", al_cambiar_canal)

    contenido = tk.Frame(ventana, bg=BG)
    contenido.pack(fill="both", expand=True, padx=14, pady=14)
    contenido.columnconfigure(0, weight=72, uniform="zona")
    contenido.columnconfigure(1, weight=28, uniform="zona")
    contenido.rowconfigure(0, weight=1)

    izquierda = tk.Frame(contenido, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1)
    izquierda.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
    izquierda.grid_rowconfigure(1, weight=1)
    izquierda.grid_columnconfigure(0, weight=1)

    cabecera_video = tk.Frame(izquierda, bg=PANEL, height=42)
    cabecera_video.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 6))
    _etiqueta(cabecera_video, "REVISIÓN DE VIDEO", WHITE, (UI, 10, "bold")).pack(side="left")
    estado_visor = _etiqueta(cabecera_video, "SIN VIDEO", MUTED, (MONO, 9))
    estado_visor.pack(side="right")

    caja_video = tk.Frame(izquierda, bg=VIDEO_BG)
    caja_video.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 4))
    visor = tk.Label(caja_video, bg=VIDEO_BG, fg=MUTED,
                     text="AUDITORÍA DE DOS TUBOS\n\nTUBO 1   │   TUBO 2\n\nCarga un video MP4 para comenzar",
                     font=(UI, 13), compound="center")
    visor.pack(fill="both", expand=True)
    visor.bind("<Configure>", _en_redimensionar_video)

    telemetria = tk.Frame(izquierda, bg=PANEL_ALT, height=42)
    telemetria.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 3))
    telemetria.pack_propagate(False)
    texto_cuadro = _etiqueta(telemetria, "FRAME  — / —", WHITE,
                             (MONO, 11, "bold"))
    texto_cuadro.pack(side="left", padx=15)
    texto_tiempo = _etiqueta(telemetria, "00:00.00 s", MUTED, (MONO, 10))
    texto_tiempo.pack(side="right", padx=15)
    texto_conteo = _etiqueta(telemetria, "T1  00   ·   T2  00   ·   TOTAL  00", GREEN,
                             (MONO, 10, "bold"))
    texto_conteo.pack(side="left", expand=True)

    timeline = tk.Canvas(izquierda, bg=PANEL, height=35, highlightthickness=0,
                         cursor="hand2")
    timeline.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 3))
    timeline.bind("<Configure>", _dibujar_timeline)
    timeline.bind("<Button-1>", _seleccionar_en_timeline)
    timeline.bind("<B1-Motion>", _seleccionar_en_timeline)

    controles = tk.Frame(izquierda, bg=PANEL, height=57)
    controles.grid(row=4, column=0, sticky="ew", padx=15, pady=(0, 6))
    grupo = tk.Frame(controles, bg=PANEL)
    grupo.pack(anchor="center")
    _boton(grupo, "|◀  Inicio", _primero, compacto=True).pack(side="left", padx=4)
    _boton(grupo, "A  -1 Frame", anterior_cuadro, compacto=True).pack(side="left", padx=4)
    boton_play = _boton(grupo, "▶  Reproducir   SPACE", alternar_reproduccion,
                        principal=True, compacto=True)
    boton_play.pack(side="left", padx=4)
    _boton(grupo, "D  +1 Frame", siguiente_cuadro, compacto=True).pack(side="left", padx=4)
    _boton(grupo, "▶|  Sig. alerta", _siguiente_alerta, compacto=True).pack(side="left", padx=4)
    _etiqueta(izquierda, "FLUJO: ↓ ARRIBA A ABAJO   ·   ROJO: anomalía   ·   VERDE: detección   ·   A/D: navegar",
              MUTED, (UI, 8), anchor="center").grid(row=5, column=0,
                                                     pady=(0, 10), sticky="ew")

    derecha = tk.Frame(contenido, bg=PANEL, highlightbackground=BORDER,
                       highlightthickness=1)
    derecha.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
    divisor = tk.PanedWindow(derecha, orient="vertical", bg=BORDER, bd=0, sashwidth=8,
                             sashrelief="flat", sashcursor="sb_v_double_arrow",
                             opaqueresize=True)
    divisor.pack(fill="both", expand=True)
    zona_alertas = tk.Frame(divisor, bg=PANEL)
    zona_correcciones = tk.Frame(divisor, bg=PANEL)
    divisor.add(zona_alertas, minsize=170, stretch="always")
    divisor.add(zona_correcciones, minsize=250, stretch="always")
    derecho_header = tk.Frame(zona_alertas, bg=PANEL)
    derecho_header.pack(fill="x", padx=16, pady=(18, 11))
    _etiqueta(derecho_header, "MOTOR DE ALERTAS", WHITE,
              (UI, 11, "bold")).pack(side="left")
    texto_alertas = tk.Label(derecho_header, text="0 ALERTAS", bg="#482A31",
                             fg="#FCA5A5", padx=9, pady=5, font=(MONO, 8, "bold"))
    texto_alertas.pack(side="right")
    tk.Frame(zona_alertas, bg=BORDER, height=1).pack(fill="x", padx=16)
    _etiqueta(zona_alertas, "Selecciona una alerta para ir al fotograma.",
              MUTED, (UI, 9), anchor="w", wraplength=300).pack(fill="x", padx=16,
                                                               pady=(12, 12))
    panel_scrolling = tk.Frame(zona_alertas, bg=PANEL)
    panel_scrolling.pack(fill="both", expand=True)
    scrollbar = tk.Scrollbar(panel_scrolling, bg=PANEL_ALT, troughcolor=PANEL,
                             activebackground=BLUE, width=10)
    scrollbar.pack(side="right", fill="y")
    canvas_alertas = tk.Canvas(panel_scrolling, bg=PANEL, bd=0,
                               highlightthickness=0, yscrollcommand=scrollbar.set)
    canvas_alertas.pack(side="left", fill="both", expand=True)
    scrollbar.configure(command=canvas_alertas.yview)
    panel_tarjetas = tk.Frame(canvas_alertas, bg=PANEL)
    panel_id = canvas_alertas.create_window((0, 0), window=panel_tarjetas, anchor="nw")
    panel_tarjetas.bind("<Configure>", lambda e: canvas_alertas.configure(
        scrollregion=canvas_alertas.bbox("all")))
    canvas_alertas.bind("<Configure>", lambda e: canvas_alertas.itemconfigure(
        panel_id, width=e.width))
    canvas_alertas.bind("<MouseWheel>", _al_mousewheel)
    canvas_alertas.bind("<Button-4>", _al_mousewheel)
    canvas_alertas.bind("<Button-5>", _al_mousewheel)
    panel_tarjetas.bind("<MouseWheel>", _al_mousewheel)

    footer = tk.Frame(zona_alertas, bg=PANEL)
    footer.pack(fill="x", side="bottom", padx=15, pady=14,
                before=panel_scrolling)
    botones_alerta = tk.Frame(footer, bg=PANEL)
    botones_alerta.pack(fill="x")
    _boton(botones_alerta, "Ir a alerta  ↗", ir_a_alerta,
           compacto=True).pack(side="left", expand=True, fill="x", padx=(0, 3))
    boton_revisada = _boton(botones_alerta, "✓  Revisada  R", alternar_revisada,
                            compacto=True)
    boton_revisada.pack(side="left", expand=True, fill="x", padx=(3, 0))
    _etiqueta(footer, "Resultados del tracker · Correcciones editables",
              MUTED, (UI, 8)).pack(pady=(9, 0))
    estado_lineas = _etiqueta(footer, "", AMBER, (MONO, 8),
                              wraplength=300, justify="center")
    estado_lineas.pack(pady=(5, 0))
    _actualizar_estado_lineas()

    panel_correcciones = PanelCorrecciones(
        zona_correcciones,
        obtener_canal=canal_elegido,
        obtener_cuadro=lambda: cuadro_actual,
        obtener_total=lambda: total_cuadros,
        ir_a_frame=ir_a_frame,
        al_cambiar=actualizar_desde_correcciones,
        canales=TUBOS,
        usuario_id=sesion.usuario_id,
    )
    panel_correcciones.pack(fill="both", expand=True, padx=15, pady=(0, 6))
    # La lista de correcciones crece al agrandar el panel con el divisor.
    panel_correcciones._lista.master.pack_configure(fill="both", expand=True)
    panel_correcciones._lista.pack_configure(fill="both", expand=True)

    def _ajustar_divisor():
        ventana.update_idletasks()
        minimo = max(250, panel_correcciones.winfo_reqheight() + 10)
        divisor.paneconfigure(zona_correcciones, minsize=minimo)
        divisor.sash_place(0, 0, max(170, divisor.winfo_height() - minimo - 120))

    ventana.after(100, _ajustar_divisor)

    ventana.bind("<KeyPress>", _tecla)
    ventana.bind("<Control-z>", lambda e: panel_correcciones.deshacer())
    ventana.bind("<Control-s>", lambda e: guardar_proyecto_actual())
    ventana.protocol("WM_DELETE_WINDOW", _cerrar)
    _construir_tarjetas()
    _dibujar_timeline()
    ventana.mainloop()


def start():
    raiz = tk.Tk()

    def iniciar_sesion(nombre_usuario):
        usuario = obtener_usuario(nombre_usuario)

        if usuario is None:
            return

        sesion.usuario_id = usuario[0]
        sesion.nombre_usuario = usuario[1]

        raiz.destroy()
        main(nombre_usuario)

    VentanaLogin(
        raiz,
        iniciar_sesion,
    )

    raiz.mainloop()


if __name__ == "__main__":
    start()