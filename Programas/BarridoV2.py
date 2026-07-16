"""
Script robusto para graficar barridos parametricos de COMSOL (Schrodinger).

Mejoras respecto a las versiones anteriores:
  1) Al ejecutar, abre una ventana para ELEGIR UNO O VARIOS archivos .txt
     desde una carpeta (Ctrl+clic o Shift+clic para elegir varios).
  2) Si eliges varios archivos, los grafica todos juntos en un MOSAICO
     (una figura con una subgrafica por archivo).
  3) Detecta automaticamente los NOMBRES DE LAS COLUMNAS leyendo el propio
     archivo (encabezado '%' de COMSOL, o encabezado de fila si es un
     archivo ya exportado en formato ancho). Los titulos de los ejes de
     cada grafica salen de esos nombres, no estan fijos en el codigo.
  4) Acepta los dos formatos que ya manejabamos:
       - Formato COMSOL original (bloques repetidos por cada x_0)
       - Formato ancho (una columna por estado, ya exportado)
  5) La cantidad de estados a graficar se controla con la CONFIGURACION
     al inicio del codigo (variable MODO_SELECCION_ESTADOS), NO se
     pregunta por interfaz. Puede ser:
       - "todos"  -> grafica todos los estados de cada archivo
       - "numero" -> grafica los primeros N estados (define NUMERO_ESTADOS)
       - "elegir" -> abre una ventana para elegir los estados a mano
  6) Es tolerante a filas mal formadas, columnas de distinto tamano, etc:
     las ignora en vez de romper la ejecucion.

Uso:
    python graficar_barrido_interfaz.py
"""

import os
import re
import math
import numpy as np
import matplotlib.pyplot as plt

# =============================================================================
# CONFIGURACION (editar aqui, no se pregunta por interfaz)
# =============================================================================

# Carpeta donde estan tus .txt (se abre ahi la ventana de seleccion de archivo)
CARPETA_POR_DEFECTO = r"C:\Users\Admin\Documents\Cuantica_Avanzada\Tablas"

# Modo de seleccion de ESTADOS a graficar, para cada archivo:
#   "todos"  -> grafica todos los estados detectados en el archivo
#   "numero" -> grafica los primeros NUMERO_ESTADOS estados
#   "elegir" -> abre una ventana para elegir los estados a mano (por archivo)
MODO_SELECCION_ESTADOS = "todos"  # "todos" | "numero" | "elegir"

# Se usa solo si MODO_SELECCION_ESTADOS == "numero"
NUMERO_ESTADOS = 5

# Columnas del archivo COMSOL a usar (formato original, con bloques
# repetidos por cada x_0). Se numeran como en el archivo, empezando en 1:
#   ej. x_0(nm)=1, lambda=2, Energia propia(eV)=3, Probabilidad=4
COLUMNA_X = 1
COLUMNA_Y = 3

# Si la columna Y tiene valores complejos (ej. COMSOL exporta "1.2+3.4i"):
#   True  -> se grafica la parte REAL
#   False -> se grafica la parte IMAGINARIA
# Si los valores son reales (caso normal), esta opcion no tiene efecto.
GRAFICAR_PARTE_REAL = True


# ---------------------------------------------------------------------------
# Seleccion de archivo (interfaz grafica)
# ---------------------------------------------------------------------------

def elegir_archivos():
    import tkinter as tk
    from tkinter import filedialog

    carpeta_inicial = CARPETA_POR_DEFECTO if os.path.isdir(CARPETA_POR_DEFECTO) else os.getcwd()

    root = tk.Tk()
    root.withdraw()
    rutas = filedialog.askopenfilenames(
        title="Selecciona uno o varios archivos .txt a graficar (Ctrl/Shift + clic)",
        initialdir=carpeta_inicial,
        filetypes=[("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")],
    )
    root.destroy()

    if not rutas:
        raise SystemExit("No se selecciono ningun archivo. Se cerro el programa.")

    return list(rutas)


# ---------------------------------------------------------------------------
# Lectura y deteccion de formato / nombres de columnas
# ---------------------------------------------------------------------------

def detectar_nombres_columnas_comsol(lineas_crudas):
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


def parsear_valor(texto):
    """Parsea un numero que puede ser real o complejo, como los que a veces
    exporta COMSOL, ej: '1.2+3.4i' o '1.2-3.4i'. Devuelve float si es real,
    o complex si tiene parte imaginaria."""
    texto = texto.strip()
    try:
        return float(texto)
    except ValueError:
        pass
    # Intenta como complejo (COMSOL usa 'i', Python usa 'j')
    return complex(texto.replace("i", "j"))


