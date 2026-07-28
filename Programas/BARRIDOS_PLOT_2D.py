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
from matplotlib.patches import Ellipse

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
NUMERO_ESTADOS = 25

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

# =============================================================================
# CONFIGURACION DE LA GEOMETRIA (panel del disco cuantico junto al grafico)
# =============================================================================

# Ancho y alto del RECTANGULO del dominio de simulacion, en nm (el borde
# exterior de tu geometria). No depende de a, b, R1, R2 ni R3.
GEOM_DOMINIO_ANCHO_NM = 100.0
GEOM_DOMINIO_ALTO_NM = 120.0

# Radios de las capas concentricas del disco (los 3 circulos), en nm. Son
# los valores "por defecto" que se usan para dibujar cuando ese radio NO es
# la variable que se esta barriendo en el archivo (si lo es, se dibuja
# resaltado y con el rango real recorrido, ver GEOM_MOSTRAR_RANGO_BARRIDO).
GEOM_R1_NM = 12.0
GEOM_R2_NM = 20.0
GEOM_R3_NM = 25.0

# Semiejes (a, b) de la SUPERELIPSE de la impureza coulombiana (el proton)
# en el centro, en nm.
GEOM_A_NM = 9.0
GEOM_B_NM = 9.0

# Exponente de la superelipse: |x/a|^n + |y/b|^n = 1.
#   n = 1   -> diamante (rombo), como en tu geometria real
#   n = 2   -> elipse comun
#   n grande (ej. 6-10) -> se ve casi como un rectangulo redondeado
GEOM_SUPERELIPSE_N = 1

# Posicion del proton sobre el eje x, en nm (se usa cuando la posicion NO
# es la variable barrida en el archivo).
GEOM_X0_NM = 0.0

# Si True, ademas de resaltar la variable barrida, se sombrea/marca el
# rango minimo-maximo real que recorre el barrido (leido del propio
# archivo). Si False, solo se resalta cual variable es la barrida.
GEOM_MOSTRAR_RANGO_BARRIDO = True

# Deteccion automatica de cual parametro se esta barriendo en cada archivo,
# a partir del nombre del eje X / nombre del archivo. Si la deteccion falla
# o quieres forzarla (por ejemplo, en archivos con encabezados ambiguos
# como "vs F N1/N2/N3", cuya columna quedo mal etiquetada como x_0), pon
# aqui manualmente uno de: "R1", "R2", "R3", "x0", "F", "B", o None para
# dejar la deteccion automatica.
VARIABLE_BARRIDA_MANUAL = None


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
# Deteccion de la variable barrida y dibujo del panel de geometria
# ---------------------------------------------------------------------------

def detectar_variable_barrida(nombre_x, nombre_archivo):
    """Intenta adivinar cual parametro fisico se esta barriendo en el
    archivo, a partir del nombre del eje X detectado y del nombre del
    archivo. Devuelve uno de: 'R1', 'R2', 'R3', 'x0', 'F', 'B', o None si
    no se pudo determinar (en ese caso se dibuja la geometria con los
    valores por defecto de la CONFIGURACION, sin nada resaltado).

    Si VARIABLE_BARRIDA_MANUAL esta definido en la CONFIGURACION, se usa
    ese valor directamente y no se intenta adivinar nada (util para
    archivos con encabezados ambiguos, como los que quedaron con la
    columna mal etiquetada 'x_0(nm)' en vez de 'F(kV/cm)')."""
    if VARIABLE_BARRIDA_MANUAL is not None:
        return VARIABLE_BARRIDA_MANUAL

    texto = f"{nombre_x} {nombre_archivo}".lower()

    if re.search(r"r[_\s]?1\b", texto):
        return "R1"
    if re.search(r"r[_\s]?2\b", texto):
        return "R2"
    if re.search(r"r[_\s]?3\b", texto):
        return "R3"
    if "x_0" in texto or "x0" in texto or "proton" in texto or "posici" in texto:
        return "x0"
    if "kv" in texto or re.search(r"\bf\b", texto) or "campo electr" in texto:
        return "F"
    if re.search(r"\bb\b", texto) or " t)" in texto or "tesla" in texto or "campo magnet" in texto:
        return "B"
    return None


