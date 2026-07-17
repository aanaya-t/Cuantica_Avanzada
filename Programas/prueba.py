"""
Script UNIFICADO para graficar barridos parametricos de COMSOL (Schrodinger).

Que hace:
  1) Abre una ventana para elegir uno o varios archivos .txt.
  2) Para cada archivo, DETECTA AUTOMATICAMENTE si es:
       - Un BARRIDO SIMPLE (una sola variable, ej. x_0): grafica lineas
         Energia vs esa variable, una linea por estado propio. Si eliges
         varios archivos de este tipo, los junta en un MOSAICO.
       - Un BARRIDO DOBLE (dos variables, ej. B y n): arma una rejilla y
         grafica, en una misma ventana, una superficie 3D (rotable con el
         mouse) y un mapa de colores 2D equivalente. Como una superficie
         solo puede mostrar UN estado a la vez, te deja ELEGIR cual
         estado/superficie quieres ver (segun la configuracion).
       - El formato "ancho" ya exportado por seleccionar_y_exportar_barrido.py
         (una columna por estado): se grafica como barrido simple.
  3) Los nombres de los ejes salen del propio archivo (encabezado '%' de
     COMSOL, nombre del archivo, o unidad detectada), no estan fijos.
  4) Soporta valores complejos (formato COMSOL "a+bi") y deja elegir si se
     grafica la parte real o imaginaria.
  5) Es tolerante a filas mal formadas, columnas de distinto tamano, etc.

PENDIENTE (a futuro, todavia no implementado):
  - Tracking de estados por continuidad (energia o solapamiento) entre
    combinaciones vecinas de la rejilla, en vez de tomar el estado por
    posicion fija dentro de cada bloque. Ver la funcion
    trackear_por_continuidad() al final del archivo.

Uso:
    python graficar_barrido_todo_en_uno.py
"""

import os
import re
import math
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (habilita projection="3d")

# =============================================================================
# CONFIGURACION (editar aqui, no se pregunta por interfaz)
# =============================================================================

# Carpeta donde estan tus .txt (se abre ahi la ventana de seleccion de archivo)
CARPETA_POR_DEFECTO = r"C:\Users\Admin\Documents\Cuantica_Avanzada\Tablas"

# Columnas del archivo (numeracion normal, empezando en 1).
#   - En un barrido SIMPLE solo se usan COLUMNA_X y COLUMNA_VALOR.
#   - En un barrido DOBLE se usan las tres (COLUMNA_VAR2 es la 2da variable).
COLUMNA_X = 1        # variable barrida "externa" (o la unica, si es simple)
COLUMNA_VAR2 = 2     # variable barrida "interna" (solo aplica si hay doble barrido)
COLUMNA_VALOR = 3    # columna a graficar (ej. Energia propia)

# Si la columna de valor tiene numeros complejos (formato COMSOL "a+bi"):
#   True  -> se grafica la parte REAL / False -> se grafica la parte IMAGINARIA
GRAFICAR_PARTE_REAL = True

# --- Config. especifica de BARRIDO SIMPLE (graficas de linea) ---
# Modo de seleccion de ESTADOS a graficar, para cada archivo:
#   "todos"  -> grafica todos los estados detectados
#   "numero" -> grafica los primeros NUMERO_ESTADOS estados
#   "elegir" -> abre una ventana para elegir los estados a mano (por archivo)
MODO_SELECCION_ESTADOS = "todos"  # "todos" | "numero" | "elegir"
NUMERO_ESTADOS = 5                  # se usa solo si el modo es "numero"

# --- Config. especifica de BARRIDO DOBLE (superficie 3D + mapa 2D) ---
# Como una superficie solo puede mostrar un estado a la vez:
#   "elegir" -> abre una ventana para elegir cual estado/superficie ver
#   "numero" -> usa directamente ESTADO_A_GRAFICAR_3D, sin preguntar
MODO_SELECCION_ESTADO_3D = "elegir"  # "numero" | "elegir"
ESTADO_A_GRAFICAR_3D = 1              # se usa solo si el modo es "numero"


# =============================================================================
# Utilidades comunes (parseo, deteccion de nombres, archivo)
# =============================================================================

def parsear_valor(texto):
    """Parsea un numero real o complejo (COMSOL usa 'i', Python usa 'j')."""
    texto = texto.strip()
    try:
        return float(texto)
    except ValueError:
        pass
    return complex(texto.replace("i", "j"))


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


