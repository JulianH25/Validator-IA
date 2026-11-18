# Visor de Auditoría — Tracker Salmones

Aplicación de escritorio para revisar videos y resultados de tracking de salmones.
Trabaja con **dos tubos verticales** y asume que los peces **caen de arriba hacia abajo**.
Incluye lectura de CSV, filtro por tubo y alertas sobre posibles anomalías.

## Ejecutar

Desde la carpeta que contiene `pyproject.toml`:

```powershell
uv run start
```

Requiere Python 3.12 y `uv` instalado. Si todavía no se descargaron las dependencias, `uv` las resolverá al ejecutar el comando.

## Uso

1. Selecciona **Cargar video** para cargar un archivo MP4.
2. Selecciona **Cargar CSV** para cargar las detecciones del tracker.
3. Utiliza **Filtro de tubo** para elegir entre **Todos (T1 + T2)**, **Tubo 1** y **Tubo 2**.
4. Selecciona una alerta a la derecha para saltar a su cuadro en el video.

### Navegación

| Control | Función |
| --- | --- |
| `SPACE` | Reproducir o pausar |
| `A` | Retroceder un cuadro |
| `D` | Avanzar un cuadro |
| `Inicio` | Primer cuadro |
| `Sig. alerta` | Ir a la siguiente anomalía |
| Barra de tiempo | Saltar a un cuadro; marcas rojas = anomalías |

La numeración visible comienza en **cuadro 1**, mientras que el CSV normalmente empieza en **frame 0**. El motor de alertas conserva los índices internos y los transforma para mostrarlos correctamente.

## Datos de entrada

CSV con una fila por detección. Columnas habituales:

```csv
frame,track_id,x1,y1,x2,y2,canal
0,101,100,50,180,90,1
0,201,300,60,390,110,2
```

En esta versión los valores de la columna `canal` deben ser **1 o 2**. Si el archivo contiene un tercer tubo (u otra etiqueta), se muestra un error en lugar de omitir detecciones silenciosamente. No se exige que haya peces en ambos tubos en todos los cuadros.

También se admiten varias alternativas de nombres de columna y cajas `x,y,w,h`. Las columnas opcionales `timestamp_ms` y `contado` permiten evaluar posibles eventos duplicados.

## Módulos

- `src/visor_video/visor_video.py`: interfaz, reproducción y navegación.
- `src/visor_video/resultados.py`: lector CSV y filtrado de detecciones.
- `src/visor_video/alertas.py`: motor de detección de anomalías.

Las anomalías se calculan a partir del CSV. El video se usa para revisar visualmente los resultados.

La coordenada `y` crece hacia abajo. Un mismo ID debe avanzar normalmente hacia valores `y` mayores.
Un retroceso vertical de 18 píxeles o más entre cuadros consecutivos genera una alerta de **movimiento hacia arriba**.
El umbral es provisional; puede ajustarse en `ConfiguracionAlertas` una vez se conozca el comportamiento del tracker.
La velocidad de caída no se utiliza todavía para contar peces.

## Alertas adicionales de Diego

Se detectan IDs que aparecen en un solo frame y se muestran como posibles anomalías.

La alerta de primera aparición bajo la línea requiere configurar la posición vertical
`y` de cada tubo en `src/visor_video/lineas_conteo.json`, en **píxeles del video**:

```json
{
  "lineas_conteo_y_px": {"1": 250, "2": 250}
}
```

Por defecto las líneas están en `null` y la alerta queda desactivada. Los valores del
ejemplo no corresponden a una línea real: hay que acordar sus coordenadas con el equipo.
El sistema utiliza el centro de la caja y considera "debajo" cuando `centro_y > linea_y`.
La línea debe definirse por separado para cada tubo y para la resolución del video correspondiente.
Las líneas visibles dibujadas dentro de un video **no se leen automáticamente**.
Al cambiar el JSON, vuelve a pulsar **Cargar CSV** para actualizar las alertas.
El panel indica qué líneas siguen sin configurar. No hay coordenadas de Duotek predefinidas.

Las alertas son indicios que requieren revisión, no errores confirmados.
Al reemplazar el video, el visor desvincula el CSV anterior para evitar mezclar grabaciones.

## Pruebas

```powershell
uv run pytest
```

La aplicación está en fase de visualización y alertas: no incluye todavía herramientas para corregir conteos, deshacer cambios ni guardar modificaciones.
