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
        print(f"⚠️ Error SQL, leyendo CSV local: {e}")

    return pd.read_csv("CMN_MASTER_preview.csv", dtype=str)

# === Carga base ===
df = cargar_datos()
df.columns = [c.strip().lower() for c in df.columns]

# === Fallbacks ===
if "type" not in df.columns:
    df["type"] = "FTD"

# === SOLO FTD ===
df = df[df["type"].str.upper() == "FTD"].copy()

# === Fechas ===
def convertir_fecha(valor):
    try:
        if "/" in valor:
            return pd.to_datetime(valor, format="%d/%m/%Y", errors="coerce")
        elif "-" in valor:
            return pd.to_datetime(str(valor).split(" ")[0], errors="coerce")
    except:
        return pd.NaT
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

# === Texto limpio ===
for col in ["team", "agent", "country", "affiliate"]:
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.title()
        df[col].replace({"Nan": None, "None": None, "": None}, inplace=True)

# === Comisión progresiva FTD ===
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

# === Conteo FTD por mes ===
df = df.sort_values(["agent", "date"]).reset_index(drop=True)
df["year_month"] = df["date"].dt.to_period("M")
df["ftd_num"] = df.groupby(["agent", "year_month"]).cumcount() + 1

# === Comisión ===
df["comm_pct"] = df["ftd_num"].apply(porcentaje_tramo_progresivo)
df["usd_neto"] = df["usd"]
df["commission_usd"] = df["usd"] * df["comm_pct"]

# ======================================================
# === DASH APP ===
# ======================================================

app = dash.Dash(__name__)
server = app.server
app.title = "OBL Digital — Dashboard Comisiones"

app.layout = html.Div(
    style={"backgroundColor": "#0d0d0d", "padding": "20px", "fontFamily": "Poppins"},
    children=[
        html.H1("💰 DASHBOARD COMISIONES POR AGENTE", style={"color": "#D4AF37", "textAlign": "center"}),

        html.Div(
            style={"display": "flex", "justifyContent": "space-between"},
            children=[
                html.Div(
                    style={"width": "25%", "backgroundColor": "#1a1a1a", "padding": "20px", "borderRadius": "12px"},
                    children=[
                        html.Label("Date Range", style={"color": "#D4AF37"}),
                        dcc.DatePickerRange(
                            id="filtro-fecha",
                            start_date=df["date"].min(),
                            end_date=df["date"].max(),
                            display_format="YYYY-MM-DD"
                        ),
                        html.Br(), html.Br(),
                        html.Label("FTD Agent", style={"color": "#D4AF37"}),
                        dcc.Dropdown(
                            id="filtro-ftd-agent",
                            multi=True,
                            placeholder="Selecciona FTD agent"
                        ),
                    ],
                ),

                html.Div(
                    style={"width": "72%"},
                    children=[
                        html.Div(
                            style={"display": "flex", "justifyContent": "space-around"},
                            children=[
                                html.Div(id="card-porcentaje"),
                                html.Div(id="card-usd-ventas"),
                                html.Div(id="card-usd-comision"),
                                html.Div(id="card-total-ftd"),
                            ]
                        ),
                        html.Br(),
                        dcc.Graph(id="grafico-comision-agent"),
                        html.Br(),
                        dash_table.DataTable(
                            id="tabla-detalle",
                            columns=[
                                {"name": "DATE", "id": "date"},
                                {"name": "AGENT", "id": "agent"},
                                {"name": "USD", "id": "usd"},
                                {"name": "FTD_NUM", "id": "ftd_num"},
                                {"name": "COMM_PCT", "id": "comm_pct"},
                                {"name": "COMMISSION_USD", "id": "commission_usd"},
                            ],
                            page_size=10,
                            style_cell={"backgroundColor": "#1a1a1a", "color": "#fff", "textAlign": "center"},
                            style_header={"backgroundColor": "#D4AF37", "color": "#000"},
                        ),
                    ],
                ),
            ],
        ),
    ],
)

@app.callback(
    Output("filtro-ftd-agent", "options"),
    Input("filtro-fecha", "start_date"),
    Input("filtro-fecha", "end_date"),
)
def cargar_agentes(start, end):
    df_f = df.copy()
    if start and end:
        df_f = df_f[(df_f["date"] >= start) & (df_f["date"] <= end)]
    agents = sorted(df_f["agent"].dropna().unique())
    return [{"label": a, "value": a} for a in agents]

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
    ],
)
def actualizar_dashboard(agents, start, end):
    df_f = df.copy()
    if agents:
        df_f = df_f[df_f["agent"].isin(agents)]
    if start and end:
        df_f = df_f[(df_f["date"] >= start) & (df_f["date"] <= end)]

    total_usd = df_f["usd"].sum()
    total_comm = df_f["commission_usd"].sum()
    total_ftd = len(df_f)
    pct = df_f["comm_pct"].max() if not df_f.empty else 0

    card = lambda t, v: html.Div([html.H4(t, style={"color": "#D4AF37"}), html.H2(v, style={"color": "#fff"})])

    fig = px.bar(
        df_f.groupby("agent", as_index=False)["commission_usd"].sum(),
        x="agent", y="commission_usd", title="Comisión USD by Agent"
    )
    fig.update_layout(paper_bgcolor="#0d0d0d", plot_bgcolor="#0d0d0d", font_color="#fff")

    df_tabla = df_f.copy()
    df_tabla["comm_pct"] = df_tabla["comm_pct"].apply(lambda x: f"{x*100:.2f}%")
    df_tabla["commission_usd"] = df_tabla["commission_usd"].round(2)

    return (
        card("PORCENTAJE COMISIÓN", f"{pct*100:.2f}%"),
        card("VENTAS USD", f"{total_usd:,.2f}"),
        card("COMISIÓN USD", f"{total_comm:,.2f}"),
        card("TOTAL FTDs", total_ftd),
        fig,
        df_tabla.to_dict("records"),
    )

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8060, debug=True)
