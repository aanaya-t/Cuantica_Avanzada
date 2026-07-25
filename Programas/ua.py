"""
Script para DOBLES barridos parametricos de COMSOL (ej. barrido de B y de n
al mismo tiempo, cada combinacion con varios estados propios).

Que hace:
  1) Abre una ventana para elegir el archivo .txt.
  2) Detecta automaticamente si el archivo corresponde a un DOBLE barrido
     (dos variables que cambian, ej. B y n) armando una rejilla var1 x var2.
     Si no detecta una rejilla valida, avisa y se detiene (para eso esta el
     otro script, graficar_barrido_interfaz.py, pensado para un solo barrido).
  3) Grafica, en una misma ventana dividida en dos:
       - Izquierda: superficie 3D (var1, var2, valor) — se puede rotar con
         el mouse porque es una ventana interactiva normal de matplotlib.
       - Derecha: el mismo dato como mapa de colores 2D (var1 vs var2,
         color = valor), version "vista desde arriba" de la superficie.
  4) Como una superficie solo puede tener un valor Z por punto, hay que
     elegir UN estado propio para graficar (variable ESTADO_A_GRAFICAR en
     la configuracion).
  5) Soporta valores complejos (formato COMSOL "a+bi") y dejar elegir si se
     grafica la parte real o imaginaria.

Uso:
    python graficar_barrido_doble_3d.py
"""

import os
import re
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (habilita projection="3d")

# =============================================================================
# CONFIGURACION (editar aqui, no se pregunta por interfaz)
# =============================================================================

# Carpeta donde estan tus .txt (se abre ahi la ventana de seleccion de archivo)
CARPETA_POR_DEFECTO = r"C:\Users\Admin\Documents\Cuantica_Avanzada\Tablas"

# Columnas del archivo (numeracion normal, empezando en 1). Ajusta segun tu
# archivo, ej. para B(T), n, lambda, Energia propia(meV), Probabilidad:
COLUMNA_VAR1 = 1    # variable del barrido "externo" (ej. B)
COLUMNA_VAR2 = 2    # variable del barrido "interno" (ej. n)
COLUMNA_VALOR = 4   # columna a graficar en Z / color (ej. Energia propia)

# Que estado propio graficar dentro de cada combinacion (var1, var2):
#   1 = el mas bajo (primero) de cada bloque, 2 = el siguiente, etc.
ESTADO_A_GRAFICAR = 1

# Si la columna de valor tiene numeros complejos (formato COMSOL "a+bi"):
#   True  -> se grafica la parte REAL
#   False -> se grafica la parte IMAGINARIA
GRAFICAR_PARTE_REAL = True


# ---------------------------------------------------------------------------
# Lectura de archivo
# ---------------------------------------------------------------------------

def parsear_valor(texto):
    """Parsea un numero real o complejo (COMSOL usa 'i', Python usa 'j')."""
    texto = texto.strip()
    try:
        return float(texto)
    except ValueError:
        pass
    return complex(texto.replace("i", "j"))


def detectar_nombres_columnas(lineas_crudas):
    """Busca la ultima linea de encabezado ('%') que tenga pinta de nombres
    de columna (varios campos separados por 2+ espacios) y los devuelve."""
    nombres = None
    for linea in lineas_crudas:
        l = linea.strip()
        if l.startswith("%"):
            contenido = l.lstrip("%").strip()
            partes = re.split(r"\s{2,}", contenido)
            partes = [p.strip() for p in partes if p.strip()]
            if len(partes) >= 2:
                nombres = partes
    return nombres


def elegir_archivo():
    import tkinter as tk
    from tkinter import filedialog

    carpeta_inicial = CARPETA_POR_DEFECTO if os.path.isdir(CARPETA_POR_DEFECTO) else os.getcwd()

    root = tk.Tk()
    root.withdraw()
    ruta = filedialog.askopenfilename(
        title="Selecciona el archivo .txt del doble barrido",
        initialdir=carpeta_inicial,
        filetypes=[("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")],
    )
    root.destroy()

    if not ruta:
        raise SystemExit("No se selecciono ningun archivo. Se cerro el programa.")

    return ruta


