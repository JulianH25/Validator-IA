"""Visor de auditoría de salmones con caída vertical por dos tubos."""

from __future__ import annotations

import math
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

try:
    from .resultados import ErrorResultados, cargar_varios, etiqueta_canal
    from .alertas import MotorAlertas, cargar_lineas_conteo
    from .correcciones import eventos_desde_resultados
    from .panel_correcciones import PanelCorrecciones
except ImportError:
    from resultados import ErrorResultados, cargar_varios, etiqueta_canal
    from alertas import MotorAlertas, cargar_lineas_conteo
    from correcciones import eventos_desde_resultados
    from panel_correcciones import PanelCorrecciones


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
motor_alertas = MotorAlertas()

ventana = None
visor = None
menu_canal = None
texto_cuadro = None
texto_tiempo = None
texto_alertas = None
texto_video = None
texto_csv = None
timeline = None
panel_tarjetas = None
canvas_alertas = None
boton_play = None
estado_visor = None
estado_lineas = None

panel_correcciones = None

alerta_seleccionada = None
frames_tarjetas = []
reproduciendo = False
reproduccion_after = None
fps_video = 30.0
ultima_dimension = (0, 0)


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


def cargar_video():
    """Abre un video local y restaura la navegación al primer cuadro.

    Si ya había resultados cargados (CSV primero y video después),
    se conservan junto con sus correcciones.
    """
    global video, cuadro_actual, total_cuadros, fps_video
    ruta = filedialog.askopenfilename(
        filetypes=[("Video MP4", "*.mp4"), ("Todos", "*.*")]
    )
    if not ruta:
        return
    nuevo_video = cv2.VideoCapture(ruta)
    if not nuevo_video.isOpened():
        messagebox.showerror("No se pudo abrir", "No fue posible abrir el video seleccionado.")
        nuevo_video.release()
        return

    detener_reproduccion()
    if video is not None:
        video.release()
    video = nuevo_video
    total_cuadros = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(video.get(cv2.CAP_PROP_FPS))
    fps_video = fps if math.isfinite(fps) and fps > 0 else 30.0
    cuadro_actual = 0
    if texto_video is not None:
        texto_video.configure(text=f"VIDEO  {os.path.basename(ruta)[:31]}", fg=GREEN)
    if estado_visor is not None:
        estado_visor.configure(text="VIDEO CARGADO", fg=GREEN)

    # El registro de correcciones necesita saber cuántos cuadros tiene el video.
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


def cargar_resultados():
    """Carga datos del tracker (un archivo con los 2 tubos, o uno por tubo)."""
    global resultados, etiqueta_a_canal
    rutas = filedialog.askopenfilenames(
        filetypes=[("Resultados del tracker", "*.csv"), ("Todos", "*.*")]
    )
    if not rutas:
        return
    try:
        nuevos = cargar_varios(rutas, resolver_canal=_preguntar_tubo)
    except (ErrorResultados, OSError) as exc:
        messagebox.showerror("No se pudieron cargar los resultados", str(exc))
        return

    no_admitidos = _canales_no_admitidos(nuevos.canales)
    if no_admitidos:
        messagebox.showerror(
            "CSV incompatible",
            "Este visor está configurado únicamente para Tubo 1 y Tubo 2.\n"
            "Canales encontrados fuera de ese rango: " + ", ".join(no_admitidos) + ".\n"
            "Revisa el CSV o consulta con el responsable de los datos del tracker.",
        )
        return

    _cargar_configuracion_lineas()
    resultados = nuevos
    etiqueta_a_canal = {nombre: canal for nombre, canal in FILTROS.items() if canal is not None}
    menu_canal.configure(values=list(FILTROS), state="readonly")
    menu_canal.set(TODOS)
    if texto_csv is not None:
        nombre = (os.path.basename(rutas[0]) if len(rutas) == 1
                  else f"{len(rutas)} archivos")
        texto_csv.configure(text=f"DATOS  {nombre[:31]}", fg=GREEN)

    if total_cuadros and resultados.ultimo_cuadro >= total_cuadros:
        messagebox.showwarning(
            "Revisa los archivos",
            f"Los resultados llegan al cuadro {resultados.ultimo_cuadro + 1}, "
            f"pero el video tiene {total_cuadros} cuadros. ¿Son del mismo video?",
        )

    if panel_correcciones is not None:
        panel_correcciones.cargar(eventos_desde_resultados(nuevos))
    actualizar_alertas()
    mostrar_cuadro()