def leer_formato_agrupado(lineas_datos, nombres_columnas):
    """Formato COMSOL original: N columnas numericas, con varias filas
    consecutivas (una por estado propio) para cada valor de la primera
    columna. Agrupa por bloques y arma una rama por posicion dentro del
    bloque."""
    filas = []
    n_cols_esperadas = None
    for linea in lineas_datos:
        valores = linea.split()
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
    n_cols = datos.shape[1]

    # Columnas X e Y: se toman de la CONFIGURACION del inicio del codigo
    # (COLUMNA_X, COLUMNA_Y), numeradas empezando en 1.
    idx_x = COLUMNA_X - 1
    idx_y = COLUMNA_Y - 1
    if idx_x < 0 or idx_x >= n_cols or idx_y < 0 or idx_y >= n_cols:
        raise ValueError(
            f"El archivo tiene {n_cols} columnas, pero se configuro "
            f"COLUMNA_X={COLUMNA_X} y COLUMNA_Y={COLUMNA_Y} (fuera de rango)."
        )

    x_col = datos[:, idx_x].real  # el eje X siempre se asume real (posicion, etc.)

    y_col_complejo = datos[:, idx_y]
    hay_parte_imaginaria = np.any(y_col_complejo.imag != 0)
    y_col = y_col_complejo.real if GRAFICAR_PARTE_REAL else y_col_complejo.imag

    x_redondeado = np.round(x_col, 6)

    x0_unicos, bloques = [], []
    x_actual, bloque_actual = None, []
    for xv, yv in zip(x_redondeado, y_col):
        if x_actual is None or xv != x_actual:
            if x_actual is not None:
                x0_unicos.append(x_actual)
                bloques.append(bloque_actual)
            x_actual, bloque_actual = xv, [yv]
        else:
            bloque_actual.append(yv)
    if x_actual is not None:
        x0_unicos.append(x_actual)
        bloques.append(bloque_actual)

    n_ramas = max(len(b) for b in bloques)
    ramas = np.full((n_ramas, len(x0_unicos)), np.nan)
    for j, bloque in enumerate(bloques):
        for i, v in enumerate(bloque):
            ramas[i, j] = v

    etiquetas = [f"Estado {i + 1}" for i in range(n_ramas)]

    nombre_x = nombres_columnas[idx_x] if (nombres_columnas and idx_x < len(nombres_columnas)) else f"Columna {COLUMNA_X}"
    if nombres_columnas and idx_y < len(nombres_columnas):
        nombre_y = nombres_columnas[idx_y]
    else:
        nombre_y = "Energia"

    if hay_parte_imaginaria:
        nombre_y += " (parte real)" if GRAFICAR_PARTE_REAL else " (parte imaginaria)"

    return np.array(x0_unicos), ramas, etiquetas, nombre_x, nombre_y


def leer_formato_ancho(lineas_datos, lineas_crudas=None):
    """Formato ya exportado (columnas): primera fila es encabezado con
    nombres, cada columna siguiente ya es una rama/estado.

    Si el archivo trae una linea de comentario '% EJE_X: ... EJE_Y: ...'
    (como la que escribe seleccionar_y_exportar_barrido.py), se usan esos
    nombres reales para los ejes en vez de un nombre generico."""
    encabezado = lineas_datos[0]
    separador = "\t" if "\t" in encabezado else None
    columnas = [c.strip() for c in encabezado.split(separador) if c.strip() != ""]

    if len(columnas) < 2:
        raise ValueError("El encabezado del archivo no tiene columnas reconocibles.")

    nombre_x = columnas[0]
    etiquetas = columnas[1:]

    filas = []
    for linea in lineas_datos[1:]:
        partes = linea.split(separador)
        partes = [p.strip() for p in partes]
        if len(partes) != len(columnas):
            continue  # fila mal formada, se ignora
        try:
            fila = [float(p) if p != "" else np.nan for p in partes]
        except ValueError:
            continue
        filas.append(fila)

    if not filas:
        raise ValueError("No se encontraron filas de datos numericas validas en el archivo.")

    tabla = np.array(filas)
    x0_unicos = tabla[:, 0]
    ramas = tabla[:, 1:].T

    nombre_y = "Valor"
    m = re.search(r"\(([^)]+)\)", etiquetas[0])
    if m:
        nombre_y = f"Valor ({m.group(1)})"

    # Buscar la linea "% EJE_X: ... EJE_Y: ..." escrita por
    # seleccionar_y_exportar_barrido.py, y usar esos nombres reales si existe.
    if lineas_crudas:
        for linea in lineas_crudas:
            l = linea.strip()
            if l.startswith("%") and "EJE_X:" in l and "EJE_Y:" in l:
                m_x = re.search(r"EJE_X:\s*(.*?)\s*(?:\t|EJE_Y:)", l)
                m_y = re.search(r"EJE_Y:\s*(.*)$", l)
                if m_x:
                    nombre_x = m_x.group(1).strip()
                if m_y:
                    nombre_y = m_y.group(1).strip()
                break

    return x0_unicos, ramas, etiquetas, nombre_x, nombre_y