def dibujar_geometria(ax, variable_barrida=None, valor_min=None, valor_max=None):
    """Dibuja el esquema 2D (vista superior) de la geometria: el
    rectangulo del dominio de simulacion, las tres capas concentricas
    (R1, R2, R3) y la impureza coulombiana (proton) como una superelipse
    de semiejes (a, b) en el centro (o desplazada sobre el eje x si el
    barrido es de posicion).

    Si 'variable_barrida' coincide con uno de los elementos dibujados, ese
    elemento se resalta (linea punteada mas gruesa) y, si se dan
    valor_min/valor_max (el rango real recorrido por el barrido leido del
    archivo), se marca ademas ese rango."""
    ax.set_aspect("equal")
    ax.set_facecolor("#f5f5f5")

    ancho, alto = GEOM_DOMINIO_ANCHO_NM, GEOM_DOMINIO_ALTO_NM

    # --- Rectangulo del dominio de simulacion ---
    ax.add_patch(plt.Rectangle((-ancho / 2, -alto / 2), ancho, alto,
                                 facecolor="#d9d9d9", edgecolor="black",
                                 linewidth=1.2, zorder=1))

    # --- Tres capas concentricas (R1, R2, R3) ---
    # Cada etiqueta se coloca en un angulo distinto (no las tres arriba en
    # x=0) para que no se encimen cuando dos radios quedan cerca en tamano
    # (ej. R1 ampliado por un barrido casi tocando a R2).
    radios = [("R1", GEOM_R1_NM, 100), ("R2", GEOM_R2_NM, 55), ("R3", GEOM_R3_NM, 20)]
    for nombre, r_defecto, angulo_grados in reversed(radios):
        resaltado = (variable_barrida == nombre)
        r = r_defecto
        if resaltado and GEOM_MOSTRAR_RANGO_BARRIDO and valor_max is not None:
            r = valor_max  # dibuja el circulo en su extremo mayor del barrido
        circ = plt.Circle((0, 0), r, facecolor="#d9d9d9", edgecolor="black",
                            linewidth=2.2 if resaltado else 1.0,
                            linestyle="--" if resaltado else "-", zorder=2)
        ax.add_patch(circ)
        etiqueta = f"{nombre} = {r_defecto:g} nm"
        if resaltado:
            etiqueta = f"{nombre} (BARRIDO)"
            if GEOM_MOSTRAR_RANGO_BARRIDO and valor_min is not None:
                etiqueta += f"\n{valor_min:g} a {valor_max:g} nm"

        angulo = np.radians(angulo_grados)
        punto_borde = np.array([r * np.cos(angulo), r * np.sin(angulo)])
        # La etiqueta se ancla siempre a la misma distancia del centro
        # (radio maximo del dominio dibujado), asi nunca se monta sobre
        # otro circulo aunque los radios sean parecidos entre si.
        radio_etiqueta = 0.5 * min(ancho, alto) * 1.02
        punto_texto = np.array([radio_etiqueta * np.cos(angulo), radio_etiqueta * np.sin(angulo)])
        ax.plot([punto_borde[0], punto_texto[0]], [punto_borde[1], punto_texto[1]],
                 color="crimson" if resaltado else "gray", linewidth=0.8,
                 linestyle=":", zorder=4)
        ax.text(punto_texto[0], punto_texto[1], etiqueta, fontsize=7.5,
                 va="center",
                 ha="left" if punto_texto[0] >= 0 else "right",
                 zorder=5, color="crimson" if resaltado else "black")

    # Si el barrido es de radio, dibuja tambien el circulo del extremo
    # menor (punteado rojo fino) para ver el rango completo.
    if variable_barrida in ("R1", "R2", "R3") and GEOM_MOSTRAR_RANGO_BARRIDO and valor_min is not None:
        ax.add_patch(plt.Circle((0, 0), valor_min, facecolor="none",
                                  edgecolor="crimson", linewidth=1.0,
                                  linestyle=":", zorder=6))

    # --- Impureza coulombiana (proton): superelipse |x/a|^n+|y/b|^n=1 ---
    a, b, n = GEOM_A_NM, GEOM_B_NM, GEOM_SUPERELIPSE_N
    x0 = GEOM_X0_NM
    barrido_posicion = (variable_barrida == "x0")

    if barrido_posicion and GEOM_MOSTRAR_RANGO_BARRIDO and valor_min is not None:
        # Se marca la trayectoria completa del proton con una flecha, y se
        # dibuja la superelipse en el centro del recorrido.
        ax.annotate("", xy=(valor_max, 0), xytext=(valor_min, 0),
                     arrowprops=dict(arrowstyle="<->", color="crimson", lw=1.4),
                     zorder=7)
        ax.text(0, -0.06 * alto, f"posición: {valor_min:g} a {valor_max:g} nm",
                 fontsize=7.5, color="crimson", ha="center", zorder=7)
        x0 = 0.0

    t = np.linspace(0, 2 * np.pi, 200)
    ct, st = np.cos(t), np.sin(t)
    x_se = x0 + a * np.sign(ct) * np.abs(ct) ** (2.0 / n)
    y_se = b * np.sign(st) * np.abs(st) ** (2.0 / n)
    ax.fill(x_se, y_se, facecolor="#e31a1c", edgecolor="black",
             linewidth=1.5, linestyle="--" if barrido_posicion else "-", zorder=8)
    ax.plot(x0, 0, marker="+", color="white", markersize=6, zorder=9)
    if not barrido_posicion:
        ax.text(x0, -b - 0.04 * alto, f"protón (a={a:g}, b={b:g} nm)",
                 fontsize=7, ha="center", va="top", zorder=9)

    # --- Campo electrico F (si es la variable barrida): flecha horizontal ---
    if variable_barrida == "F":
        ax.annotate("", xy=(0.42 * ancho, 0), xytext=(-0.42 * ancho, 0),
                     arrowprops=dict(arrowstyle="->", color="purple", lw=2), zorder=10)
        etiqueta_f = "F (BARRIDO)"
        if GEOM_MOSTRAR_RANGO_BARRIDO and valor_min is not None:
            etiqueta_f += f"\n{valor_min:g} a {valor_max:g} kV/cm"
        ax.text(0, 0.42 * alto, etiqueta_f, color="purple", fontsize=8,
                 ha="center", zorder=10)

    # --- Campo magnetico B (si es la variable barrida): simbolo en esquina ---
    if variable_barrida == "B":
        etiqueta_b = "B ⟂ al plano (BARRIDO)"
        if GEOM_MOSTRAR_RANGO_BARRIDO and valor_min is not None:
            etiqueta_b += f"\n{valor_min:g} a {valor_max:g} T"
        ax.text(-0.44 * ancho, 0.42 * alto, etiqueta_b, color="darkgreen",
                 fontsize=7.5, ha="left", va="top", zorder=10,
                 bbox=dict(boxstyle="round", fc="white", ec="darkgreen"))

    margen = 1.08
    ax.set_xlim(-ancho / 2 * margen, ancho / 2 * margen)
    ax.set_ylim(-alto / 2 * margen, alto / 2 * margen)
    ax.set_xlabel("x (nm)", fontsize=9)
    ax.set_ylabel("y (nm)", fontsize=9)
    ax.set_title("Geometría del disco cuántico", fontsize=10)
    ax.tick_params(labelsize=7.5)


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