def limpiar_nombre_archivo(ruta_archivo):
    """Convierte el nombre de archivo en una etiqueta legible para el eje X,
    ej: 'energia_barrido_proton.txt' -> 'energia barrido proton'."""
    base = os.path.splitext(os.path.basename(ruta_archivo))[0]
    return base.replace("_", " ").strip()


def extraer_unidad(texto):
    """Extrae lo que este entre parentesis en un texto, ej:
    'Energia propia (eV)' -> 'eV'. Devuelve None si no encuentra nada."""
    if not texto:
        return None
    m = re.search(r"\(([^)]+)\)", texto)
    return m.group(1) if m else None


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


# =============================================================================
# Lectura: formato ancho (ya exportado, una columna por estado)
# =============================================================================

def leer_formato_ancho(lineas_datos, lineas_crudas=None):
    encabezado = lineas_datos[0]
    separador = "\t" if "\t" in encabezado else None
    columnas = [c.strip() for c in encabezado.split(separador) if c.strip() != ""]

    if len(columnas) < 2:
        raise ValueError("El encabezado del archivo no tiene columnas reconocibles.")

    nombre_x = columnas[0]
    etiquetas = columnas[1:]

    filas = []
    for linea in lineas_datos[1:]:
        partes = [p.strip() for p in linea.split(separador)]
        if len(partes) != len(columnas):
            continue
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


# =============================================================================
# Lectura: formato crudo de COMSOL (con soporte para 1 o 2 variables barridas)
# =============================================================================

def leer_filas_numericas(lineas_datos):
    """Parsea todas las filas de datos (reales o complejas), descartando
    las que no coincidan en numero de columnas con la mayoria."""
    filas = []
    n_cols_esperadas = None
    for linea in lineas_datos:
        valores = linea.split()
        try:
            fila = [parsear_valor(v) for v in valores]
        except ValueError:
            continue
        if not fila:
            continue
        if n_cols_esperadas is None:
            n_cols_esperadas = len(fila)
        if len(fila) != n_cols_esperadas:
            continue
        filas.append(fila)

    if not filas:
        raise ValueError("No se encontraron filas de datos numericas validas en el archivo.")

    return np.array(filas, dtype=complex)


def agrupar_por_dos_variables(datos, idx_x, idx_v2, idx_val, decimales=6):
    """Agrupa las filas por combinacion (var_x, var2), en el orden en que
    aparecen. Devuelve una lista de bloques (x_val, v2_val, [valores]) y si
    se detecto parte imaginaria distinta de cero en la columna de valor."""
    x_col = np.round(datos[:, idx_x].real, decimales)
    v2_col = np.round(datos[:, idx_v2].real, decimales)
    val_col_complejo = datos[:, idx_val]
    val_col = val_col_complejo.real if GRAFICAR_PARTE_REAL else val_col_complejo.imag
    hay_parte_imaginaria = bool(np.any(val_col_complejo.imag != 0))

    bloques = []
    actual = None
    valores_actual = []
    for xv, v2, val in zip(x_col, v2_col, val_col):
        clave = (xv, v2)
        if actual is None or clave != actual:
            if actual is not None:
                bloques.append((actual[0], actual[1], valores_actual))
            actual = clave
            valores_actual = [val]
        else:
            valores_actual.append(val)
    if actual is not None:
        bloques.append((actual[0], actual[1], valores_actual))

    return bloques, hay_parte_imaginaria


def es_doble_barrido(bloques):
    """Determina si realmente hay 2 variables barridas. No basta con que
    cada bloque de var_x tenga varios valores de var2 (eso tambien pasa si
    var2 es, por ejemplo, una columna tipo 'lambda' que cambia con cada
    estado); ademas se exige que el MISMO conjunto de valores de var2 se
    repita en la mayoria de los bloques de var_x, como corresponde a una
    rejilla real de barrido doble (ej. B x n)."""
    x_valores = sorted(set(b[0] for b in bloques))
    v2_valores_totales = sorted(set(b[1] for b in bloques))

    if len(x_valores) <= 1 or len(v2_valores_totales) <= 1:
        return False, x_valores, v2_valores_totales

    conjuntos_por_x = {}
    for xv, v2, _ in bloques:
        conjuntos_por_x.setdefault(xv, set()).add(v2)

    conjuntos = list(conjuntos_por_x.values())
    tamanos = [len(c) for c in conjuntos]
    tiene_varios_v2 = float(np.median(tamanos)) > 1

    referencia = conjuntos[0]
    coincidencias = sum(1 for c in conjuntos if c == referencia)
    proporcion_coincidencia = coincidencias / len(conjuntos)

    es_doble = tiene_varios_v2 and proporcion_coincidencia >= 0.8

    return es_doble, x_valores, v2_valores_totales


