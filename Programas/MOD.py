"""
Script para:
  1) Leer la tabla de barrido parametrico de COMSOL (Schrodinger).
  2) Dejarte elegir cuantos/cuales estados de energia quieres graficar.
  3) Graficar esos estados (x_0 vs Energia propia) con lineas continuas.
  4) Exportar un .txt "limpio" solo con los estados seleccionados, listo
     para usar como entrada de otro programa.

Formato del archivo de entrada esperado (igual al exportado por COMSOL):
    x_0 (nm) | lambda | Energia propia (eV) | Probabilidad total (1)
  con lineas de encabezado que empiezan con '%', y varias filas seguidas
  (una por cada estado propio) para cada valor de x_0.

Formato del archivo de salida (para el siguiente programa):
    x_0(nm)   Estado_1(eV)   Estado_3(eV)   Estado_5(eV)   ...
  una fila por cada valor de x_0, columnas separadas por tabulador, con
  encabezado. Si tu siguiente programa necesita otro formato (por ejemplo
  formato largo x_0/estado/energia en vez de columnas), dimelo y lo ajusto.

Uso:
    python seleccionar_y_exportar_barrido.py
    (usa la ruta fija RUTA_ARCHIVO_POR_DEFECTO, o pasa otra ruta como argumento)
"""

import sys
import numpy as np
import matplotlib.pyplot as plt

# Ruta fija del archivo de datos de entrada
RUTA_ARCHIVO_POR_DEFECTO = r"C:\Users\Admin\Documents\Cuantica_Avanzada\Tablas\p.txt"

# Ruta fija del archivo de salida (para el siguiente programa)
RUTA_SALIDA_POR_DEFECTO = r"C:\Users\Admin\Documents\Cuantica_Avanzada\Tablas\Grafica FINAL E vs N F0.txt"


def leer_datos(ruta_archivo):
    """Lee el archivo, ignora el encabezado ('%') y devuelve un arreglo
    numpy con las 4 columnas numericas."""
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


def agrupar_por_ramas(datos, decimales_x0=6):
    """Agrupa las filas en bloques con el mismo x_0 y arma una rama por
    posicion dentro de cada bloque. Devuelve x0_unicos y una matriz
    (n_ramas x n_puntos) con la energia de cada rama."""
    x0_col = datos[:, 0]
    energia_col = datos[:, 2]
    x0_redondeado = np.round(x0_col, decimales_x0)

    x0_unicos = []
    bloques = []
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


def pedir_seleccion(n_ramas):
    """Pregunta al usuario cuales estados quiere graficar/exportar.
    Acepta:
      - 'todos'
      - lista separada por comas, ej: 1,3,5
      - rangos, ej: 1-20
      - combinacion de ambos, ej: 1-5,8,10-12
    """
    print(f"\nSe detectaron {n_ramas} estados de energia (ramas) en el archivo.")
    entrada = input(
        f"¿Cuales quieres graficar/exportar? Escribe 'todos', una lista "
        f"separada por comas (ej: 1,2,3), un rango (ej: 1-20) o una "
        f"combinacion (ej: 1-5,8,10-12) [1-{n_ramas}]: "
    ).strip().lower()

    if entrada in ("todos", "all", ""):
        return list(range(1, n_ramas + 1))

    indices = []
    for parte in entrada.split(","):
        parte = parte.strip()
        if not parte:
            continue

        if "-" in parte:
            extremos = parte.split("-")
            if len(extremos) != 2:
                raise ValueError(f"Rango invalido: '{parte}'. Usa el formato 'inicio-fin', ej: 1-20.")
            inicio_str, fin_str = extremos[0].strip(), extremos[1].strip()
            if not inicio_str or not fin_str:
                raise ValueError(f"Rango invalido: '{parte}'. Usa el formato 'inicio-fin', ej: 1-20.")
            inicio, fin = int(inicio_str), int(fin_str)
            if inicio > fin:
                inicio, fin = fin, inicio
            if inicio < 1 or fin > n_ramas:
                raise ValueError(f"El rango {inicio}-{fin} se sale del rango valido: 1-{n_ramas}.")
            indices.extend(range(inicio, fin + 1))
        else:
            idx = int(parte)
            if idx < 1 or idx > n_ramas:
                raise ValueError(f"El estado {idx} no existe (rango valido: 1-{n_ramas}).")
            indices.append(idx)

    if not indices:
        raise ValueError("No se selecciono ningun estado valido.")

    return sorted(set(indices))


def graficar(x0_unicos, ramas, seleccion, titulo="Energia propia vs x_0"):
    plt.figure(figsize=(9, 6))
    for idx in seleccion:
        plt.plot(x0_unicos, ramas[idx - 1, :], linestyle="-", linewidth=1.8,
                  label=f"Estado {idx}")

    plt.xlabel(r"$x_0$ (nm)")
    plt.ylabel("Energia propia (eV)")
    plt.title(titulo)
    plt.legend(loc="best", fontsize=8, ncol=2)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def exportar_txt(x0_unicos, ramas, seleccion, ruta_salida):
    """Exporta un .txt con columnas: x_0(nm), Estado_i(eV)... solo para
    los estados seleccionados. Separador: tabulador."""
    encabezado = "x_0(nm)\t" + "\t".join(f"Estado_{idx}(eV)" for idx in seleccion)

    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(encabezado + "\n")
        for j, x0_val in enumerate(x0_unicos):
            valores = [f"{x0_val:.10g}"]
            for idx in seleccion:
                energia = ramas[idx - 1, j]
                valores.append(f"{energia:.10g}" if not np.isnan(energia) else "")
            f.write("\t".join(valores) + "\n")

    print(f"\nArchivo exportado en: {ruta_salida}")


def main():
    ruta_archivo = sys.argv[1] if len(sys.argv) > 1 else RUTA_ARCHIVO_POR_DEFECTO
    ruta_salida = sys.argv[2] if len(sys.argv) > 2 else RUTA_SALIDA_POR_DEFECTO

    datos = leer_datos(ruta_archivo)
    x0_unicos, ramas = agrupar_por_ramas(datos)
    n_ramas = ramas.shape[0]

    seleccion = pedir_seleccion(n_ramas)
    print(f"Estados seleccionados: {seleccion}")

    exportar_txt(x0_unicos, ramas, seleccion, ruta_salida)
    graficar(x0_unicos, ramas, seleccion)


if __name__ == "__main__":
    main()