def limpiar_nombre_archivo(ruta_archivo):
    """Convierte el nombre de archivo en una etiqueta legible para el eje X,
    ej: 'energia_barrido_proton.txt' -> 'energia barrido proton'."""
    base = os.path.splitext(os.path.basename(ruta_archivo))[0]
    base = base.replace("_", " ").strip()
    return base


def extraer_unidad(texto):
    """Extrae lo que este entre parentesis en un texto, ej:
    'Energia propia (eV)' -> 'eV'. Devuelve None si no encuentra nada."""
    if not texto:
        return None
    m = re.search(r"\(([^)]+)\)", texto)
    return m.group(1) if m else None


def cargar_archivo(ruta_archivo):
    with open(ruta_archivo, "r", encoding="utf-8", errors="ignore") as f:
        lineas_crudas = [l.rstrip("\n") for l in f]

    nombres_columnas = detectar_nombres_columnas_comsol(lineas_crudas)

    lineas_datos = [l.strip() for l in lineas_crudas
                     if l.strip() and not l.strip().startswith("%")]

    if not lineas_datos:
        raise ValueError("El archivo no contiene filas de datos.")

    primera_linea = lineas_datos[0]
    primer_token = primera_linea.split("\t")[0] if "\t" in primera_linea else primera_linea.split()[0]

    try:
        float(primer_token)
        es_formato_ancho = False
    except ValueError:
        es_formato_ancho = True

    if es_formato_ancho:
        x0_unicos, ramas, etiquetas, nombre_x_col, nombre_y_col = leer_formato_ancho(lineas_datos, lineas_crudas)
    else:
        x0_unicos, ramas, etiquetas, nombre_x_col, nombre_y_col = leer_formato_agrupado(lineas_datos, nombres_columnas)

    # Eje X: se nombra segun el archivo, no segun el nombre de columna.
    nombre_x = limpiar_nombre_archivo(ruta_archivo)

    # Eje Y: se nombra segun la unidad detectada (lo que este entre
    # parentesis, ej "eV", "nm"...). Si no se detecta ninguna unidad, se
    # deja el nombre de columna tal cual como respaldo.
    unidad = extraer_unidad(nombre_y_col)
    if not unidad and etiquetas:
        unidad = extraer_unidad(etiquetas[0])
    nombre_y = f"Valor ({unidad})" if unidad else nombre_y_col

    return x0_unicos, ramas, etiquetas, nombre_x, nombre_y


# ---------------------------------------------------------------------------
# Seleccion de estados (segun configuracion del inicio del codigo)
# ---------------------------------------------------------------------------

def obtener_indices_estados(etiquetas, nombre_archivo=""):
    """Decide que estados graficar segun la CONFIGURACION del inicio del
    codigo (MODO_SELECCION_ESTADOS). Solo abre una ventana si el modo es
    'elegir'; en los otros modos no se pregunta nada por interfaz."""
    n_estados = len(etiquetas)

    if MODO_SELECCION_ESTADOS == "todos":
        return list(range(n_estados))

    elif MODO_SELECCION_ESTADOS == "numero":
        n = min(NUMERO_ESTADOS, n_estados)
        if NUMERO_ESTADOS > n_estados:
            print(f"Aviso: '{nombre_archivo}' solo tiene {n_estados} estados "
                  f"(se pidieron {NUMERO_ESTADOS}); se graficaran los {n} disponibles.")
        return list(range(n))

    elif MODO_SELECCION_ESTADOS == "elegir":
        return elegir_estados_gui(etiquetas, nombre_archivo)

    else:
        raise ValueError(
            f"MODO_SELECCION_ESTADOS invalido: '{MODO_SELECCION_ESTADOS}'. "
            f"Usa 'todos', 'numero' o 'elegir'."
        )