def armar_ramas_barrido_simple(bloques):
    """A partir de los bloques (agrupados por (x, v2), pero v2 se ignora
    porque es barrido simple), arma x0_unicos y la matriz de ramas, igual
    que en el barrido de una sola variable."""
    x0_unicos = []
    listas_valores = []
    x_actual = None
    valores_actual = []

    for xv, _v2, valores in bloques:
        if x_actual is None or xv != x_actual:
            if x_actual is not None:
                x0_unicos.append(x_actual)
                listas_valores.append(valores_actual)
            x_actual = xv
            valores_actual = list(valores)
        else:
            valores_actual.extend(valores)
    if x_actual is not None:
        x0_unicos.append(x_actual)
        listas_valores.append(valores_actual)

    n_ramas = max(len(v) for v in listas_valores)
    ramas = np.full((n_ramas, len(x0_unicos)), np.nan)
    for j, valores in enumerate(listas_valores):
        for i, v in enumerate(valores):
            ramas[i, j] = v

    return np.array(x0_unicos), ramas


def construir_grilla(bloques, x_valores, v2_valores, estado_idx):
    """Arma la matriz Z[i, j] usando el estado 'estado_idx' (0-indexado) de
    cada bloque (x[i], v2[j]). Si falta el bloque o el estado no existe
    ahi, deja NaN."""
    idx_x = {v: i for i, v in enumerate(x_valores)}
    idx_v2 = {v: j for j, v in enumerate(v2_valores)}

    Z = np.full((len(x_valores), len(v2_valores)), np.nan)
    for xv, v2, valores in bloques:
        i = idx_x[xv]
        j = idx_v2[v2]
        if 0 <= estado_idx < len(valores):
            Z[i, j] = valores[estado_idx]

    return Z


# =============================================================================
# Carga unificada de un archivo: decide formato y tipo de barrido
# =============================================================================

def procesar_archivo(ruta_archivo):
    nombre_archivo = os.path.basename(ruta_archivo)

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

    # --- Formato ancho (ya exportado): siempre es barrido simple ---
    if es_formato_ancho:
        x0_unicos, ramas, etiquetas, nombre_x_col, nombre_y_col = leer_formato_ancho(lineas_datos, lineas_crudas)
        nombre_x = limpiar_nombre_archivo(ruta_archivo)
        unidad = extraer_unidad(nombre_y_col) or (extraer_unidad(etiquetas[0]) if etiquetas else None)
        nombre_y = f"Valor ({unidad})" if unidad else nombre_y_col
        return {
            "tipo": "simple", "x": x0_unicos, "ramas": ramas, "etiquetas": etiquetas,
            "nombre_x": nombre_x, "nombre_y": nombre_y, "nombre_archivo": nombre_archivo,
        }

    # --- Formato crudo de COMSOL: parsear y detectar simple vs doble ---
    datos = leer_filas_numericas(lineas_datos)
    n_cols = datos.shape[1]

    idx_x, idx_v2, idx_val = COLUMNA_X - 1, COLUMNA_VAR2 - 1, COLUMNA_VALOR - 1
    for idx, nombre in [(idx_x, "COLUMNA_X"), (idx_val, "COLUMNA_VALOR")]:
        if idx < 0 or idx >= n_cols:
            raise ValueError(f"{nombre} esta fuera de rango (el archivo tiene {n_cols} columnas).")
    idx_v2_valido = 0 <= idx_v2 < n_cols

    if idx_v2_valido:
        bloques, hay_parte_imaginaria = agrupar_por_dos_variables(datos, idx_x, idx_v2, idx_val)
        es_doble, x_valores, v2_valores = es_doble_barrido(bloques)
    else:
        bloques, hay_parte_imaginaria = agrupar_por_dos_variables(datos, idx_x, idx_x, idx_val)
        es_doble, x_valores, v2_valores = False, [], []

    nombre_x_col = nombres_columnas[idx_x] if nombres_columnas and idx_x < len(nombres_columnas) else f"Columna {COLUMNA_X}"
    nombre_valor = nombres_columnas[idx_val] if nombres_columnas and idx_val < len(nombres_columnas) else f"Columna {COLUMNA_VALOR}"
    if hay_parte_imaginaria:
        nombre_valor += " (parte real)" if GRAFICAR_PARTE_REAL else " (parte imaginaria)"

    if es_doble:
        nombre_var2 = nombres_columnas[idx_v2] if nombres_columnas and idx_v2 < len(nombres_columnas) else f"Columna {COLUMNA_VAR2}"
        return {
            "tipo": "doble", "bloques": bloques, "x_valores": x_valores, "v2_valores": v2_valores,
            "nombre_x": nombre_x_col, "nombre_var2": nombre_var2, "nombre_valor": nombre_valor,
            "nombre_archivo": nombre_archivo,
        }

    x0_unicos, ramas = armar_ramas_barrido_simple(bloques)
    etiquetas = [f"Estado {i + 1}" for i in range(ramas.shape[0])]
    nombre_x = limpiar_nombre_archivo(ruta_archivo)
    unidad = extraer_unidad(nombre_valor)
    nombre_y = f"Valor ({unidad})" if unidad else nombre_valor

    return {
        "tipo": "simple", "x": x0_unicos, "ramas": ramas, "etiquetas": etiquetas,
        "nombre_x": nombre_x, "nombre_y": nombre_y, "nombre_archivo": nombre_archivo,
    }