def graficar(x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo,
             variable_barrida=None, valor_min=None, valor_max=None):
    """Grafica un solo archivo: datos a la izquierda, geometria del disco
    cuantico a la derecha (con la variable barrida resaltada)."""
    fig, (ax_datos, ax_geo) = plt.subplots(
        1, 2, figsize=(13, 6), gridspec_kw={"width_ratios": [1.3, 1]})

    for idx in indices:
        ax_datos.plot(x0_unicos, ramas[idx, :], linestyle="-", linewidth=1.8,
                       label=etiquetas[idx])

    ax_datos.set_xlabel(nombre_x)
    ax_datos.set_ylabel(nombre_y)
    ax_datos.set_title(titulo)
    ax_datos.legend(loc="best", fontsize=8, ncol=2)
    ax_datos.grid(True, alpha=0.3)

    dibujar_geometria(ax_geo, variable_barrida, valor_min, valor_max)

    plt.tight_layout()
    plt.show()


def graficar_mosaico(resultados):
    """Grafica varios archivos en una sola figura: una FILA por archivo,
    con los datos en la columna izquierda y la geometria (con la variable
    barrida de ese archivo resaltada) en la columna derecha. 'resultados'
    es una lista de tuplas:
    (x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo,
     variable_barrida, valor_min, valor_max)."""
    n = len(resultados)

    fig, axes = plt.subplots(n, 2, figsize=(11, 4.2 * n), squeeze=False,
                               gridspec_kw={"width_ratios": [1.3, 1]})

    for fila, resultado in zip(axes, resultados):
        ax_datos, ax_geo = fila
        (x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo,
         variable_barrida, valor_min, valor_max) = resultado

        for idx in indices:
            ax_datos.plot(x0_unicos, ramas[idx, :], linestyle="-", linewidth=1.5,
                           label=etiquetas[idx])
        ax_datos.set_xlabel(nombre_x, fontsize=9)
        ax_datos.set_ylabel(nombre_y, fontsize=9)
        ax_datos.set_title(titulo, fontsize=10)
        ax_datos.legend(loc="best", fontsize=6, ncol=2)
        ax_datos.grid(True, alpha=0.3)
        ax_datos.tick_params(labelsize=8)

        dibujar_geometria(ax_geo, variable_barrida, valor_min, valor_max)

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

        variable_barrida = detectar_variable_barrida(nombre_x, nombre_archivo)
        valor_min = float(np.min(x0_unicos)) if len(x0_unicos) else None
        valor_max = float(np.max(x0_unicos)) if len(x0_unicos) else None
        if variable_barrida:
            print(f"  Variable barrida detectada: {variable_barrida} "
                  f"({valor_min:g} a {valor_max:g})")
        else:
            print("  Variable barrida: no se pudo determinar automaticamente "
                  "(se dibuja la geometria con los valores por defecto; "
                  "usa VARIABLE_BARRIDA_MANUAL si quieres forzarla).")

        resultados.append((x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y,
                            nombre_archivo, variable_barrida, valor_min, valor_max))

    if not resultados:
        raise SystemExit("Ningun archivo se pudo leer correctamente.")

    if len(resultados) == 1:
        (x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo,
         variable_barrida, valor_min, valor_max) = resultados[0]
        graficar(x0_unicos, ramas, etiquetas, indices, nombre_x, nombre_y, titulo,
                 variable_barrida, valor_min, valor_max)
    else:
        graficar_mosaico(resultados)


if __name__ == "__main__":
    main()