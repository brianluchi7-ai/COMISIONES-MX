import re
import pandas as pd
import dash
from dash import html, dcc, Input, Output, dash_table
import plotly.express as px
from conexion_mysql import crear_conexion

# ======================================================
# === OBL DIGITAL DASHBOARD — COMISIONES POR AGENTE  ===
# ======================================================

def cargar_datos():
    try:
        conexion = crear_conexion()
        if conexion:
            print("✅ Leyendo desde Railway MySQL...")
            query = "SELECT * FROM CMN_MASTER_MEX_CLEAN"
            df = pd.read_sql(query, conexion)
            conexion.close()
            return df
    except Exception as e:
        print(f"⚠️ Error conectando a SQL, leyendo CSV local: {e}")

    print("📁 Leyendo desde CSV local...")
    return pd.read_csv("CMN_MASTER_MEX_preview.csv", dtype=str)

def cargar_withdrawals():
    try:
        conexion = crear_conexion()
        if conexion:
            query = "SELECT agent, usd, date, method FROM withdrawals_mx_2025"
            df_w = pd.read_sql(query, conexion)
            conexion.close()
            return df_w
    except Exception as e:
        print(f"⚠️ Error leyendo withdrawals: {e}")
    return pd.DataFrame(columns=["agent", "usd"])


# === Carga base ===
df = cargar_datos()
df_withdrawals = cargar_withdrawals()

df.columns = [c.strip().lower() for c in df.columns]

if "source" not in df.columns:
    df["source"] = None
if "type" not in df.columns:
    df["type"] = "FTD"  # fallback

# === Fechas ===
def convertir_fecha(valor):
    try:
        if "/" in valor:
            return pd.to_datetime(valor, format="%d/%m/%Y", errors="coerce")
        elif "-" in valor:
            return pd.to_datetime(str(valor).split(" ")[0], errors="coerce")
    except Exception:
        return pd.NaT
    return pd.NaT

df["date"] = df["date"].astype(str).str.strip().apply(convertir_fecha)
df = df[df["date"].notna()]
df["date"] = pd.to_datetime(df["date"], utc=False).dt.tz_localize(None)

# === Limpieza USD ===
def limpiar_usd(valor):
    if pd.isna(valor): return 0.0
    s = str(valor).strip()
    if s == "": return 0.0
    s = re.sub(r"[^\d,.\-]", "", s)
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        partes = s.split(",")
        s = s.replace(",", ".") if len(partes[-1]) == 2 else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except:
        return 0.0
        
df_withdrawals["usd"] = df_withdrawals["usd"].apply(limpiar_usd)
df["usd"] = df["usd"].apply(limpiar_usd)

# ==========================
# FECHAS WITHDRAWALS (FIX DEFINITIVO)
# ==========================
if "date" not in df_withdrawals.columns:
    raise Exception("❌ withdrawals_mx_2025 NO tiene columna 'date'")

df_withdrawals["date"] = pd.to_datetime(df_withdrawals["date"], errors="coerce")
df_withdrawals = df_withdrawals[df_withdrawals["date"].notna()]
df_withdrawals["year_month"] = df_withdrawals["date"].dt.to_period("M")

df_withdrawals["agent"] = df_withdrawals["agent"].astype(str).str.strip().str.title()
df_withdrawals["method"] = df_withdrawals["method"].astype(str).str.upper()

# Withdrawals por agente / mes
withdrawals_normal = (
    df_withdrawals[df_withdrawals["method"] != "WALLET"]
    .groupby(["agent", "year_month"])["usd"]
    .sum()
    .to_dict()
)

withdrawals_wallet = (
    df_withdrawals[df_withdrawals["method"] == "WALLET"]
    .groupby(["agent", "year_month"])["usd"]
    .sum()
    .to_dict()
)

# === Texto limpio ===
for col in ["team", "agent", "country", "affiliate", "source", "id"]:
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.title()
        df[col].replace({"Nan": None, "None": None, "": None}, inplace=True)

