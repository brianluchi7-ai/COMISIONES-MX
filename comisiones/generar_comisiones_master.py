import pandas as pd
import re
from conexion_mysql import crear_conexion

# ======================================================
# === OBL DIGITAL — Generador CMN_MASTER_MEX_CLEAN (FTD + RTN)
# ======================================================

def limpiar_valor_monto(valor):
    """Limpia texto/moneda y devuelve número como string o None."""
    if pd.isna(valor):
        return None
    s = str(valor).strip()
    if s == "":
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        partes = s.split(",")
        if len(partes[-1]) in (2, 3):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        float(s)
        return s
    except:
        return None


def primera_fila_parece_encabezado(df):
    """Evalúa si la primera fila parece encabezado en lugar de datos."""
    cols = [str(c).lower() for c in df.columns]
    genericas = sum(1 for c in cols if c.startswith("col") or "unnamed" in c or c.startswith("num_"))
    if genericas >= len(cols) * 0.5:
        fila0 = df.iloc[0]
        textos = 0
        for v in fila0:
            if isinstance(v, str):
                if not re.match(r"^\d{1,4}([/-]\d{1,2}){1,2}$", v):  # evita fechas
                    textos += 1
        return textos >= len(fila0) * 0.4
    return False


def limpiar_encabezados(df, tabla):
    """Si la primera fila parece encabezado, úsala como encabezado real."""
    if primera_fila_parece_encabezado(df):
        print(f"🔹 {tabla}: primera fila tomada como encabezado.")
        primera_fila = df.iloc[0].fillna("").astype(str)
        df.columns = primera_fila
        df = df.drop(df.index[0]).reset_index(drop=True)
    else:
        print(f"🔹 {tabla}: se conservan los encabezados originales.")
    return df


def estandarizar_columnas(df):
    rename_map = {
        "data": "date", "fecha": "date", "date_ftd": "date", "fechadep": "date",
        "fecha_dep": "date", "fecha_rtn": "date", "fecha_de_registro": "date",

        "equipo": "team", "team_name": "team", "leader_team": "team", "team_lader": "team",

        "pais": "country", "country_name": "country",

        "agente": "agent", "agent_sales": "agent", "agent_name": "agent",

        "afiliado": "affiliate", "affiliate_name": "affiliate",

        "usuario": "id", "id_user": "id", "id_usuario": "id",

        "monto": "usd", "usd_total": "usd", "amount_country": "usd", "usd_monto": "usd",

        "origen": "source", "source_name": "source"
    }

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df.rename(columns={old: new}, inplace=True)

    if "source" not in df.columns:
        df["source"] = None

    return df


def construir_df_limpio(df, month_label, tipo):
    """Crea DataFrame limpio y normalizado con columnas estándar y TYPE."""
    cols_finales = ["date", "id", "team", "agent", "country", "affiliate", "usd", "source"]

    df_limpio = pd.DataFrame()
    for col in cols_finales:
        if col in df.columns:
            serie = df[col]
        else:
            serie = pd.Series([None] * len(df))

        if col == "usd":
            serie = serie.apply(limpiar_valor_monto)
        else:
            serie = serie.apply(lambda x: str(x).strip() if pd.notna(x) else None)

        df_limpio[col] = serie

    df_limpio["month_name"] = month_label
    df_limpio["type"] = tipo
    df_limpio.replace("", None, inplace=True)
    df_limpio.dropna(how="all", subset=cols_finales, inplace=True)
    df_limpio.reset_index(drop=True, inplace=True)
    return df_limpio


def cargar_tabla(tabla, conexion):
    """Lee, limpia y devuelve un DF estandarizado."""
    print(f"\n===> Leyendo tabla {tabla} ...")
    df = pd.read_sql(f"SELECT * FROM {tabla}", conexion)
    print(f"   🔸 Columnas originales: {list(df.columns)}")
    print(f"   🔸 Registros brutos: {len(df)}")

    df = limpiar_encabezados(df, tabla)
    df = estandarizar_columnas(df)

    # Detectar mes
    mes_raw = tabla.replace("ftds_", "").replace("dep_", "").replace("_rtn", "").replace("_2025", "")
    month_label = mes_raw[:3].capitalize()

    # Detectar tipo (FTD / RTN)
    tipo = "FTD" if "ftd" in tabla.lower() else "RTN"

    df_limpio = construir_df_limpio(df, month_label, tipo)
    print(f"   ✅ Filas válidas en {tabla}: {len(df_limpio)}")
    return df_limpio


def obtener_datos():
    conexion = crear_conexion()
    if conexion is None:
        print("❌ No se pudo conectar a Railway.")
        return pd.DataFrame()

    tablas = [
        "dep_sep_rtn_2025",
        "dep_oct_rtn_2025",
        "dep_nov_rtn_2025",
        "ftds_sep_2025",
        "ftds_oct_2025",
        "ftds_nov_2025"
    ]
    dataframes = []

    for tabla in tablas:
        try:
            df_mes = cargar_tabla(tabla, conexion)
            if not df_mes.empty:
                dataframes.append(df_mes)
        except Exception as e:
            print(f"⚠️ Error procesando {tabla}: {e}")

    conexion.close()

    if not dataframes:
        print("❌ No se generó CMN_MASTER_MEX (sin datos).")
        return pd.DataFrame()

    df_master = pd.concat(dataframes, ignore_index=True)
    print(f"\n📊 CMN_MASTER_MEX generado correctamente con {len(df_master)} registros totales.")
    print(df_master["month_name"].value_counts())

    df_master.to_csv("CMN_MASTER_MEX_preview.csv", index=False, encoding="utf-8-sig")
    print("💾 Vista previa guardada: CMN_MASTER_MEX_preview.csv")

    # Crear tabla en Railway
    try:
        conexion = crear_conexion()
        if conexion:
            cursor = conexion.cursor()
            cursor.execute("DROP TABLE IF EXISTS CMN_MASTER_MEX_CLEAN;")
            cursor.execute("""
                CREATE TABLE CMN_MASTER_MEX_CLEAN (
                    date TEXT,
                    id TEXT,
                    team TEXT,
                    agent TEXT,
                    country TEXT,
                    affiliate TEXT,
                    source TEXT,
                    usd TEXT,
                    month_name TEXT,
                    type TEXT
                );
            """)
            conexion.commit()

            columnas = ["date", "id", "team", "agent", "country", "affiliate", "source", "usd", "month_name", "type"]
            for _, row in df_master.iterrows():
                valores = [row.get(c) if row.get(c) is not None else None for c in columnas]
                cursor.execute(
                    f"INSERT INTO CMN_MASTER_MEX_CLEAN ({', '.join(columnas)}) VALUES ({', '.join(['%s'] * len(columnas))})",
                    valores
                )
            conexion.commit()
            conexion.close()
            print("✅ CMN_MASTER_MEX_CLEAN creada y poblada correctamente en Railway (con TYPE).")
    except Exception as e:
        print(f"⚠️ Error al crear CMN_MASTER_MEX_CLEAN: {e}")

    return df_master


if __name__ == "__main__":
    df = obtener_datos()
    print("\nPrimeras filas de CMN_MASTER_MEX:")
    print(df.head())
