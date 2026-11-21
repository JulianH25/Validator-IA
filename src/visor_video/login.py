import customtkinter as ctk
from tkinter import messagebox

from visor_video.database import usuario_existe


class VentanaLogin:
    def __init__(self, root, al_iniciar_sesion):
        self.root = root
        self.al_iniciar_sesion = al_iniciar_sesion

        self.root.title("Inicio de sesión")
        self.root.geometry("400x250")
        self.root.resizable(False, False)

        self.frame = ctk.CTkFrame(self.root)
        self.frame.pack(
            expand=True,
            fill="both",
            padx=30,
            pady=30,
        )

        self.titulo = ctk.CTkLabel(
            self.frame,
            text="Validator-IA",
            font=("Arial", 24, "bold"),
        )
        self.titulo.pack(pady=(20, 20))

        self.entrada_usuario = ctk.CTkEntry(
            self.frame,
            placeholder_text="Nombre de usuario",
            width=250,
        )
        self.entrada_usuario.pack(pady=10)

        self.boton = ctk.CTkButton(
            self.frame,
            text="Iniciar sesión",
            command=self.iniciar_sesion,
        )
        self.boton.pack(pady=20)

        self.entrada_usuario.bind(
            "<Return>",
            lambda event: self.iniciar_sesion(),
        )

    def iniciar_sesion(self):
        nombre_usuario = self.entrada_usuario.get().strip()

        if not nombre_usuario:
            messagebox.showwarning(
                "Inicio de sesión",
                "Ingresa un nombre de usuario.",
            )
            return

        try:
            existe = usuario_existe(nombre_usuario)
        except Exception as error:
            messagebox.showerror(
                "Error de conexión",
                f"No se pudo conectar con la base de datos.\n\n{error}",
            )
            return

        if not existe:
            messagebox.showerror(
                "Inicio de sesión",
                "El usuario no existe.",
            )
            return

        self.al_iniciar_sesion(nombre_usuario)