# === Comisión progresiva ===
def porcentaje_tramo_progresivo(n_venta):
    if 1 <= n_venta <= 3:
        return 0.10
    elif 4 <= n_venta <= 7:
        return 0.17
    elif 8 <= n_venta <= 12:
        return 0.19
    elif 13 <= n_venta <= 17:
        return 0.22
    elif 18 <= n_venta <= 21:
        return 0.25
    elif n_venta >= 22:
        return 0.30
    return 0.0

def porcentaje_rtn_progresivo(usd_total):
    if usd_total <= 25000:
        return 0.05
    elif usd_total <= 50000:
        return 0.06
    elif usd_total <= 75000:
        return 0.075
    elif usd_total <= 101000:
        return 0.09
    elif usd_total <= 151000:
        return 0.10
    else:
        return 0.12

def calcular_comision_wallet(df_rtn, pct_base, pct_wallet_extra):
    """
    Aplica comisión separando WALLET y NO WALLET
    """
    if df_rtn.empty:
        return 0.0

    df_wallet = df_rtn[df_rtn["method"].str.upper() == "WALLET"] if "method" in df_rtn.columns else pd.DataFrame()
    df_normal = df_rtn.drop(df_wallet.index)

    usd_wallet = df_wallet["usd_neto"].sum()
    usd_normal = df_normal["usd_neto"].sum()

    return (usd_normal * pct_base) + (usd_wallet * (pct_base + pct_wallet_extra))

def porcentaje_team_leader(cumplimiento):
    """
    cumplimiento = total_team_rtn / target
    retorna porcentaje en decimal
    """
    if cumplimiento < 0.75:
        return 0.0
    elif cumplimiento < 1.0:
        return 0.008      # 0.8%
    elif cumplimiento < 1.10:
        return 0.01       # 1.0%
    elif cumplimiento < 1.20:
        return 0.011      # 1.10%
    elif cumplimiento < 1.30:
        return 0.012      # 1.20%
    elif cumplimiento < 1.40:
        return 0.013      # 1.30%
    elif cumplimiento < 1.50:
        return 0.014      # 1.40%
    else:
        return 0.015      # 1.50%



# =========================
# NUEVOS TARGETS BASE TL
# =========================
TARGETS_BASE = {
    "Luisa Medina": 180000,
    "Hugo Del Castillo": 230000,
    "Rafael Castellanos": 230000,
    "Carlos Frias": 210000,
    "Diego Ceballos": 47000,
}

TARGETS_RUNTIME = TARGETS_BASE.copy()


# === 🧩 Corrección: reiniciar conteo por mes ===
df = df.sort_values(["agent", "date"]).reset_index(drop=True)

if not pd.api.types.is_datetime64_any_dtype(df["date"]):
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
df = df.dropna(subset=["date"])

df["year_month"] = df["date"].dt.to_period("M")
df["ftd_num"] = df.groupby(["agent", "year_month"]).cumcount() + 1

# === FTD: lógica original (NO SE TOCA) ===
df.loc[df["type"].str.upper() == "FTD", "comm_pct"] = (
    df.loc[df["type"].str.upper() == "FTD", "ftd_num"]
    .apply(porcentaje_tramo_progresivo)
)
df.loc[df["type"].str.upper() == "FTD", "usd_neto"] = df["usd"]
df.loc[df["type"].str.upper() == "FTD", "commission_usd"] = (
    df["usd"] * df["comm_pct"]
)

# ==========================
# RTN → NETO REAL (DEP - WITHDRAWALS)
# ==========================
df_rtn = df[df["type"].str.upper() == "RTN"].copy()
df_rtn = df_rtn.sort_values(["agent", "year_month", "date"]).reset_index(drop=True)


# Total depósitos por agente/mes
total_dep_map = (
    df_rtn
    .groupby(["agent", "year_month"])["usd"]
    .sum()
    .to_dict()
)