# =============================================================================
# Seleccion de estados (barrido simple) / estado unico (barrido doble)
# =============================================================================

def obtener_indices_estados(etiquetas, nombre_archivo=""):
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
        raise ValueError(f"MODO_SELECCION_ESTADOS invalido: '{MODO_SELECCION_ESTADOS}'.")


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
    listbox = tk.Listbox(frame, selectmode=tk.EXTENDED, width=40,
                           height=min(15, len(etiquetas)), yscrollcommand=scrollbar.set)
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


def obtener_estado_3d(n_estados_disponibles, nombre_archivo=""):
    """Devuelve el indice (0-indexado) del estado a graficar como
    superficie, segun MODO_SELECCION_ESTADO_3D."""
    if MODO_SELECCION_ESTADO_3D == "numero":
        idx = min(max(ESTADO_A_GRAFICAR_3D, 1), n_estados_disponibles) - 1
        return idx
    elif MODO_SELECCION_ESTADO_3D == "elegir":
        return elegir_estado_3d_gui(n_estados_disponibles, nombre_archivo)
    else:
        raise ValueError(f"MODO_SELECCION_ESTADO_3D invalido: '{MODO_SELECCION_ESTADO_3D}'.")


def elegir_estado_3d_gui(n_estados_disponibles, nombre_archivo=""):
    import tkinter as tk
    from tkinter import messagebox

    seleccion = []
    root = tk.Tk()
    titulo_ventana = "Elige el estado/superficie a graficar"
    if nombre_archivo:
        titulo_ventana += f" - {nombre_archivo}"
    root.title(titulo_ventana)

    tk.Label(
        root,
        text="Elige UN estado (la superficie solo puede mostrar uno a la vez):",
        justify="left",
    ).pack(padx=10, pady=(10, 5))

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=5, fill="both", expand=True)
    scrollbar = tk.Scrollbar(frame, orient="vertical")
    listbox = tk.Listbox(frame, selectmode=tk.BROWSE, width=40,
                           height=min(15, n_estados_disponibles), yscrollcommand=scrollbar.set)
    scrollbar.config(command=listbox.yview)
    scrollbar.pack(side="right", fill="y")
    listbox.pack(side="left", fill="both", expand=True)
    for i in range(n_estados_disponibles):
        listbox.insert(tk.END, f"Estado {i + 1}")
    listbox.select_set(0)

    def confirmar():
        idxs = listbox.curselection()
        if not idxs:
            messagebox.showwarning("Aviso", "Selecciona un estado.")
            return
        seleccion.append(idxs[0])
        root.destroy()

    tk.Button(root, text="Graficar", command=confirmar).pack(pady=10)
    root.mainloop()

    if not seleccion:
        raise SystemExit("No se selecciono ningun estado. Se cerro el programa.")
    return seleccion[0]


# =============================================================================
# Graficado
# =============================================================================

def graficar_linea(x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo):
    plt.figure(figsize=(9, 6))
    for idx in indices:
        plt.plot(x0_unicos, ramas[idx, :], linestyle="-", linewidth=1.8, label=etiquetas[idx])
    plt.xlabel(nombre_x)
    plt.ylabel(nombre_y)
    plt.title(titulo)
    plt.legend(loc="best", fontsize=8, ncol=2)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def graficar_mosaico_lineas(resultados):
    n = len(resultados)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)

    fig, axes = plt.subplots(rows, cols, figsize=(5.5 * cols, 4.2 * rows), squeeze=False)
    axes_planas = axes.reshape(-1)

    for ax, resultado in zip(axes_planas, resultados):
        x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo = resultado
        for idx in indices:
            ax.plot(x0_unicos, ramas[idx, :], linestyle="-", linewidth=1.5, label=etiquetas[idx])
        ax.set_xlabel(nombre_x, fontsize=9)
        ax.set_ylabel(nombre_y, fontsize=9)
        ax.set_title(titulo, fontsize=10)
        ax.legend(loc="best", fontsize=6, ncol=2)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)

    for ax_vacio in axes_planas[n:]:
        ax_vacio.axis("off")

    plt.tight_layout()
    plt.show()


