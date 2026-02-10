import re
import pandas as pd
import dash
from dash import html, dcc, Input, Output, dash_table
import plotly.express as px
from conexion_mysql import crear_conexion

# ======================================================
# === OBL DIGITAL DASHBOARD — SOLO FTD (VISTA ORIGINAL)
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

# === SOLO FTD ===
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

df["date"] = df["date"].apply(convertir_fecha)
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
for col in ["agent", "team", "country", "affiliate"]:
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

# === CONTEO POR MES (INTERNO, NO SALE AL CALLBACK) ===
df = df.sort_values(["agent", "date"]).reset_index(drop=True)
df["_year_month"] = df["date"].dt.to_period("M")   # 👈 PRIVADO
df["ftd_num"] = df.groupby(["agent", "_year_month"]).cumcount() + 1

df["comm_pct"] = df["ftd_num"].apply(porcentaje_tramo_progresivo)
df["commission_usd"] = df["usd_neto"] * df["comm_pct"]

# ======================================================
# === DASH APP (MISMA VISTA)
# ======================================================

app = dash.Dash(__name__)
server = app.server
app.title = "OBL Digital — Dashboard Comisiones"

app.layout = html.Div(
    style={"backgroundColor": "#0d0d0d", "padding": "20px", "fontFamily": "Poppins"},
    children=[
        html.H1("💰 DASHBOARD COMISIONES POR AGENTE", style={"color": "#D4AF37", "textAlign": "center"}),

        html.Div(style={"display": "flex", "justifyContent": "space-between"}, children=[

            # === FILTROS (IGUAL QUE ANTES) ===
            html.Div(style={"width": "25%", "backgroundColor": "#1a1a1a", "padding": "20px", "borderRadius": "12px"}, children=[
                html.Label("Date Range", style={"color": "#D4AF37"}),
                dcc.DatePickerRange(
                    id="filtro-fecha",
                    start_date=df["date"].min(),
                    end_date=df["date"].max(),
                    display_format="YYYY-MM-DD"
                ),
                html.Br(), html.Br(),

                html.Label("FTD Agent", style={"color": "#D4AF37"}),
                dcc.Dropdown(id="filtro-ftd-agent", multi=True),

                html.Br(),
                html.Label("Tipo de cambio (MXN/USD)", style={"color": "#D4AF37"}),
                dcc.Input(id="input-tc", type="number", value=18.19, step=0.01)
            ]),

            # === PANEL ===
            html.Div(style={"width": "72%"}, children=[
                html.Div(style={"display": "flex", "justifyContent": "space-around"}, children=[
                    html.Div(id="card-porcentaje"),
                    html.Div(id="card-usd-ventas"),
                    html.Div(id="card-usd-comision"),
                    html.Div(id="card-total-ftd"),
                ]),
                html.Br(),
                dcc.Graph(id="grafico-comision-agent"),
                html.Br(),
                dash_table.DataTable(
                    id="tabla-detalle",
                    page_size=10,
                    style_cell={"backgroundColor": "#1a1a1a", "color": "#fff", "textAlign": "center"},
                    style_header={"backgroundColor": "#D4AF37", "color": "#000"},
                    columns=[
                        {"name": "DATE", "id": "date"},
                        {"name": "AGENT", "id": "agent"},
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

# === CALLBACKS ===
@app.callback(
    Output("filtro-ftd-agent", "options"),
    Input("filtro-fecha", "start_date"),
    Input("filtro-fecha", "end_date"),
)
def cargar_agentes(start, end):
    dff = df.copy()
    if start and end:
        dff = dff[(dff["date"] >= start) & (dff["date"] <= end)]
    return [{"label": a, "value": a} for a in sorted(dff["agent"].dropna().unique())]

@app.callback(
    [
        Output("card-porcentaje", "children"),
        Output("card-usd-ventas", "children"),
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
def actualizar_dashboard(agents, start, end, tc):

    dff = df.copy()
    if agents:
        dff = dff[dff["agent"].isin(agents)]
    if start and end:
        dff = dff[(dff["date"] >= start) & (dff["date"] <= end)]

    total_usd = dff["usd_neto"].sum()
    total_comm = dff["commission_usd"].sum()
    total_ftd = len(dff)
    pct = dff["comm_pct"].max() if not dff.empty else 0

    card = lambda t, v: html.Div([html.H4(t, style={"color": "#D4AF37"}), html.H2(v, style={"color": "#fff"})])

    fig = px.bar(
        dff.groupby("agent", as_index=False)["commission_usd"].sum(),
        x="agent", y="commission_usd",
        title="Comisión USD by Agent"
    )
    fig.update_layout(paper_bgcolor="#0d0d0d", plot_bgcolor="#0d0d0d", font_color="#fff")

    tabla = dff[["date", "agent", "usd", "ftd_num", "comm_pct", "commission_usd"]].copy()
    tabla["comm_pct"] = tabla["comm_pct"].apply(lambda x: f"{x*100:.2f}%")
    tabla["commission_usd"] = tabla["commission_usd"].round(2)

    return (
        card("PORCENTAJE COMISIÓN", f"{pct*100:.2f}%"),
        card("VENTAS USD", f"{total_usd:,.2f}"),
        card("COMISIÓN USD", f"{total_comm:,.2f}"),
        card("TOTAL FTDs", total_ftd),
        fig,
        tabla.to_dict("records"),
    )

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8060, debug=True)