def calcular_usd_neto(row):
    key = (row["agent"], row["year_month"])

    retiro_normal = withdrawals_normal.get(key, 0)
    total_dep = total_dep_map.get(key, 0)

    if total_dep <= 0:
        return row["usd"]

    # 🔒 Nunca se descuenta más de lo depositado
    retiro_aplicable = min(retiro_normal, total_dep)

    proporcion = row["usd"] / total_dep
    retiro_fila = retiro_aplicable * proporcion

    return max(row["usd"] - retiro_fila, 0)

    total_dep = total_dep_map.get((row["agent"], row["year_month"]), 0)

    if total_dep <= 0:
        return row["usd"]

    proporcion = row["usd"] / total_dep
    retiro_fila = retiro_total * proporcion
    return max(row["usd"] - retiro_fila, 0)

df_rtn["usd_neto"] = df_rtn.apply(calcular_usd_neto, axis=1)

# 🔥 TOTAL NETO POR AGENT / MES
total_neto_mes = (
    df_rtn
    .groupby(["agent", "year_month"])["usd_neto"]
    .sum()
    .reset_index(name="usd_total_mes")
)

# Determinar porcentaje ÚNICO por mes
total_neto_mes["comm_pct"] = total_neto_mes["usd_total_mes"].apply(
    porcentaje_rtn_progresivo
)

# Unir el porcentaje plano a cada fila
df_rtn = df_rtn.merge(
    total_neto_mes[["agent", "year_month", "comm_pct"]],
    on=["agent", "year_month"],
    how="left"
)

# 🔒 FIX CRÍTICO
if "comm_pct" not in df_rtn.columns:
    df_rtn["comm_pct"] = 0.0

df_rtn["comm_pct"] = df_rtn["comm_pct"].fillna(0.0)

# Comisión RTN sobre NETO
df_rtn["commission_usd"] = df_rtn["usd_neto"] * df_rtn["comm_pct"]


# Comisión RTN sobre NETO
df_rtn["commission_usd"] = df_rtn["usd_neto"] * df_rtn["comm_pct"]

# 🔥 FIX DEFINITIVO: reemplazar RTN originales por RTN procesados

# Separar FTD intactos
df_ftd = df[df["type"].str.upper() == "FTD"].copy()

# Unir FTD + RTN ya calculados
df = pd.concat([df_ftd, df_rtn], ignore_index=True)

# Orden final limpio
df = df.sort_values(["agent", "date"]).reset_index(drop=True)


def week_of_month(dt):
    """
    Calcula la semana del mes (1..5) tomando en cuenta el día
    de la semana del primer día del mes (similar a tu macro de VBA).
    """
    first_day = dt.replace(day=1)
    # weekday(): lunes=0, domingo=6
    adjusted_dom = dt.day + first_day.weekday()
    return int((adjusted_dom - 1) / 7) + 1


# === App ===
app = dash.Dash(__name__)
server = app.server
app.title = "OBL Digital — Dashboard Comisiones"