# ---------------------------------------------------------------------------
# Seleccion de estados (interfaz grafica, solo se usa en modo 'elegir')
# ---------------------------------------------------------------------------

def elegir_estados_gui(etiquetas, nombre_archivo=""):
    import tkinter as tk
    from tkinter import messagebox

    seleccion = []

    root = tk.Tk()
    titulo_ventana = "Selecciona los estados a graficar"
    if nombre_archivo:
        titulo_ventana += f" - {nombre_archivo}"
    root.title(titulo_ventana)

    tk.Label(
        root,
        text="Selecciona uno o mas estados\n(clic + Ctrl o Shift para varios; todos vienen preseleccionados):",
        justify="left",
    ).pack(padx=10, pady=(10, 5))

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=5, fill="both", expand=True)

    scrollbar = tk.Scrollbar(frame, orient="vertical")
    listbox = tk.Listbox(
        frame, selectmode=tk.EXTENDED, width=40,
        height=min(15, len(etiquetas)), yscrollcommand=scrollbar.set,
    )
    scrollbar.config(command=listbox.yview)
    scrollbar.pack(side="right", fill="y")
    listbox.pack(side="left", fill="both", expand=True)

    for et in etiquetas:
        listbox.insert(tk.END, et)
    listbox.select_set(0, tk.END)

    def confirmar():
        idxs = list(listbox.curselection())
        if not idxs:
            messagebox.showwarning("Aviso", "Selecciona al menos un estado.")
            return
        seleccion.extend(idxs)
        root.destroy()

    tk.Button(root, text="Graficar", command=confirmar).pack(pady=10)
    root.mainloop()

    if not seleccion:
        raise SystemExit("No se selecciono ningun estado. Se cerro el programa.")

    return seleccion


# ---------------------------------------------------------------------------
# Graficado
# ---------------------------------------------------------------------------

def graficar(x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo):
    """Grafica un solo archivo en una figura individual."""
    plt.figure(figsize=(9, 6))
    for idx in indices:
        plt.plot(x0_unicos, ramas[idx, :], linestyle="-", linewidth=1.8,
                  label=etiquetas[idx])

    plt.xlabel(nombre_x)
    plt.ylabel(nombre_y)
    plt.title(titulo)
    plt.legend(loc="best", fontsize=8, ncol=2)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def graficar_mosaico(resultados):
    """Grafica varios archivos en una sola figura tipo mosaico (una
    subgrafica por archivo). 'resultados' es una lista de tuplas:
    (x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo)."""
    n = len(resultados)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)

    fig, axes = plt.subplots(rows, cols, figsize=(5.5 * cols, 4.2 * rows), squeeze=False)
    axes_planas = axes.reshape(-1)

    for ax, resultado in zip(axes_planas, resultados):
        x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo = resultado
        for idx in indices:
            ax.plot(x0_unicos, ramas[idx, :], linestyle="-", linewidth=1.5,
                     label=etiquetas[idx])
        ax.set_xlabel(nombre_x, fontsize=9)
        ax.set_ylabel(nombre_y, fontsize=9)
        ax.set_title(titulo, fontsize=10)
        ax.legend(loc="best", fontsize=6, ncol=2)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)

    # ocultar subgraficas sobrantes si n no llena la cuadricula
    for ax_vacio in axes_planas[n:]:
        ax_vacio.axis("off")

    plt.tight_layout()
    plt.show()


def main():
    rutas_archivos = elegir_archivos()

    resultados = []
    for ruta_archivo in rutas_archivos:
        nombre_archivo = os.path.basename(ruta_archivo)
        try:
            x0_unicos, ramas, etiquetas, nombre_x, nombre_y = cargar_archivo(ruta_archivo)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Error al leer el archivo", f"{nombre_archivo}:\n{e}")
            continue  # sigue con los demas archivos en vez de detener todo

        print(f"Archivo: {ruta_archivo}")
        print(f"  Eje X detectado: {nombre_x}")
        print(f"  Eje Y detectado: {nombre_y}")
        print(f"  {len(x0_unicos)} valores en el eje X y {ramas.shape[0]} estados.")

        indices = obtener_indices_estados(etiquetas, nombre_archivo)

        resultados.append((x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, nombre_archivo))

    if not resultados:
        raise SystemExit("Ningun archivo se pudo leer correctamente.")

    if len(resultados) == 1:
        x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo = resultados[0]
        graficar(x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo)
    else:
        graficar_mosaico(resultados)


if __name__ == "__main__":
    main()