def _cargar_configuracion_lineas():
    ruta = Path(__file__).with_name("lineas_conteo.json")
    try:
        motor_alertas.config.lineas_conteo_y_px = cargar_lineas_conteo(ruta)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        motor_alertas.config.lineas_conteo_y_px = {}
        if ventana is not None:
            messagebox.showwarning("Líneas de conteo", str(exc))
    if estado_lineas is not None:
        lineas = motor_alertas.config.lineas_conteo_y_px
        sin_linea = [t for t in TUBOS if t not in lineas]
        texto = ("LÍNEAS SIN CONFIGURAR: " + ", ".join("T" + t for t in sin_linea)
                 if sin_linea else "LÍNEAS CONFIGURADAS: " + ", ".join(
                     f"T{t} y={lineas[str(t)]:g}" for t in TUBOS))
        estado_lineas.configure(text=texto, fg=AMBER if sin_linea else GREEN)


def actualizar_alertas():
    """Genera la lista de alertas a partir de las detecciones cargadas."""
    global alertas_detectadas, alerta_seleccionada
    alertas_detectadas = (motor_alertas.analizar(resultados.detecciones)
                         if resultados is not None else [])
    alerta_seleccionada = None

    if texto_alertas is not None:
        texto_alertas.configure(text=f"{len(alertas_detectadas)} ALERTA{'S' if len(alertas_detectadas) != 1 else ''}")
    _construir_tarjetas()
    _dibujar_timeline()


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
        panel_correcciones.refrescar()
    mostrar_cuadro()


def _color_alerta(alerta):
    return {
        "PECES_JUNTOS": RED,
        "PERDIDA_SEGUIMIENTO": AMBER,
        "POSIBLE_DUPLICADO": RED,
        "APARICION_UN_CUADRO": AMBER,
        "INICIO_BAJO_LINEA": RED,
        "MOVIMIENTO_CONTRARIO": AMBER,
    }.get(alerta.tipo, RED)