# === Layout ===
app.layout = html.Div(
    style={"backgroundColor": "#0d0d0d", "color": "#000000", "fontFamily": "Poppins, Arial", "padding": "20px"},
    children=[
        html.H1("💰 DASHBOARD COMISIONES POR AGENTE", style={
            "textAlign": "center",
            "color": "#D4AF37",
            "marginBottom": "30px",
            "fontWeight": "bold"
        }),

        html.Div(
            style={"display": "flex", "justifyContent": "space-between"},
            children=[
                # === FILTROS ===
                html.Div(
                    style={
                        "width": "25%",
                        "backgroundColor": "#1a1a1a",
                        "padding": "20px",
                        "borderRadius": "12px",
                        "boxShadow": "0 0 15px rgba(212,175,55,0.3)",
                        "textAlign": "center"
                    },
                    children=[
                        html.Label("Date Range", style={"color": "#D4AF37", "fontWeight": "bold", "display": "block"}),
                        dcc.DatePickerRange(
                            id="filtro-fecha",
                            start_date=df["date"].min(),
                            end_date=df["date"].max(),
                            display_format="YYYY-MM-DD",
                            minimum_nights=0
                        ),
                        html.Br(), html.Br(),

                        html.Label("RTN Agent", style={"color": "#D4AF37", "fontWeight": "bold"}),
                        dcc.Dropdown(
                            id="filtro-rtn-agent",
                            multi=True,
                            placeholder="Selecciona RTN agent"
                       ),
                        html.Br(),
                        html.Label("RTN Team Leader", style={"color": "#D4AF37", "fontWeight": "bold"}),
                        dcc.Dropdown(
                            id="filtro-rtn-teamleader",
                            multi=False,
                            placeholder="Selecciona RTN Team Leader"
                        ),
                        html.Br(),

                        html.Label("FTD Agent", style={"color": "#D4AF37", "fontWeight": "bold"}),
                        dcc.Dropdown(
                            id="filtro-ftd-agent",
                            multi=True,
                            placeholder="Selecciona FTD agent"
                        ),
                        html.Br(),

                        html.Label("Tipo de cambio (MXN/USD)", style={"color": "#D4AF37", "fontWeight": "bold"}),
                        dcc.Input(
                            id="input-tc",
                            type="number",
                            value=18.19,
                            min=10, max=25, step=0.01,
                            style={"width": "120px", "textAlign": "center", "marginTop": "10px"}
                        
                        ), 
                        html.Br(),
                        html.Label("Target Team Leader (USD)", style={"color": "#D4AF37", "fontWeight": "bold"}),
                        dcc.Input(
                            id="input-target-tl",
                            type="number",
                            value=0,
                            min=0,
                            step=1000,
                            style={"width": "120px", "textAlign": "center", "marginTop": "10px"}
                        ),

                    ],
                ),

                # === PANEL PRINCIPAL ===
                html.Div(
                    style={"width": "72%"},
                    children=[
                        html.Div(
                            style={"display": "flex", "justifyContent": "space-around", "flexWrap": "wrap", "gap": "10px"},
                            children=[
                                html.Div(id="card-porcentaje", style={"flex": "1 1 18%", "minWidth": "200px"}),
                                html.Div(id="card-usd-ventas", style={"flex": "1 1 18%", "minWidth": "200px"}),
                                html.Div(id="card-usd-bonus", style={"flex": "1 1 18%", "minWidth": "200px"}),
                                html.Div(id="card-usd-comision", style={"flex": "1 1 18%", "minWidth": "200px"}),
                                html.Div(id="card-total-ftd", style={"flex": "1 1 18%", "minWidth": "200px"}),
                            ],
                        ),
                        html.Br(),
                        dcc.Graph(id="grafico-comision-agent", style={"width": "100%", "height": "400px"}),
                        html.Br(),
                        html.H4("📋 Detalle de transacciones y comisiones", style={"color": "#D4AF37"}),
                        dash_table.DataTable(
                            id="tabla-detalle",
                            columns=[
                                {"name": "DATE", "id": "date"},
                                {"name": "AGENT", "id": "agent"},
                                {"name": "TYPE", "id": "type"},
                                {"name": "TEAM", "id": "team"},
                                {"name": "COUNTRY", "id": "country"},
                                {"name": "AFFILIATE", "id": "affiliate"},
                                {"name": "USD", "id": "usd"},
                                {"name": "FTD_NUM", "id": "ftd_num"},
                                {"name": "COMM_PCT", "id": "comm_pct"},
                                {"name": "COMMISSION_USD", "id": "commission_usd"},
                            ],
                            style_table={"overflowX": "auto", "backgroundColor": "#0d0d0d"},
                            page_size=10,
                            style_cell={
                                "textAlign": "center",
                                "color": "#f2f2f2",
                                "backgroundColor": "#1a1a1a",
                                "fontSize": "12px",
                            },
                            style_header={"backgroundColor": "#D4AF37", "color": "#000", "fontWeight": "bold"},
                            sort_action="native",
                        ),
                    ],
                ),
            ],
        ),
    ],
)

@app.callback(
    Output("input-target-tl", "value"),
    Input("filtro-rtn-teamleader", "value")
)
def cargar_target(teamleader):
    if not teamleader:
        return 0
    return TARGETS_RUNTIME.get(teamleader, 0)


