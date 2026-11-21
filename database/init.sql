CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre_usuario VARCHAR(100) NOT NULL UNIQUE,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historial_correcciones (
    id INT AUTO_INCREMENT PRIMARY KEY,

    usuario_id INT NOT NULL,

    tipo_correccion VARCHAR(50) NOT NULL,
    canal VARCHAR(20),
    cuadro INT,
    id_pez VARCHAR(100),

    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id)
);

INSERT IGNORE INTO usuarios (nombre_usuario)
VALUES
    ('vicente'),
    ('diego'),
    ('julian');