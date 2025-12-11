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

# === Carga base ===
df = cargar_datos()
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

df["usd"] = df["usd"].apply(limpiar_usd)

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

df = df.sort_values(["agent", "date"]).reset_index(drop=True)
df["ftd_num"] = df.groupby("agent").cumcount() + 1
df["comm_pct"] = df["ftd_num"].apply(porcentaje_tramo_progresivo)
df["commission_usd"] = df["usd"] * df["comm_pct"]

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
                            sorted(df[df["type"].str.upper() == "RTN"]["agent"].dropna().unique()),
                            [],
                            multi=True,
                            id="filtro-rtn-agent",
                            placeholder="Selecciona RTN agent"
                        ),
                        html.Br(),

                        html.Label("FTD Agent", style={"color": "#D4AF37", "fontWeight": "bold"}),
                        dcc.Dropdown(
                            sorted(df[df["type"].str.upper() == "FTD"]["agent"].dropna().unique()),
                            [],
                            multi=True,
                            id="filtro-ftd-agent",
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

# === Callback ===
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
        Input("input-tc", "value")
    ],
)
def actualizar_dashboard(rtn_agents, ftd_agents, start_date, end_date, tipo_cambio):
    df_filtrado = df.copy()

    if rtn_agents or ftd_agents:
        agentes_seleccionados = []
        if rtn_agents:
            agentes_seleccionados += rtn_agents
        if ftd_agents:
            agentes_seleccionados += ftd_agents
        df_filtrado = df_filtrado[df_filtrado["agent"].isin(agentes_seleccionados)]

    if start_date and end_date:
        df_filtrado = df_filtrado[
            (df_filtrado["date"] >= pd.to_datetime(start_date)) &
            (df_filtrado["date"] <= pd.to_datetime(end_date))
        ]

    if df_filtrado.empty:
        fig_vacio = px.scatter(title="Sin datos para mostrar")
        fig_vacio.update_layout(paper_bgcolor="#0d0d0d", plot_bgcolor="#0d0d0d", font_color="#f2f2f2")
        vacio = html.Div("Sin datos", style={"color": "#D4AF37", "textAlign": "center"})
        return vacio, vacio, vacio, vacio, vacio, fig_vacio, []

    
    # === BONUS SEMANAL EXACTO (por semana del mes, en base a depósitos) ===
    df_filtrado["year"] = df_filtrado["date"].dt.year
    df_filtrado["month"] = df_filtrado["date"].dt.month

    def week_of_month(dt):
        first_day = dt.replace(day=1)
        adjusted = dt.day + first_day.weekday()
        return int((adjusted - 1) / 7) + 1

    df_filtrado["week_month"] = df_filtrado["date"].apply(week_of_month)

    # Cada fila = 1 depósito → contamos filas por semana
    df_semana = (
        df_filtrado.groupby(["agent", "year", "month", "week_month"])
        .size()
        .reset_index(name="ftds")
    )

    bonus_total_usd = 0.0

    for _, row in df_semana.iterrows():
        ftds = row["ftds"]
        weekly_usd = 0.0

        # === Reglas actualizadas del bonus por semana ===
        # 2 o más FTDs → 500 MXN
        # 4 o más FTDs → 1000 MXN
        # 5–14 FTDs → 1500 MXN
        # 15 o más FTDs → 150 USD directos

        if ftds >= 15:
            weekly_usd = 150  # USD directo
        elif ftds >= 5:
            weekly_usd = 1500 / tipo_cambio
        elif ftds >= 4:
            weekly_usd = 1000 / tipo_cambio
        elif ftds >= 2:
            weekly_usd = 500 / tipo_cambio

        bonus_total_usd += weekly_usd

    total_bonus = round(bonus_total_usd, 2)



    total_usd = df_filtrado["usd"].sum()
    total_commission = df_filtrado["commission_usd"].sum()
    total_commission_final = total_commission + total_bonus
    total_ftd = len(df_filtrado)
    promedio_pct = total_commission / total_usd if total_usd > 0 else 0.0

    # === Cards y gráfico (sin tocar estructura) ===
    card_style = {
        "backgroundColor": "#1a1a1a",
        "borderRadius": "10px",
        "padding": "20px",
        "textAlign": "center",
        "boxShadow": "0 0 10px rgba(212,175,55,0.3)",
    }

    def card(title, value):
        return html.Div([html.H4(title, style={"color": "#D4AF37"}), html.H2(value, style={"color": "#FFFFFF"})], style=card_style)

    fig_agent = px.bar(
        df_filtrado.groupby("agent", as_index=False)["commission_usd"].sum(),
        x="agent", y="commission_usd",
        title="Comisión USD by Agent",
        color="commission_usd",
        color_continuous_scale="YlOrBr"
    )
    fig_agent.update_layout(paper_bgcolor="#0d0d0d", plot_bgcolor="#0d0d0d", font_color="#f2f2f2", title_font_color="#D4AF37")

    df_tabla = df_filtrado[[
        "date", "agent", "type", "team", "country", "affiliate", "usd", "ftd_num", "comm_pct", "commission_usd"
    ]].copy()
    df_tabla["comm_pct"] = df_tabla["comm_pct"].apply(lambda x: f"{x*100:.2f}%")
    df_tabla["commission_usd"] = df_tabla["commission_usd"].round(2)

    return (
        card("PORCENTAJE COMISIÓN", f"{promedio_pct*100:,.2f}%"),
        card("VENTAS USD", f"{total_usd:,.2f}"),
        card("BONUS SEMANAL USD", f"{total_bonus:,.2f}"),
        card("COMISIÓN USD (TOTAL)", f"{total_commission_final:,.2f}"),
        card("TOTAL VENTAS (FTDs)", f"{total_ftd:,}"),
        fig_agent,
        df_tabla.to_dict("records")
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