@app.callback(
    Output("filtro-rtn-teamleader", "options"),
    Input("filtro-fecha", "start_date"),
    Input("filtro-fecha", "end_date"),
)
def cargar_team_leaders(start_date, end_date):

    df_f = df[df["type"].str.upper() == "RTN"].copy()

    if start_date and end_date:
        df_f = df_f[
            (df_f["date"] >= pd.to_datetime(start_date)) &
            (df_f["date"] <= pd.to_datetime(end_date))
        ]

    leaders = sorted(df_f["team"].dropna().unique())
    return [{"label": l, "value": l} for l in leaders]


@app.callback(
    [
        Output("filtro-rtn-agent", "options"),
        Output("filtro-ftd-agent", "options"),
    ],
    [
        Input("filtro-fecha", "start_date"),
        Input("filtro-fecha", "end_date"),
    ],
)
def actualizar_agentes_por_fecha(start_date, end_date):

    df_f = df.copy()

    if start_date and end_date:
        df_f = df_f[
            (df_f["date"] >= pd.to_datetime(start_date)) &
            (df_f["date"] <= pd.to_datetime(end_date))
        ]

    rtn_agents = sorted(
        df_f[df_f["type"].str.upper() == "RTN"]["agent"]
        .dropna()
        .unique()
    )

    ftd_agents = sorted(
        df_f[df_f["type"].str.upper() == "FTD"]["agent"]
        .dropna()
        .unique()
    )

    return (
        [{"label": a, "value": a} for a in rtn_agents],
        [{"label": a, "value": a} for a in ftd_agents],
    )
    

@app.callback(
    [
        Output("card-porcentaje", "children"),
        Output("card-usd-ventas", "children"),
        Output("card-usd-bonus", "children"),
        Output("card-usd-comision", "children"),
        Output("card-total-ftd", "children"),
        Output("grafico-comision-agent", "figure"),
        Output("tabla-detalle", "data"),
    ],
    [
        Input("filtro-rtn-agent", "value"),
        Input("filtro-ftd-agent", "value"),
        Input("filtro-fecha", "start_date"),
        Input("filtro-fecha", "end_date"),
        Input("input-tc", "value"),
        Input("filtro-rtn-teamleader", "value"),
        Input("input-target-tl", "value"),
    ],
)

