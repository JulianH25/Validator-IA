import mysql.connector


DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "validator",
    "password": "validator123",
    "database": "validator_ia",
}


def conectar():
    return mysql.connector.connect(**DB_CONFIG)


def usuario_existe(nombre_usuario):
    conexion = conectar()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT id
            FROM usuarios
            WHERE nombre_usuario = %s
            """,
            (nombre_usuario,),
        )

        return cursor.fetchone() is not None

    finally:
        cursor.close()
        conexion.close()

def obtener_usuario(nombre_usuario):
    conexion = conectar()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT id, nombre_usuario
            FROM usuarios
            WHERE nombre_usuario = %s
            """,
            (nombre_usuario,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        conexion.close()

def guardar_correccion(
    usuario_id,
    tipo_correccion,
    canal=None,
    cuadro=None,
    id_pez=None,
):
    conexion = conectar()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            """
            INSERT INTO historial_correcciones (
                usuario_id,
                tipo_correccion,
                canal,
                cuadro,
                id_pez
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                usuario_id,
                tipo_correccion,
                canal,
                cuadro,
                id_pez,
            ),
        )

        conexion.commit()

    finally:
        cursor.close()
        conexion.close()