def leer_archivo(ruta_archivo):
    with open(ruta_archivo, "r", encoding="utf-8", errors="ignore") as f:
        lineas_crudas = [l.rstrip("\n") for l in f]

    nombres_columnas = detectar_nombres_columnas(lineas_crudas)

    filas = []
    n_cols_esperadas = None
    for linea in lineas_crudas:
        l = linea.strip()
        if not l or l.startswith("%"):
            continue
        valores = l.split()
        try:
            fila = [parsear_valor(v) for v in valores]
        except ValueError:
            continue  # fila mal formada, se ignora
        if not fila:
            continue
        if n_cols_esperadas is None:
            n_cols_esperadas = len(fila)
        if len(fila) != n_cols_esperadas:
            continue  # fila con numero de columnas distinto, se ignora
        filas.append(fila)

    if not filas:
        raise ValueError("No se encontraron filas de datos numericas validas en el archivo.")

    datos = np.array(filas, dtype=complex)
    return datos, nombres_columnas


# ---------------------------------------------------------------------------
# Deteccion y agrupamiento del doble barrido
# ---------------------------------------------------------------------------

def agrupar_doble_barrido(datos, decimales=6):
    """Agrupa las filas por combinacion (var1, var2), en el orden en que
    aparecen. Devuelve una lista de bloques (var1_val, var2_val, [valores_Z])
    y si se detecto parte imaginaria distinta de cero."""
    idx1 = COLUMNA_VAR1 - 1
    idx2 = COLUMNA_VAR2 - 1
    idxz = COLUMNA_VALOR - 1

    n_cols = datos.shape[1]
    for idx, nombre in [(idx1, "COLUMNA_VAR1"), (idx2, "COLUMNA_VAR2"), (idxz, "COLUMNA_VALOR")]:
        if idx < 0 or idx >= n_cols:
            raise ValueError(f"{nombre} esta fuera de rango (el archivo tiene {n_cols} columnas).")

    var1_col = np.round(datos[:, idx1].real, decimales)
    var2_col = np.round(datos[:, idx2].real, decimales)
    z_col_complejo = datos[:, idxz]
    z_col = z_col_complejo.real if GRAFICAR_PARTE_REAL else z_col_complejo.imag
    hay_parte_imaginaria = bool(np.any(z_col_complejo.imag != 0))

    bloques = []
    actual = None
    valores_actual = []
    for v1, v2, z in zip(var1_col, var2_col, z_col):
        clave = (v1, v2)
        if actual is None or clave != actual:
            if actual is not None:
                bloques.append((actual[0], actual[1], valores_actual))
            actual = clave
            valores_actual = [z]
        else:
            valores_actual.append(z)
    if actual is not None:
        bloques.append((actual[0], actual[1], valores_actual))

    return bloques, hay_parte_imaginaria


def es_doble_barrido(bloques):
    """Determina si realmente hay 2 variables barridas: mas de un valor
    unico en var1 y en var2, y que la mayoria de los var1 tengan varios
    var2 asociados (estructura de rejilla, no una coincidencia aislada)."""
    var1_valores = sorted(set(b[0] for b in bloques))
    var2_valores = sorted(set(b[1] for b in bloques))

    if len(var1_valores) <= 1 or len(var2_valores) <= 1:
        return False, var1_valores, var2_valores

    conteo_por_var1 = {}
    for v1, v2, _ in bloques:
        conteo_por_var1.setdefault(v1, set()).add(v2)

    tamanos = [len(s) for s in conteo_por_var1.values()]
    es_doble = float(np.median(tamanos)) > 1

    return es_doble, var1_valores, var2_valores


def construir_grilla(bloques, var1_valores, var2_valores):
    """Arma la matriz Z[i, j] usando el estado ESTADO_A_GRAFICAR (1-indexado)
    de cada bloque (var1[i], var2[j]). Si falta el bloque o el estado no
    existe ahi, deja NaN."""
    idx_var1 = {v: i for i, v in enumerate(var1_valores)}
    idx_var2 = {v: j for j, v in enumerate(var2_valores)}

    Z = np.full((len(var1_valores), len(var2_valores)), np.nan)
    k = ESTADO_A_GRAFICAR - 1

    for v1, v2, valores_z in bloques:
        i = idx_var1[v1]
        j = idx_var2[v2]
        if 0 <= k < len(valores_z):
            Z[i, j] = valores_z[k]

    return Z


