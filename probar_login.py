import customtkinter as ctk

from visor_video.login import VentanaLogin


def login_correcto(nombre_usuario):
    print(f"Inicio de sesión correcto: {nombre_usuario}")


root = ctk.CTk()

VentanaLogin(
    root,
    login_correcto,
)

root.mainloop()