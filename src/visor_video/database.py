"""Usuarios e historial de correcciones, guardados en un archivo SQLite local."""

import sqlite3
from contextlib import closing
from pathlib import Path

RUTA_DB = Path(__file__).with_name("validator.db")
USUARIOS_INICIALES = ("vicente", "diego", "julian")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_usuario TEXT NOT NULL UNIQUE,
    fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historial_correcciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    tipo_correccion TEXT NOT NULL,
    canal TEXT,
    cuadro INTEGER,
    id_pez TEXT,
    fecha TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def conectar():
    """Abre el archivo (lo crea si no existe) y deja las tablas listas."""
    conexion = sqlite3.connect(RUTA_DB)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.executescript(_ESQUEMA)
    conexion.executemany(
        "INSERT OR IGNORE INTO usuarios (nombre_usuario) VALUES (?)",
        [(n,) for n in USUARIOS_INICIALES],
    )
    conexion.commit()
    return conexion


def usuario_existe(nombre_usuario):
    with closing(conectar()) as conexion:
        fila = conexion.execute(
            "SELECT id FROM usuarios WHERE nombre_usuario = ?", (nombre_usuario,)
        ).fetchone()
    return fila is not None


def obtener_usuario(nombre_usuario):
    """Devuelve (id, nombre_usuario) o None."""
    with closing(conectar()) as conexion:
        return conexion.execute(
            "SELECT id, nombre_usuario FROM usuarios WHERE nombre_usuario = ?",
            (nombre_usuario,),
        ).fetchone()


def guardar_correccion(usuario_id, tipo_correccion, canal=None, cuadro=None, id_pez=None):
    with closing(conectar()) as conexion:
        with conexion:  # confirma la transacción
            conexion.execute(
                """
                INSERT INTO historial_correcciones
                    (usuario_id, tipo_correccion, canal, cuadro, id_pez)
                VALUES (?, ?, ?, ?, ?)
                """,
                (usuario_id, tipo_correccion, canal, cuadro, id_pez),
            )