def _titulo_alerta(alerta):
    return {
        "PECES_JUNTOS": "Peces muy juntos",
        "PERDIDA_SEGUIMIENTO": "Pérdida de seguimiento",
        "POSIBLE_DUPLICADO": "Posible duplicado",
        "APARICION_UN_CUADRO": "ID en un solo frame",
        "INICIO_BAJO_LINEA": "Aparición bajo la línea",
        "MOVIMIENTO_CONTRARIO": "Movimiento hacia arriba",
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


def mostrar_cuadro():
    if video is None or visor is None:
        return
    video.set(cv2.CAP_PROP_POS_FRAMES, cuadro_actual)
    correcto, imagen_bgr = video.read()
    if not correcto:
        return

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
            timeline.create_line(x, y-12, x, y+12, fill=RED, width=2)
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
    global frames_tarjetas
    if panel_tarjetas is not None:
        for hijo in panel_tarjetas.winfo_children():
            hijo.destroy()
    frames_tarjetas = []


def _seleccionar_alerta(indice, saltar=False):
    global alerta_seleccionada
    if not 0 <= indice < len(alertas_detectadas):
        return
    alerta_seleccionada = indice
    _resaltar_tarjetas()
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
        sin_linea = [t for t in TUBOS if t not in motor_alertas.config.lineas_conteo_y_px]
        texto = ("Carga un CSV para analizar los resultados." if resultados is None
                 else "No se detectaron anomalías. Línea sin configurar en "
                      + ", ".join("T" + t for t in sin_linea) + "." if sin_linea
                 else "No se detectaron anomalías con los criterios actuales.")
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
        tk.Label(segunda, text="●", bg=PANEL_ALT, fg=_color_alerta(alerta),
                 font=(UI, 12)).pack(side="left")
        titulo = _etiqueta(segunda, _titulo_alerta(alerta), WHITE, (UI, 10, "bold"))
        titulo.pack(side="left", padx=(5, 0))
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


def _cerrar():
    detener_reproduccion()
    if video is not None:
        video.release()
    ventana.destroy()


def main():
    global ventana, visor, texto_cuadro, texto_tiempo, texto_alertas
    global menu_canal, texto_video, texto_csv, timeline, boton_play
    global panel_tarjetas, canvas_alertas, estado_visor, estado_lineas
    global panel_correcciones

    ventana = tk.Tk()
    ventana.title("Visor de Auditoría - Tracker Salmones")
    ventana.geometry("1440x810")
    ventana.minsize(1050, 620)
    ventana.configure(bg=BG)

    _cargar_configuracion_lineas()

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
    texto_csv = _etiqueta(cargas, "DATOS  Sin cargar", MUTED,
                          (MONO, 8), anchor="w", width=33)
    texto_csv.pack(anchor="w", pady=(3, 0))

    _boton(barra, "Cargar video", cargar_video, compacto=True).pack(side="left", padx=(5, 6))
    _boton(barra, "Cargar CSV", cargar_resultados, compacto=True).pack(side="left", padx=(0, 14))

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
    derecho_header = tk.Frame(derecha, bg=PANEL)
    derecho_header.pack(fill="x", padx=16, pady=(18, 11))
    _etiqueta(derecho_header, "MOTOR DE ALERTAS", WHITE,
              (UI, 11, "bold")).pack(side="left")
    texto_alertas = tk.Label(derecho_header, text="0 ALERTAS", bg="#482A31",
                             fg="#FCA5A5", padx=9, pady=5, font=(MONO, 8, "bold"))
    texto_alertas.pack(side="right")
    tk.Frame(derecha, bg=BORDER, height=1).pack(fill="x", padx=16)
    _etiqueta(derecha, "Selecciona una alerta para ir al fotograma.",
              MUTED, (UI, 9), anchor="w", wraplength=300).pack(fill="x", padx=16,
                                                               pady=(12, 12))
    panel_scrolling = tk.Frame(derecha, bg=PANEL)
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

    footer = tk.Frame(derecha, bg=PANEL)
    footer.pack(fill="x", side="bottom", padx=15, pady=14,
                before=panel_scrolling)
    _boton(footer, "Ir a alerta seleccionada  ↗", ir_a_alerta,
           compacto=True).pack(fill="x")
    _etiqueta(footer, "Resultados del tracker · Correcciones editables",
              MUTED, (UI, 8)).pack(pady=(9, 0))
    estado_lineas = _etiqueta(footer, "", AMBER, (MONO, 8),
                             wraplength=300, justify="center")
    estado_lineas.pack(pady=(5, 0))
    _cargar_configuracion_lineas()

    panel_correcciones = PanelCorrecciones(
        derecha,
        obtener_canal=canal_elegido,
        obtener_cuadro=lambda: cuadro_actual,
        obtener_total=lambda: total_cuadros,
        ir_a_frame=ir_a_frame,
        canales=TUBOS,
    )
    panel_correcciones.pack(fill="x", side="bottom", padx=15, pady=(0, 6),
                            before=panel_scrolling)

    ventana.bind("<KeyPress>", _tecla)
    ventana.bind("<Control-z>", lambda e: panel_correcciones.deshacer())
    ventana.protocol("WM_DELETE_WINDOW", _cerrar)
    _construir_tarjetas()
    _dibujar_timeline()
    ventana.mainloop()


if __name__ == "__main__":
    main()
