import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
from PIL import Image, ImageTk

try:
    from .resultados import (
        ErrorResultados,
        cargar_csv,
        dibujar_cajas,
        etiqueta_canal,
    )
    from .alertas import MotorAlertas
except ImportError:  # al ejecutar el archivo directamente
    from resultados import (
        ErrorResultados,
        cargar_csv,
        dibujar_cajas,
        etiqueta_canal,
    )
    from alertas import MotorAlertas


TODOS = "Todos los tubos"

video = None
cuadro_actual = 0
total_cuadros = 0

resultados = None
etiqueta_a_canal = {}
alertas_detectadas = []
motor_alertas = MotorAlertas()


def cargar_video():
    global video, cuadro_actual, total_cuadros

    ruta = filedialog.askopenfilename(
        filetypes=[
            ("Videos", "*.mp4 *.avi *.mov *.mkv")
        ]
    )

    if ruta == "":
        return

    video = cv2.VideoCapture(ruta)

    if not video.isOpened():
        return

    total_cuadros = int(
        video.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    cuadro_actual = 0

    mostrar_cuadro()


def cargar_resultados():
    """Carga el CSV del Tracker y llena el menú de tubos."""
    global resultados, etiqueta_a_canal

    ruta = filedialog.askopenfilename(
        filetypes=[
            ("Resultados del Tracker", "*.csv"),
            ("Todos los archivos", "*.*"),
        ]
    )

    if ruta == "":
        return

    try:
        nuevos = cargar_csv(ruta)
    except ErrorResultados as error:
        messagebox.showerror("No se pudieron cargar los resultados", str(error))
        return

    resultados = nuevos
    etiqueta_a_canal = {etiqueta_canal(c): c for c in resultados.canales}

    menu_canal.config(
        values=[TODOS] + list(etiqueta_a_canal),
        state="readonly",
    )
    menu_canal.set(TODOS)

    if total_cuadros and resultados.ultimo_cuadro >= total_cuadros:
        messagebox.showwarning(
            "Revisa los archivos",
            "Los resultados llegan hasta el cuadro "
            f"{resultados.ultimo_cuadro + 1}, pero el video tiene "
            f"{total_cuadros} cuadros. ¿Son del mismo video?",
        )

    actualizar_alertas()
    mostrar_cuadro()


def actualizar_alertas():
    """Analiza las detecciones cargadas y actualiza la lista de advertencias."""
    global alertas_detectadas

    if resultados is None:
        alertas_detectadas = []
    else:
        alertas_detectadas = motor_alertas.analizar(resultados.detecciones)

    if "lista_alertas" not in globals():
        return

    lista_alertas.delete(0, tk.END)
    for alerta in alertas_detectadas:
        lista_alertas.insert(tk.END, alerta.mensaje)

    if alertas_detectadas:
        texto_alertas.config(
            text=f"Alertas detectadas: {len(alertas_detectadas)}. "
                 "Haz doble clic para ir al cuadro."
        )
    elif resultados is not None:
        texto_alertas.config(text="Alertas detectadas: 0")
    else:
        texto_alertas.config(text="Carga resultados para analizar alertas")


def ir_a_frame(cuadro):
    """Salta al cuadro interno indicado (base 0) y lo muestra en el visor."""
    global cuadro_actual

    if video is None:
        messagebox.showinfo(
            "Carga un video",
            "Carga el video correspondiente antes de saltar a una alerta.",
        )
        return

    if total_cuadros <= 0:
        return

    cuadro_actual = max(0, min(int(cuadro), total_cuadros - 1))
    mostrar_cuadro()


def ir_a_alerta(evento=None):
    """Salta al cuadro de la advertencia seleccionada."""
    seleccion = lista_alertas.curselection()
    if not seleccion:
        return

    indice = seleccion[0]
    if indice >= len(alertas_detectadas):
        return
    ir_a_frame(alertas_detectadas[indice].cuadro)


def canal_elegido():
    """Canal seleccionado en el menú, o None si se ven todos."""
    return etiqueta_a_canal.get(menu_canal.get())


def al_cambiar_canal(evento=None):
    mostrar_cuadro()


def mostrar_cuadro():
    if video is None:
        return

    video.set(
        cv2.CAP_PROP_POS_FRAMES,
        cuadro_actual
    )

    correcto, cuadro = video.read()

    if not correcto:
        return

    texto_peces = ""

    if resultados is not None:
        detecciones = resultados.en_cuadro(cuadro_actual, canal_elegido())
        cuadro = dibujar_cajas(cuadro, detecciones)
        texto_peces = f"   Peces en este cuadro: {len(detecciones)}"

    cuadro = cv2.cvtColor(
        cuadro,
        cv2.COLOR_BGR2RGB
    )

    imagen = Image.fromarray(cuadro)

    # Ajustar el tamaño del video
    imagen.thumbnail((800, 450))

    imagen = ImageTk.PhotoImage(imagen)

    visor.config(image=imagen)
    visor.image = imagen

    texto_cuadro.config(
        text=f"Cuadro: {cuadro_actual + 1} / {total_cuadros}{texto_peces}"
    )


def siguiente_cuadro():
    global cuadro_actual

    if video is None:
        return

    if cuadro_actual < total_cuadros - 1:
        cuadro_actual += 1
        mostrar_cuadro()


def anterior_cuadro():
    global cuadro_actual

    if video is None:
        return

    if cuadro_actual > 0:
        cuadro_actual -= 1
        mostrar_cuadro()


def main():

    global visor
    global texto_cuadro
    global menu_canal
    global lista_alertas
    global texto_alertas

    # --------------------------------
    # Ventana principal
    # --------------------------------

    ventana = tk.Tk()

    ventana.title("Visor de Video")
    ventana.geometry("950x820")


    # --------------------------------
    # Área del video
    # --------------------------------

    visor = tk.Label(
        ventana,
        text="Carga un video",
        bg="white"
    )

    visor.pack(
        padx=10,
        pady=10
    )


    # --------------------------------
    # Botones de carga
    # --------------------------------

    carga = tk.Frame(ventana)

    carga.pack(
        pady=5
    )

    boton_cargar = tk.Button(
        carga,
        text="Cargar video",
        command=cargar_video
    )

    boton_cargar.pack(
        side=tk.LEFT,
        padx=10
    )

    boton_resultados = tk.Button(
        carga,
        text="Cargar resultados",
        command=cargar_resultados
    )

    boton_resultados.pack(
        side=tk.LEFT,
        padx=10
    )


    # --------------------------------
    # Menú de tubo (canal)
    # --------------------------------

    filtro = tk.Frame(ventana)

    filtro.pack(
        pady=5
    )

    tk.Label(
        filtro,
        text="Tubo:"
    ).pack(
        side=tk.LEFT,
        padx=5
    )

    menu_canal = ttk.Combobox(
        filtro,
        values=[TODOS],
        state="disabled",
        width=20
    )

    menu_canal.set(TODOS)

    menu_canal.pack(
        side=tk.LEFT
    )

    menu_canal.bind(
        "<<ComboboxSelected>>",
        al_cambiar_canal
    )


    # --------------------------------
    # Controles
    # --------------------------------

    controles = tk.Frame(ventana)

    controles.pack(
        pady=10
    )


    boton_anterior = tk.Button(
        controles,
        text="◀ Anterior",
        command=anterior_cuadro
    )

    boton_anterior.pack(
        side=tk.LEFT,
        padx=10
    )


    texto_cuadro = tk.Label(
        controles,
        text="Cuadro: -"
    )

    texto_cuadro.pack(
        side=tk.LEFT,
        padx=20
    )


    boton_siguiente = tk.Button(
        controles,
        text="Siguiente ▶",
        command=siguiente_cuadro
    )

    boton_siguiente.pack(
        side=tk.LEFT,
        padx=10
    )


    # --------------------------------
    # Lista interactiva de alertas
    # --------------------------------

    panel_alertas = tk.LabelFrame(
        ventana,
        text="Alertas",
        padx=8,
        pady=8,
    )
    panel_alertas.pack(
        fill=tk.BOTH,
        expand=True,
        padx=15,
        pady=(5, 12),
    )

    texto_alertas = tk.Label(
        panel_alertas,
        text="Carga resultados para analizar alertas",
        anchor="w",
    )
    texto_alertas.pack(fill=tk.X, pady=(0, 5))

    contenedor_lista = tk.Frame(panel_alertas)
    contenedor_lista.pack(fill=tk.BOTH, expand=True)

    barra_alertas = tk.Scrollbar(contenedor_lista)
    barra_alertas.pack(side=tk.RIGHT, fill=tk.Y)

    lista_alertas = tk.Listbox(
        contenedor_lista,
        height=7,
        activestyle="dotbox",
        yscrollcommand=barra_alertas.set,
    )
    lista_alertas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    barra_alertas.config(command=lista_alertas.yview)

    lista_alertas.bind("<Double-Button-1>", ir_a_alerta)

    boton_ir_alerta = tk.Button(
        panel_alertas,
        text="Ir a la alerta seleccionada",
        command=ir_a_alerta,
    )
    boton_ir_alerta.pack(pady=(7, 0))


    # --------------------------------
    # Iniciar aplicación
    # --------------------------------

    ventana.mainloop()


if __name__ == "__main__":
    main()