def actualizar_dashboard(
    rtn_agents,
    ftd_agents,
    start_date,
    end_date,
    tipo_cambio,
    rtn_teamleader,
    target_teamleader
):

    
    df_filtrado = df.copy()

    
    # ======================
    # GUARDAR TARGET EDITADO DEL TEAM LEADER
    # ======================
    if rtn_teamleader and target_teamleader:
       TARGETS_RUNTIME[rtn_teamleader] = float(target_teamleader)


    # ======================
    # 1️⃣ FILTRO POR FECHA (SIEMPRE PRIMERO)
    # ======================
    if start_date and end_date:
        df_filtrado = df_filtrado[
            (df_filtrado["date"] >= pd.to_datetime(start_date)) &
            (df_filtrado["date"] <= pd.to_datetime(end_date))
        ]
    
    # ======================
    # 2️⃣ FILTRO RTN TEAM LEADER (TIENE PRIORIDAD TOTAL)
    # ======================
    if rtn_teamleader:
        df_filtrado = df_filtrado[
            (df_filtrado["type"].str.upper() == "RTN") &
            (df_filtrado["team"] == rtn_teamleader)
        ]

    
    # ======================
    # 3️⃣ FILTRO POR AGENTES (SOLO SI NO HAY TEAM LEADER)
    # ======================
    elif rtn_agents or ftd_agents:
        agentes = []
        if rtn_agents:
            agentes += rtn_agents
        if ftd_agents:
            agentes += ftd_agents
    
        df_filtrado = df_filtrado[df_filtrado["agent"].isin(agentes)]
    
    # ======================
    # ORDEN FINAL
    # ======================
    df_filtrado = (
        df_filtrado
        .sort_values(["agent", "date"])
        .reset_index(drop=True)
    )

    if df_filtrado.empty:
        fig_vacio = px.scatter(title="Sin datos para mostrar")
        fig_vacio.update_layout(
            paper_bgcolor="#0d0d0d",
            plot_bgcolor="#0d0d0d",
            font_color="#f2f2f2"
        )
        vacio = html.Div("Sin datos", style={"color": "#D4AF37"})
        return vacio, vacio, vacio, vacio, vacio, fig_vacio, []

    # ======================
    # BONUS SEMANAL (SOLO FTD)
    # ======================
    df_bonus = df_filtrado[df_filtrado["type"].str.upper() == "FTD"].copy()

    df_bonus["year"] = df_bonus["date"].dt.year
    df_bonus["month"] = df_bonus["date"].dt.month

    def week_of_month(dt):
        first_day = dt.replace(day=1)
        adjusted = dt.day + first_day.weekday()
        return int((adjusted - 1) / 7) + 1

    df_bonus["week_month"] = df_bonus["date"].apply(week_of_month)

    df_semana = (
        df_bonus
        .groupby(["agent", "year", "month", "week_month"])
        .size()
        .reset_index(name="ftds")
    )

    bonus_total_usd = 0.0

    for _, row in df_semana.iterrows():
        ftds = row["ftds"]
        if ftds >= 15:
            bonus_total_usd += 150
        elif ftds >= 5:
            bonus_total_usd += 1500 / tipo_cambio
        elif ftds >= 4:
            bonus_total_usd += 1000 / tipo_cambio
        elif ftds >= 2:
            bonus_total_usd += 500 / tipo_cambio

    total_bonus = round(bonus_total_usd, 2)

    # ======================
    # 🔥 RECALCULO RTN POST-FILTRO (FIX DEFINITIVO)
    # ======================
    df_rtn_f = df_filtrado[df_filtrado["type"].str.upper() == "RTN"]

    if not df_rtn_f.empty:
        total_rtn_neto = df_rtn_f["usd_neto"].sum()
        pct_rtn = porcentaje_rtn_progresivo(total_rtn_neto)

        df_filtrado.loc[
            df_filtrado["type"].str.upper() == "RTN", "comm_pct"
        ] = pct_rtn

        df_filtrado.loc[
            df_filtrado["type"].str.upper() == "RTN", "commission_usd"
        ] = df_filtrado["usd_neto"] * pct_rtn

    # ======================
    # DATASET TEAM LEADER (SOLO RTN)
    # ======================
    df_team = pd.DataFrame()
    if rtn_teamleader:
        df_team = df_filtrado[
            (df_filtrado["type"].str.upper() == "RTN") &
            (df_filtrado["team"] == rtn_teamleader)
        ].copy()


    # ======================
    # 👑 COMISIÓN TEAM LEADER (SOLO RTN – SOLO CARDS)
    # ======================
    comision_teamleader = 0.0
    pct_tl = 0.0
    
    if rtn_teamleader and not df_team.empty:
        total_team_rtn = df_team["usd_neto"].sum()
        target = TARGETS_RUNTIME.get(rtn_teamleader, 0)
    
        if target > 0:
            cumplimiento = total_team_rtn / target
            pct_tl = porcentaje_team_leader(cumplimiento)
        
            comision_teamleader = calcular_comision_wallet(
                df_team,
                pct_tl,
                0.05   # wallet extra (lo validamos luego)
            )


    # ======================
    # TOTALES (TEAM LEADER TIENE PRIORIDAD)
    # ======================
    if rtn_teamleader and not df_team.empty:
        total_usd = df_team["usd_neto"].sum()
        
        # Separar wallet y no wallet
        df_wallet = df_team[df_team["method"].str.upper() == "WALLET"]
        df_normal = df_team[df_team["method"].str.upper() != "WALLET"]
        
        usd_wallet = df_wallet["usd_neto"].sum()
        usd_normal = df_normal["usd_neto"].sum()
        
        # Porcentajes
        pct_normal = pct_tl
        pct_wallet = pct_tl + 0.05
        
        # Comisión final TL
        comision_teamleader = (usd_normal * pct_normal) + (usd_wallet * pct_wallet)

        total_ftd = len(df_team)
        pct_real = pct_tl
    else:
        total_usd = df_filtrado["usd_neto"].sum()
        
        # Separar wallet y no wallet
        df_wallet = df_filtrado[df_filtrado["method"].str.upper() == "WALLET"]
        df_normal = df_filtrado[df_filtrado["method"].str.upper() != "WALLET"]
        
        usd_wallet = df_wallet["usd_neto"].sum()
        usd_normal = df_normal["usd_neto"].sum()
        
        # Porcentajes
        pct_normal = pct_tl
        pct_wallet = pct_tl + 0.05
        
        # Comisión final TL
        comision_agentrtn = (usd_normal * pct_normal) + (usd_wallet * pct_wallet)

        total_ftd = len(df_filtrado)
        pct_real = pct_tl

    # ======================
    # CARDS
    # ======================
    card_style = {
        "backgroundColor": "#1a1a1a",
        "borderRadius": "10px",
        "padding": "20px",
        "textAlign": "center",
        "boxShadow": "0 0 10px rgba(212,175,55,0.3)",
    }

    def card(title, value):
        return html.Div(
            [
                html.H4(title, style={"color": "#D4AF37"}),
                html.H2(value, style={"color": "#FFFFFF"}),
            ],
            style=card_style
        )

    fig_agent = px.bar(
        df_filtrado.groupby("agent", as_index=False)["commission_usd"].sum(),
        x="agent",
        y="commission_usd",
        title="Comisión USD by Agent",
        color="commission_usd",
        color_continuous_scale="YlOrBr"
    )

    fig_agent.update_layout(
        paper_bgcolor="#0d0d0d",
        plot_bgcolor="#0d0d0d",
        font_color="#f2f2f2",
        title_font_color="#D4AF37"
    )

    df_tabla = df_filtrado[
        ["date", "agent", "type", "team", "country", "affiliate", "usd", "ftd_num", "comm_pct", "commission_usd"]
    ].copy()

    df_tabla["comm_pct"] = df_tabla["comm_pct"].apply(lambda x: f"{x*100:.2f}%")
    df_tabla["commission_usd"] = df_tabla["commission_usd"].round(2)

    return (
        card("PORCENTAJE COMISIÓN", f"{pct_real*100:,.2f}%"),
        card("VENTAS USD", f"{total_usd:,.2f}"),
        card("BONUS SEMANAL USD", f"{total_bonus:,.2f}"),
        card("COMISIÓN USD (TOTAL)", f"{total_commission_final:,.2f}"),
        card("TOTAL VENTAS (FTDs)", f"{total_ftd:,}"),
        fig_agent,
        df_tabla.to_dict("records"),
    )

# === 🔟 Index string para capturar imagen (igual que el otro dashboard) ===
app.index_string = '''
<!DOCTYPE html>
<html>
<head>
  {%metas%}
  <title>OBL Digital — Dashboard Comisiones</title>
  {%favicon%}
  {%css%}
  <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
</head>
<body>
  {%app_entry%}
  <footer>
    {%config%}
    {%scripts%}
    {%renderer%}
  </footer>

  <script>
    window.addEventListener("message", async (event) => {
      if (!event.data || event.data.action !== "capture_dashboard") return;

      try {
        const canvas = await html2canvas(document.body, { useCORS: true, scale: 2, backgroundColor: "#0d0d0d" });
        const imgData = canvas.toDataURL("image/png");

        window.parent.postMessage({
          action: "capture_image",
          img: imgData,
          filetype: event.data.type
        }, "*");
      } catch (err) {
        console.error("Error al capturar dashboard:", err);
        window.parent.postMessage({ action: "capture_done" }, "*");
      }
    });
  </script>
</body>
</html>
'''

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8060, debug=True)






























