"""Panel de correcciones del visor: lista de conteos del canal y botones."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

try:
    from .correcciones import ErrorCorreccion, RegistroCorrecciones, ORIGEN_MANUAL
except ImportError:
    from correcciones import ErrorCorreccion, RegistroCorrecciones, ORIGEN_MANUAL

BG = "#181A1F"
PANEL = "#21252B"
PANEL_ALT = "#292E37"
BORDER = "#3A3F4B"
BLUE = "#3B82F6"
RED = "#EF4444"
AMBER = "#F59E0B"
WHITE = "#F3F4F6"
MUTED = "#9CA3AF"
MONO = "Consolas"
UI = "Segoe UI"


class _DialogoEvento(tk.Toplevel):
    """Pide canal y cuadro (el cuadro se escribe base 1, como en pantalla)."""

    def __init__(self, padre, titulo, canales, canal, cuadro, total):
        super().__init__(padre)
        self.title(titulo)
        self.configure(bg=PANEL, padx=18, pady=16)
        self.resizable(False, False)
        self.transient(padre.winfo_toplevel())
        self.resultado = None
        self._canales = canales
        self._total = total

        tk.Label(self, text="Canal", bg=PANEL, fg=MUTED, font=(UI, 9)).grid(row=0, column=0, sticky="w")
        self._canal = ttk.Combobox(self, values=[f"Tubo {c}" for c in canales],
                                   state="readonly", width=14)
        self._canal.set(f"Tubo {canal}" if canal in canales else f"Tubo {canales[0]}")
        self._canal.grid(row=1, column=0, pady=(2, 10), sticky="w")

        rango = f" (1 a {total})" if total else ""
        tk.Label(self, text=f"Cuadro{rango}", bg=PANEL, fg=MUTED, font=(UI, 9)).grid(row=2, column=0, sticky="w")
        self._cuadro = tk.Entry(self, width=16, font=(MONO, 10))
        self._cuadro.insert(0, str(cuadro + 1))
        self._cuadro.grid(row=3, column=0, pady=(2, 6), sticky="w")

        self._error = tk.Label(self, text="", bg=PANEL, fg=RED, font=(UI, 9),
                               wraplength=240, justify="left")
        self._error.grid(row=4, column=0, sticky="w")

        botones = tk.Frame(self, bg=PANEL)
        botones.grid(row=5, column=0, pady=(10, 0), sticky="e")
        tk.Button(botones, text="Cancelar", command=self.destroy, bg=PANEL_ALT,
                  fg=WHITE, relief="flat", padx=12, pady=5).pack(side="left", padx=(0, 6))
        tk.Button(botones, text="Aceptar", command=self._aceptar, bg=BLUE,
                  fg=WHITE, relief="flat", padx=12, pady=5).pack(side="left")

        self.bind("<Return>", lambda e: self._aceptar())
        self.bind("<Escape>", lambda e: self.destroy())
        self._cuadro.focus_set()
        self._cuadro.selection_range(0, "end")
        self.grab_set()
        self.wait_window()

    def _aceptar(self):
        try:
            cuadro = int(self._cuadro.get().strip()) - 1
        except ValueError:
            self._error.configure(text="El cuadro debe ser un número entero.")
            return
        if cuadro < 0 or (self._total and cuadro >= self._total):
            self._error.configure(text="El cuadro está fuera del video.")
            return
        self.resultado = (self._canal.get().replace("Tubo ", ""), cuadro)
        self.destroy()


class PanelCorrecciones(tk.Frame):
    def __init__(self, padre, obtener_canal, obtener_cuadro, obtener_total,
                 ir_a_frame, al_cambiar=None, canales=("1", "2")):
        super().__init__(padre, bg=PANEL)
        self._obtener_canal = obtener_canal
        self._obtener_cuadro = obtener_cuadro
        self._obtener_total = obtener_total
        self._ir_a_frame = ir_a_frame
        self._al_cambiar = al_cambiar
        self._canales = tuple(canales)
        self.registro: RegistroCorrecciones | None = None
        self._ids: list[int] = []

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))
        cabecera = tk.Frame(self, bg=PANEL)
        cabecera.pack(fill="x")
        tk.Label(cabecera, text="CORRECCIONES", bg=PANEL, fg=WHITE,
                 font=(UI, 10, "bold")).pack(side="left")
        self._conteos = tk.Label(cabecera, text="Sin resultados", bg=PANEL,
                                 fg=MUTED, font=(MONO, 9, "bold"))
        self._conteos.pack(side="right")

        caja = tk.Frame(self, bg=PANEL)
        caja.pack(fill="x", pady=(6, 6))
        barra = tk.Scrollbar(caja, width=10)
        barra.pack(side="right", fill="y")
        self._lista = tk.Listbox(
            caja, height=5, bg=PANEL_ALT, fg=WHITE, font=(MONO, 9),
            selectbackground=BLUE, selectforeground=WHITE, activestyle="none",
            highlightthickness=1, highlightbackground=BORDER, relief="flat",
            exportselection=False, yscrollcommand=barra.set,
        )
        self._lista.pack(side="left", fill="x", expand=True)
        barra.configure(command=self._lista.yview)
        self._lista.bind("<Double-Button-1>", self._saltar)

        fila1 = tk.Frame(self, bg=PANEL)
        fila1.pack(fill="x")
        self._boton(fila1, "+ Agregar aquí", self.agregar).pack(side="left", expand=True, fill="x", padx=(0, 3))
        self._boton(fila1, "Eliminar", self.eliminar).pack(side="left", expand=True, fill="x", padx=3)
        fila2 = tk.Frame(self, bg=PANEL)
        fila2.pack(fill="x", pady=(5, 0))
        self._boton(fila2, "Mover…", self.mover).pack(side="left", expand=True, fill="x", padx=(0, 3))
        self._btn_deshacer = self._boton(fila2, "↶ Deshacer  Ctrl+Z", self.deshacer)
        self._btn_deshacer.pack(side="left", expand=True, fill="x", padx=3)
        self.refrescar()

    @staticmethod
    def _boton(padre, texto, accion):
        return tk.Button(padre, text=texto, command=accion, font=(UI, 8, "bold"),
                         bg=PANEL_ALT, fg=WHITE, activebackground=BORDER,
                         activeforeground=WHITE, disabledforeground="#6B7280",
                         relief="flat", borderwidth=0, cursor="hand2",
                         padx=6, pady=6, highlightthickness=0)

    # ---------- ciclo de vida ----------
    def cargar(self, eventos):
        self.registro = RegistroCorrecciones(
            eventos, self._canales, self._obtener_total() or None
        )
        self.refrescar()

    def limpiar(self):
        self.registro = None
        self.refrescar()

    # ---------- vista ----------
    def refrescar(self, seleccionar=None):
        self._lista.delete(0, "end")
        self._ids = []
        if self.registro is None:
            self._conteos.configure(text="Sin resultados", fg=MUTED)
            self._btn_deshacer.configure(state="disabled")
            return
        canal = self._obtener_canal()
        for e in self.registro.eventos(canal):
            marca = "✎" if e.origen == ORIGEN_MANUAL else " "
            pez = f"ID {e.id_pez}" if e.id_pez else "manual"
            self._lista.insert("end", f"{marca} T{e.canal}  frame {e.cuadro + 1:05d}  {pez}")
            self._ids.append(e.id)
        if seleccionar in self._ids:
            fila = self._ids.index(seleccionar)
            self._lista.selection_set(fila)
            self._lista.see(fila)
        c = self.registro.conteos()
        texto = "  ".join(f"T{k}:{v}" for k, v in c.items()) + f"  Total:{self.registro.total}"
        self._conteos.configure(text=texto, fg=AMBER if self.registro.hay_cambios else WHITE)
        self._btn_deshacer.configure(
            state="normal" if self.registro.puede_deshacer else "disabled")
        if self._al_cambiar:
            self._al_cambiar()

    # ---------- acciones ----------
    def _seleccionado(self):
        seleccion = self._lista.curselection()
        if not seleccion:
            messagebox.showinfo("Selecciona un conteo",
                                "Elige un conteo de la lista primero.")
            return None
        return self._ids[seleccion[0]]

    def _hay_registro(self):
        if self.registro is None:
            messagebox.showinfo("Carga los resultados",
                                "Carga el CSV del tracker para poder corregir conteos.")
            return False
        return True

    def _saltar(self, _evento=None):
        seleccion = self._lista.curselection()
        if seleccion and self.registro is not None:
            self._ir_a_frame(self.registro.evento(self._ids[seleccion[0]]).cuadro)

    def agregar(self):
        if not self._hay_registro():
                self.registro.total_cuadros = self._obtener_total() or None
                return
        canal, cuadro = self._obtener_canal(), self._obtener_cuadro()
        if canal is None:  # filtro "Todos": hay que elegir el tubo
            datos = _DialogoEvento(self, "Agregar conteo", self._canales,
                                   self._canales[0], cuadro, self._obtener_total()).resultado
            if datos is None:
                return
            canal, cuadro = datos
        try:
            nuevo = self.registro.agregar(canal, cuadro)
        except ErrorCorreccion as exc:
            messagebox.showerror("No se pudo agregar", str(exc))
            return
        self.refrescar(seleccionar=nuevo.id)

    def eliminar(self):
        if not self._hay_registro():
            return
        evento_id = self._seleccionado()
        if evento_id is None:
            return
        try:
            self.registro.eliminar(evento_id)
        except ErrorCorreccion as exc:
            messagebox.showerror("No se pudo eliminar", str(exc))
            return
        self.refrescar()

    def mover(self):
        if not self._hay_registro():
            self.registro.total_cuadros = self._obtener_total() or None
            return
        evento_id = self._seleccionado()
        if evento_id is None:
            return
        actual = self.registro.evento(evento_id)
        datos = _DialogoEvento(self, "Mover conteo", self._canales, actual.canal,
                               actual.cuadro, self._obtener_total()).resultado
        if datos is None:
            return
        try:
            self.registro.mover(evento_id, *datos)
        except ErrorCorreccion as exc:
            messagebox.showerror("No se pudo mover", str(exc))
            return
        self.refrescar(seleccionar=evento_id)

    def deshacer(self, _evento=None):
        if self.registro is None or not self.registro.puede_deshacer:
            return
        op = self.registro.deshacer()
        self.refrescar(seleccionar=op.evento_id if op else None)