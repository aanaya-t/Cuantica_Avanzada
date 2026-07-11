"""
Script para graficar un barrido parametrico de COMSOL (solucion de la ecuacion
de Schrodinger) exportado como tabla .txt.

Acepta DOS formatos de archivo de entrada (se detectan automaticamente):

  FORMATO 1 - Exportacion original de COMSOL:
    Lineas de encabezado que empiezan con '%', seguidas de 4 columnas:
        x_0 (nm) | lambda | Energia propia (eV) | Probabilidad total (1)
    Para cada valor de x_0 hay varias filas consecutivas, una por cada
    estado propio. El script agrupa esas filas por bloque (mismo x_0) y
    arma una "rama" (curva) por cada posicion dentro del bloque, asumiendo
    que COMSOL exporta los estados siempre en el mismo orden.

  FORMATO 2 - Salida de seleccionar_y_exportar_barrido.py:
    Una linea de encabezado con nombres de columna (x_0(nm), Estado_1(eV),
    Estado_3(eV), ...) seguida de filas donde cada columna ya es una rama
    (formato ancho, separado por tabuladores o espacios). En este caso no
    hace falta agrupar nada, se lee directo.

Uso:
    python graficar_barrido_comsol.py
    (usa la ruta fija definida en RUTA_ARCHIVO_POR_DEFECTO, o puedes pasar
    otra ruta como argumento)

    python graficar_barrido_comsol.py "C:/ruta/a/otro_archivo.txt"
"""

import sys
import numpy as np
import matplotlib.pyplot as plt

# Ruta fija del archivo de datos
RUTA_ARCHIVO_POR_DEFECTO = r"C:\Users\Admin\Documents\Cuantica_Avanzada\Tablas\p.txt"


def leer_datos(ruta_archivo):
    """Lee el archivo original de COMSOL (formato 1), ignora el encabezado
    (lineas que empiezan con '%') y devuelve un arreglo numpy con las
    4 columnas numericas."""
    filas = []
    with open(ruta_archivo, "r", encoding="utf-8", errors="ignore") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("%"):
                continue
            valores = linea.split()
            if len(valores) < 4:
                continue
            try:
                fila = [float(v) for v in valores[:4]]
            except ValueError:
                continue
            filas.append(fila)

    if not filas:
        raise ValueError("No se encontraron filas de datos validas en el archivo.")

    return np.array(filas)  # columnas: x_0, lambda, energia, probabilidad


def leer_formato_ancho(lineas_datos):
    """Lee el formato 2 (salida de seleccionar_y_exportar_barrido.py):
    una linea de encabezado (x_0(nm), Estado_1(eV), ...) seguida de filas
    ya organizadas por columnas/ramas. Devuelve x0_unicos, ramas, etiquetas."""
    encabezado = lineas_datos[0]
    separador = "\t" if "\t" in encabezado else None
    columnas = encabezado.split(separador)
    etiquetas = [c.strip() for c in columnas[1:]]

    filas = []
    for linea in lineas_datos[1:]:
        partes = linea.split(separador)
        partes = [p.strip() for p in partes]
        fila = [float(p) if p != "" else np.nan for p in partes]
        filas.append(fila)

    tabla = np.array(filas)
    x0_unicos = tabla[:, 0]
    ramas = tabla[:, 1:].T  # n_ramas x n_puntos

    return x0_unicos, ramas, etiquetas


def cargar_barrido(ruta_archivo):
    """Funcion unica de carga: detecta si el archivo es el formato original
    de COMSOL o el formato ancho ya exportado, y devuelve en cualquier caso
    (x0_unicos, ramas, etiquetas) listo para graficar."""
    with open(ruta_archivo, "r", encoding="utf-8", errors="ignore") as f:
        lineas_crudas = [linea.rstrip("\n") for linea in f]

    lineas_datos = [linea.strip() for linea in lineas_crudas
                     if linea.strip() and not linea.strip().startswith("%")]

    if not lineas_datos:
        raise ValueError("No se encontraron filas de datos validas en el archivo.")

    primer_token = lineas_datos[0].split()[0]
    try:
        float(primer_token)
        es_formato_ancho = False
    except ValueError:
        es_formato_ancho = True

    if es_formato_ancho:
        x0_unicos, ramas, etiquetas = leer_formato_ancho(lineas_datos)
    else:
        datos = leer_datos(ruta_archivo)
        x0_unicos, ramas = agrupar_por_ramas(datos)
        etiquetas = [f"Estado {i + 1}" for i in range(ramas.shape[0])]

    return x0_unicos, ramas, etiquetas


def agrupar_por_ramas(datos, decimales_x0=6):
    """Agrupa las filas en bloques con el mismo x_0 (redondeado) y arma
    una rama por posicion dentro de cada bloque.

    Devuelve:
        x0_unicos: array con los valores unicos de x_0, en orden de aparicion
        ramas: lista de arrays, donde ramas[i] es la energia de la rama i
               (misma longitud que x0_unicos; puede tener NaN si algun
               bloque tiene menos estados que otros)
    """
    x0_col = datos[:, 0]
    energia_col = datos[:, 2]

    x0_redondeado = np.round(x0_col, decimales_x0)

    x0_unicos = []
    bloques = []  # lista de listas de energias, un elemento por x_0 unico

    x0_actual = None
    bloque_actual = []

    for x0_val, energia in zip(x0_redondeado, energia_col):
        if x0_actual is None or x0_val != x0_actual:
            if x0_actual is not None:
                x0_unicos.append(x0_actual)
                bloques.append(bloque_actual)
            x0_actual = x0_val
            bloque_actual = [energia]
        else:
            bloque_actual.append(energia)

    # agregar el ultimo bloque
    if x0_actual is not None:
        x0_unicos.append(x0_actual)
        bloques.append(bloque_actual)

    n_ramas = max(len(b) for b in bloques)
    n_puntos = len(x0_unicos)

    ramas = np.full((n_ramas, n_puntos), np.nan)
    for j, bloque in enumerate(bloques):
        for i, energia in enumerate(bloque):
            ramas[i, j] = energia

    return np.array(x0_unicos), ramas


def graficar(x0_unicos, ramas, etiquetas=None, titulo="Energia propia vs x_0"):
    plt.figure(figsize=(9, 6))
    n_ramas = ramas.shape[0]

    if etiquetas is None:
        etiquetas = [f"Estado {i + 1}" for i in range(n_ramas)]

    for i in range(n_ramas):
        plt.plot(x0_unicos, ramas[i, :], linestyle="-", linewidth=1.8,
                  label=etiquetas[i])

    plt.xlabel(r"$x_0$ (nm)")
    plt.ylabel("Energia propia (eV)")
    plt.title(titulo)
    plt.legend(loc="best", fontsize=8, ncol=2)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def main():
    if len(sys.argv) > 1:
        ruta_archivo = sys.argv[1]
    else:
        ruta_archivo = RUTA_ARCHIVO_POR_DEFECTO

    x0_unicos, ramas, etiquetas = cargar_barrido(ruta_archivo)

    print(f"Se detectaron {len(x0_unicos)} valores de x_0 y {ramas.shape[0]} ramas (estados propios).")

    graficar(x0_unicos, ramas, etiquetas)


if __name__ == "__main__":
    main()