# ---------------------------------------------------------------------------
# Graficado: superficie 3D + mapa de colores 2D, en la misma ventana
# ---------------------------------------------------------------------------

def graficar_doble_barrido(var1_valores, var2_valores, Z, nombre_var1, nombre_var2, nombre_valor, titulo):
    X, Y = np.meshgrid(var2_valores, var1_valores)  # X,Y quedan con forma (len(var1), len(var2)) = forma de Z

    fig = plt.figure(figsize=(14, 6))
    fig.suptitle(titulo)

    # --- Izquierda: superficie 3D (se rota arrastrando con el mouse) ---
    ax3d = fig.add_subplot(1, 2, 1, projection="3d")
    superficie = ax3d.plot_surface(X, Y, Z, cmap="viridis", edgecolor="none")
    ax3d.set_xlabel(nombre_var2)
    ax3d.set_ylabel(nombre_var1)
    ax3d.set_zlabel(nombre_valor)
    ax3d.set_title(f"Superficie 3D (Estado {ESTADO_A_GRAFICAR})")
    fig.colorbar(superficie, ax=ax3d, shrink=0.6, pad=0.1)

    # --- Derecha: mismo dato como mapa de colores 2D ---
    ax2d = fig.add_subplot(1, 2, 2)
    mapa = ax2d.pcolormesh(X, Y, Z, cmap="viridis", shading="auto")
    ax2d.set_xlabel(nombre_var2)
    ax2d.set_ylabel(nombre_var1)
    ax2d.set_title(f"Mapa de colores 2D (Estado {ESTADO_A_GRAFICAR})")
    fig.colorbar(mapa, ax=ax2d, label=nombre_valor)

    plt.tight_layout()
    plt.show()


def main():
    ruta_archivo = elegir_archivo()
    datos, nombres_columnas = leer_archivo(ruta_archivo)

    bloques, hay_parte_imaginaria = agrupar_doble_barrido(datos)
    es_doble, var1_valores, var2_valores = es_doble_barrido(bloques)

    idx1 = COLUMNA_VAR1 - 1
    idx2 = COLUMNA_VAR2 - 1
    idxz = COLUMNA_VALOR - 1
    nombre_var1 = nombres_columnas[idx1] if nombres_columnas and idx1 < len(nombres_columnas) else f"Columna {COLUMNA_VAR1}"
    nombre_var2 = nombres_columnas[idx2] if nombres_columnas and idx2 < len(nombres_columnas) else f"Columna {COLUMNA_VAR2}"
    nombre_valor = nombres_columnas[idxz] if nombres_columnas and idxz < len(nombres_columnas) else f"Columna {COLUMNA_VALOR}"
    if hay_parte_imaginaria:
        nombre_valor += " (parte real)" if GRAFICAR_PARTE_REAL else " (parte imaginaria)"

    if not es_doble:
        raise SystemExit(
            "No se detecto un doble barrido en este archivo (solo hay una "
            "variable barrida, o la rejilla no es regular). Para un solo "
            "barrido usa graficar_barrido_interfaz.py."
        )

    print(f"Doble barrido detectado: {nombre_var1} ({len(var1_valores)} valores) "
          f"x {nombre_var2} ({len(var2_valores)} valores).")
    print(f"Graficando el estado #{ESTADO_A_GRAFICAR} de '{nombre_valor}'.")

    Z = construir_grilla(bloques, var1_valores, var2_valores)

    n_nan = int(np.isnan(Z).sum())
    if n_nan:
        print(f"Aviso: {n_nan} combinaciones no tienen el estado #{ESTADO_A_GRAFICAR} "
              f"(quedan como huecos en la grafica).")

    graficar_doble_barrido(
        var1_valores, var2_valores, Z,
        nombre_var1, nombre_var2, nombre_valor,
        titulo=os.path.basename(ruta_archivo),
    )


if __name__ == "__main__":
    main()