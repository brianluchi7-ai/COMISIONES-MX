import re
import pandas as pd
import dash
from dash import html, dcc, Input, Output, dash_table
import plotly.express as px
from conexion_mysql import crear_conexion

# ======================================================
# === OBL DIGITAL DASHBOARD — COMISIONES SOLO FTD ===
# ======================================================

def cargar_datos():
    try:
        conexion = crear_conexion()
        if conexion:
            query = "SELECT * FROM CMN_MASTER_MEX_CLEAN"
            df = pd.read_sql(query, conexion)
            conexion.close()
            return df
    except Exception as e:
        print(f"⚠️ Error SQL, usando CSV: {e}")
    return pd.read_csv("CMN_MASTER_preview.csv", dtype=str)

# === CARGA BASE ===
df = cargar_datos()
df.columns = [c.strip().lower() for c in df.columns]

# === SOLO FTD (CLAVE) ===
if "type" not in df.columns:
    df["type"] = "FTD"
df = df[df["type"].str.upper() == "FTD"].copy()

# === FECHAS ===
def convertir_fecha(valor):
    try:
        if "/" in str(valor):
            return pd.to_datetime(valor, format="%d/%m/%Y", errors="coerce")
        return pd.to_datetime(str(valor).split(" ")[0], errors="coerce")
    except:
        return pd.NaT

df["date"] = df["date"].astype(str).apply(convertir_fecha)
df = df[df["date"].notna()]
df["date"] = df["date"].dt.tz_localize(None)

# === USD ===
def limpiar_usd(valor):
    if pd.isna(valor): return 0.0
    s = re.sub(r"[^\d,.\-]", "", str(valor))
    if "." in s and "," in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) == 2 else s.replace(",", "")
    try:
        return float(s)
    except:
        return 0.0

df["usd"] = df["usd"].apply(limpiar_usd)
df["usd_neto"] = df["usd"]

# === TEXTO LIMPIO ===
for col in ["team", "agent", "country", "affiliate"]:
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.title()
        df[col].replace({"Nan": None, "None": None, "": None}, inplace=True)

# === COMISIÓN PROGRESIVA FTD ===
def porcentaje_tramo_progresivo(n):
    if n <= 3: return 0.10
    if n <= 7: return 0.17
    if n <= 12: return 0.19
    if n <= 17: return 0.22
    if n <= 21: return 0.25
    return 0.30

# === CONTEO POR MES (INTERNO, SIN PERIOD EN CALLBACK) ===
df = df.sort_values(["agent", "date"]).reset_index(drop=True)
df["_ym"] = df["date"].dt.to_period("M")
df["ftd_num"] = df.groupby(["agent", "_ym"]).cumcount() + 1

df["comm_pct"] = df["ftd_num"].apply(porcentaje_tramo_progresivo)
df["commission_usd"] = df["usd_neto"] * df["comm_pct"]

# ======================================================
# === DASH APP (MISMO LAYOUT)
# ======================================================

app = dash.Dash(__name__)
server = app.server
app.title = "OBL Digital — Dashboard Comisiones"

app.layout = html.Div(
    style={"backgroundColor": "#0d0d0d", "color": "#000", "fontFamily": "Poppins, Arial", "padding": "20px"},
    children=[

        html.H1("💰 DASHBOARD COMISIONES POR AGENTE", style={
            "textAlign": "center",
            "color": "#D4AF37",
            "marginBottom": "30px",
            "fontWeight": "bold"
        }),

        html.Div(style={"display": "flex", "justifyContent": "space-between"}, children=[

            # === FILTROS (NO SE TOCAN) ===
            html.Div(style={
                "width": "25%",
                "backgroundColor": "#1a1a1a",
                "padding": "20px",
                "borderRadius": "12px",
                "boxShadow": "0 0 15px rgba(212,175,55,0.3)",
                "textAlign": "center"
            }, children=[

                html.Label("Date Range", style={"color": "#D4AF37", "fontWeight": "bold"}),
                dcc.DatePickerRange(
                    id="filtro-fecha",
                    start_date=df["date"].min(),
                    end_date=df["date"].max(),
                    display_format="YYYY-MM-DD"
                ),
                html.Br(), html.Br(),

                html.Br(),
                html.Label("FTD Agent", style={"color": "#D4AF37", "fontWeight": "bold"}),
                dcc.Dropdown(id="filtro-ftd-agent", multi=True),

                html.Br(),
                html.Label("Tipo de cambio (MXN/USD)", style={"color": "#D4AF37", "fontWeight": "bold"}),
                dcc.Input(
                    id="input-tc",
                    type="number",
                    value=18.19,
                    step=0.01,
                    style={"width": "120px", "textAlign": "center"}
                ),
            ]),

            # === PANEL ===
            html.Div(style={"width": "72%"}, children=[

                html.Div(style={"display": "flex", "justifyContent": "space-around", "flexWrap": "wrap", "gap": "10px"}, children=[
                    html.Div(id="card-porcentaje", style={"flex": "1 1 18%"}),
                    html.Div(id="card-usd-ventas", style={"flex": "1 1 18%"}),
                    html.Div(id="card-usd-bonus", style={"flex": "1 1 18%"}),
                    html.Div(id="card-usd-comision", style={"flex": "1 1 18%"}),
                    html.Div(id="card-total-ftd", style={"flex": "1 1 18%"}),
                ]),

                html.Br(),
                dcc.Graph(id="grafico-comision-agent", style={"height": "400px"}),

                html.Br(),
                html.H4("📋 Detalle de transacciones y comisiones", style={"color": "#D4AF37"}),

                dash_table.DataTable(
                    id="tabla-detalle",
                    page_size=10,
                    sort_action="native",
                    style_table={"overflowX": "auto"},
                    style_cell={
                        "textAlign": "center",
                        "backgroundColor": "#1a1a1a",
                        "color": "#f2f2f2",
                        "fontSize": "12px",
                    },
                    style_header={
                        "backgroundColor": "#D4AF37",
                        "color": "#000",
                        "fontWeight": "bold"
                    },
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
                )
            ])
        ])
    ]
)