def graficar_doble(x_valores, v2_valores, Z, nombre_x, nombre_var2, nombre_valor, titulo):
    X, Y = np.meshgrid(v2_valores, x_valores)  # forma (len(x_valores), len(v2_valores)) = forma de Z

    fig = plt.figure(figsize=(14, 6))
    fig.suptitle(titulo)

    ax3d = fig.add_subplot(1, 2, 1, projection="3d")
    superficie = ax3d.plot_surface(X, Y, Z, cmap="viridis", edgecolor="none")
    ax3d.set_xlabel(nombre_var2)
    ax3d.set_ylabel(nombre_x)
    ax3d.set_zlabel(nombre_valor)
    ax3d.set_title("Superficie 3D")
    fig.colorbar(superficie, ax=ax3d, shrink=0.6, pad=0.1)

    ax2d = fig.add_subplot(1, 2, 2)
    mapa = ax2d.pcolormesh(X, Y, Z, cmap="viridis", shading="auto")
    ax2d.set_xlabel(nombre_var2)
    ax2d.set_ylabel(nombre_x)
    ax2d.set_title("Mapa de colores 2D")
    fig.colorbar(mapa, ax=ax2d, label=nombre_valor)

    plt.tight_layout()
    plt.show()


# =============================================================================
# PENDIENTE (a futuro): tracking de estados por continuidad
# =============================================================================

def trackear_por_continuidad(bloques, x_valores, v2_valores):
    """PENDIENTE (a futuro, todavia NO implementado).

    Idea: en vez de tomar el estado propio por su POSICION fija dentro de
    cada bloque (var_x, var2) -- que puede cruzarse o reordenarse entre
    combinaciones vecinas de la rejilla -- esta funcion deberia seguir cada
    estado por continuidad (ej. energia mas cercana, o mayor solapamiento
    de funcion de onda) entre bloques vecinos, para armar superficies
    suaves y consistentes aunque COMSOL reordene los estados.

    No se llama desde ningun lado todavia; queda como referencia para
    cuando se retome esta mejora.
    """
    raise NotImplementedError("Tracking por continuidad: pendiente para una futura version.")


# =============================================================================
# Main
# =============================================================================

def main():
    rutas_archivos = elegir_archivos()

    resultados_simples = []

    for ruta_archivo in rutas_archivos:
        nombre_archivo = os.path.basename(ruta_archivo)
        try:
            info = procesar_archivo(ruta_archivo)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Error al leer el archivo", f"{nombre_archivo}:\n{e}")
            continue

        if info["tipo"] == "doble":
            n_estados_disp = max(len(v) for (_, _, v) in info["bloques"])
            print(f"{nombre_archivo}: DOBLE barrido detectado "
                  f"({info['nombre_x']} x {info['nombre_var2']}), {n_estados_disp} estados disponibles.")

            estado_idx = obtener_estado_3d(n_estados_disp, nombre_archivo)
            Z = construir_grilla(info["bloques"], info["x_valores"], info["v2_valores"], estado_idx)

            n_nan = int(np.isnan(Z).sum())
            if n_nan:
                print(f"Aviso: {n_nan} combinaciones no tienen el estado #{estado_idx + 1} (quedan como huecos).")

            graficar_doble(
                info["x_valores"], info["v2_valores"], Z,
                info["nombre_x"], info["nombre_var2"], info["nombre_valor"],
                titulo=f"{nombre_archivo} - Estado {estado_idx + 1}",
            )

        else:
            print(f"{nombre_archivo}: barrido simple detectado "
                  f"({info['ramas'].shape[0]} estados, eje X: {info['nombre_x']}, eje Y: {info['nombre_y']}).")
            indices = obtener_indices_estados(info["etiquetas"], nombre_archivo)
            resultados_simples.append((
                info["x"], info["ramas"], info["etiquetas"], indices,
                info["nombre_x"], info["nombre_y"], nombre_archivo,
            ))

    if resultados_simples:
        if len(resultados_simples) == 1:
            graficar_linea(*resultados_simples[0])
        else:
            graficar_mosaico_lineas(resultados_simples)


if __name__ == "__main__":
    main()