# ======================================================
# === CALLBACKS ===
# ======================================================

@app.callback(
    [Output("filtro-ftd-agent", "options")],
    [Input("filtro-fecha", "start_date"), Input("filtro-fecha", "end_date")]
)
def cargar_agentes(start, end):
    dff = df.copy()
    if start and end:
        dff = dff[(dff["date"] >= start) & (dff["date"] <= end)]
    agents = sorted(dff["agent"].dropna().unique())
    opts = [{"label": a, "value": a} for a in agents]
    return opts, opts

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
        Input("filtro-ftd-agent", "value"),
        Input("filtro-fecha", "start_date"),
        Input("filtro-fecha", "end_date"),
        Input("input-tc", "value"),
    ],
)
def actualizar_dashboard(_, ftd_agents, start, end, tc):

    dff = df.copy()

    if ftd_agents:
        dff = dff[dff["agent"].isin(ftd_agents)]

    if start and end:
        dff = dff[(dff["date"] >= start) & (dff["date"] <= end)]

    # === BONUS SEMANAL ===
    dff["year"] = dff["date"].dt.year
    dff["month"] = dff["date"].dt.month
    dff["week"] = dff["date"].apply(lambda d: (d.day + d.replace(day=1).weekday() - 1) // 7 + 1)

    bonus = 0.0
    for _, r in dff.groupby(["agent", "year", "month", "week"]).size().reset_index(name="ftds").iterrows():
        if r.ftds >= 15: bonus += 150
        elif r.ftds >= 5: bonus += 1500 / tc
        elif r.ftds >= 4: bonus += 1000 / tc
        elif r.ftds >= 2: bonus += 500 / tc

    bonus = round(bonus, 2)

    total_usd = dff["usd_neto"].sum()
    total_comm = dff["commission_usd"].sum() + bonus
    total_ftd = len(dff)
    pct = dff["comm_pct"].max() if not dff.empty else 0

    card = lambda t, v: html.Div(
        [html.H4(t, style={"color": "#D4AF37"}), html.H2(v, style={"color": "#fff"})],
        style={
            "backgroundColor": "#1a1a1a",
            "borderRadius": "10px",
            "padding": "20px",
            "textAlign": "center",
            "boxShadow": "0 0 10px rgba(212,175,55,0.3)",
        }
    )

    fig = px.bar(
        dff.groupby("agent", as_index=False)["commission_usd"].sum(),
        x="agent", y="commission_usd",
        title="Comisión USD by Agent",
        color="commission_usd",
        color_continuous_scale="YlOrBr"
    )

    fig.update_layout(
        paper_bgcolor="#0d0d0d",
        plot_bgcolor="#0d0d0d",
        font_color="#f2f2f2",
        title_font_color="#D4AF37",
        xaxis_tickangle=-90
    )

    tabla = dff[[
        "date", "agent", "type", "team", "country", "affiliate",
        "usd", "ftd_num", "comm_pct", "commission_usd"
    ]].copy()

    tabla["comm_pct"] = tabla["comm_pct"].apply(lambda x: f"{x*100:.2f}%")
    tabla["commission_usd"] = tabla["commission_usd"].round(2)

    return (
        card("PORCENTAJE COMISIÓN", f"{pct*100:.2f}%"),
        card("VENTAS USD", f"{total_usd:,.2f}"),
        card("BONUS SEMANAL USD", f"{bonus:,.2f}"),
        card("COMISIÓN USD (TOTAL)", f"{total_comm:,.2f}"),
        card("TOTAL VENTAS (FTDs)", f"{total_ftd:,}"),
        fig,
        tabla.to_dict("records"),
    )

# ======================================================
if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8060, debug=True)
