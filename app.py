import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os

# ─────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────
FILE_PATH = "portfolio_data.csv"

def guardar_datos(df):
    df.to_csv(FILE_PATH, index=False)

def cargar_datos():
    if os.path.exists(FILE_PATH):
        return pd.read_csv(FILE_PATH)
    return pd.DataFrame(columns=["Ticker", "Nombre", "Compra", "Cantidad", "Mercado"])

if "portfolio" not in st.session_state:
    st.session_state.portfolio = cargar_datos()

if "vista" not in st.session_state:
    st.session_state.vista = "dashboard"

# ─────────────────────────────────────────
#  CSS GLOBAL — dark luxury / terminal feel
# ─────────────────────────────────────────
st.set_page_config(page_title="AI.lino PRO", layout="wide", page_icon="📈")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap');

/* ── Base ── */
html, body, [data-testid="stAppViewContainer"] {
    background: #080810 !important;
    color: #e8e8f0 !important;
    font-family: 'Syne', sans-serif !important;
}
[data-testid="stSidebar"] {
    background: #0c0c18 !important;
    border-right: 1px solid #1c1c30 !important;
    min-width: 290px !important;
    max-width: 290px !important;
}
[data-testid="stSidebar"] * { font-family: 'Syne', sans-serif !important; }

/* ── Hide default streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }
.block-container { padding: 0 2rem 2rem 2rem !important; max-width: 100% !important; }

/* ── Inputs ── */
input[type="text"], input[type="number"], .stTextInput input, .stNumberInput input {
    background: #10101e !important;
    border: 1px solid #2a2a44 !important;
    border-radius: 8px !important;
    color: #e8e8f0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
    padding: 8px 12px !important;
}
input:focus { border-color: #00ff9d !important; outline: none !important; box-shadow: 0 0 0 2px #00ff9d22 !important; }

/* ── Selectbox ── */
[data-testid="stSelectbox"] > div > div {
    background: #10101e !important;
    border: 1px solid #2a2a44 !important;
    border-radius: 8px !important;
    color: #e8e8f0 !important;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #00ff9d18, #00ff9d33) !important;
    border: 1px solid #00ff9d55 !important;
    border-radius: 8px !important;
    color: #00ff9d !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    letter-spacing: 0.5px !important;
    transition: all 0.2s !important;
    padding: 8px 16px !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #00ff9d33, #00ff9d55) !important;
    border-color: #00ff9d !important;
    box-shadow: 0 0 16px #00ff9d33 !important;
}
.stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid #2a2a44 !important;
    color: #666688 !important;
}
.stButton > button[kind="secondary"]:hover {
    border-color: #ff4466 !important;
    color: #ff4466 !important;
    box-shadow: none !important;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: #0e0e1e !important;
    border: 1px solid #1c1c30 !important;
    border-radius: 12px !important;
    padding: 16px !important;
}
[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 22px !important;
    color: #00ff9d !important;
}
[data-testid="stMetricDelta"] { font-family: 'JetBrains Mono', monospace !important; }

/* ── Section labels ── */
.label-tag {
    font-size: 10px; letter-spacing: 3px; text-transform: uppercase;
    color: #444466; margin-bottom: 8px; font-family: 'JetBrains Mono', monospace;
}
.hero-pct {
    font-family: 'Syne', sans-serif; font-size: 56px; font-weight: 800;
    letter-spacing: -2px; line-height: 1;
}
.card {
    background: #0e0e1e; border: 1px solid #1c1c30; border-radius: 14px;
    padding: 20px; margin-bottom: 12px;
}
.ticker-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 14px; border-radius: 10px; border: 1px solid #1c1c30;
    margin-bottom: 8px; background: #0a0a16;
    transition: border-color 0.2s;
}
.ticker-row:hover { border-color: #2a2a50; }
.badge-up   { color: #00ff9d; font-family: 'JetBrains Mono'; font-size: 12px; font-weight: 500; }
.badge-down { color: #ff4466; font-family: 'JetBrains Mono'; font-size: 12px; font-weight: 500; }
.badge-neu  { color: #888; font-family: 'JetBrains Mono'; font-size: 12px; }
.divider { border: none; border-top: 1px solid #1c1c30; margin: 16px 0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
#  MOTOR CUANTITATIVO
# ─────────────────────────────────────────
def motor_avanzado(ticker):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty:
            return None
        close = df["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        precios = close.dropna().values.flatten().astype(float)
        if len(precios) < 2:
            return None
        xhat, P, Q, R = precios[0], 1.0, 1e-5, 0.01**2
        for p in precios:
            Pminus = P + Q
            K = Pminus / (Pminus + R)
            xhat = xhat + K * (float(p) - xhat)
            P = (1 - K) * Pminus
        return float(xhat), float(precios[-1])
    except:
        return None

@st.cache_data(ttl=300)
def get_historico(ticker, period, interval="1d"):
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return None
        close = df["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        s = close.dropna()
        s.index = pd.to_datetime(s.index)
        return s
    except:
        return None

# ─────────────────────────────────────────
#  ETFs / ÍNDICES DE REFERENCIA
# ─────────────────────────────────────────
BENCHMARKS = {
    "S&P 500 (SPY)":         {"ticker": "SPY",  "color": "#f59e0b"},
    "NASDAQ 100 (QQQ)":      {"ticker": "QQQ",  "color": "#6b7280"},
    "México BOLSA (EWW)":    {"ticker": "EWW",  "color": "#10b981"},
    "Bono Treasury 1-3Y":    {"ticker": "SHY",  "color": "#3b82f6"},
    "Oro (GLD)":             {"ticker": "GLD",  "color": "#eab308"},
    "Mercados Emergentes":   {"ticker": "EEM",  "color": "#8b5cf6"},
    "Europa (EZU)":          {"ticker": "EZU",  "color": "#ec4899"},
    "Dividendos (VYM)":      {"ticker": "VYM",  "color": "#06b6d4"},
}

PERIODOS = {
    "1 semana": "5d",
    "1 mes":    "1mo",
    "6 meses":  "6mo",
    "1 año":    "1y",
    "Máx":      "5y",
}

# ─────────────────────────────────────────
#  SIDEBAR — Buscador + Lista
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding: 20px 4px 8px'>
        <div style='font-family:Syne;font-size:22px;font-weight:800;letter-spacing:-0.5px;color:#e8e8f0'>
            AI<span style='color:#00ff9d'>.lino</span> PRO
        </div>
        <div style='font-family:JetBrains Mono;font-size:10px;letter-spacing:3px;color:#444466;margin-top:2px'>
            PORTFOLIO ENGINE
        </div>
    </div>
    <hr style='border-color:#1c1c30;margin:12px 0 20px'>
    """, unsafe_allow_html=True)

    # Navegación
    nav_items = {"📊  Dashboard": "dashboard", "⚡  Comparación": "comparacion"}
    for label, key in nav_items.items():
        active = st.session_state.vista == key
        if st.button(
            label,
            use_container_width=True,
            key=f"nav_{key}",
            type="primary" if active else "secondary",
        ):
            st.session_state.vista = key
            st.rerun()

    st.markdown("<hr style='border-color:#1c1c30;margin:16px 0'>", unsafe_allow_html=True)
    st.markdown("<div class='label-tag'>Buscar acción</div>", unsafe_allow_html=True)

    query = st.text_input("", placeholder="Tesla, Bimbo, Apple…", label_visibility="collapsed")

    if query:
        with st.spinner("Buscando…"):
            try:
                resultados = yf.Search(query, max_results=7).quotes
            except:
                resultados = []

        if resultados:
            opciones = {
                f"{s['symbol']}  ·  {s.get('exchange','?')}  —  {s.get('longname', s.get('shortname',''))}": s["symbol"]
                for s in resultados
            }
            seleccion = st.selectbox("", list(opciones.keys()), label_visibility="collapsed")

            col_a, col_b = st.columns(2)
            p_compra = col_a.number_input("Precio compra", min_value=0.0, key="p_compra")
            cant = col_b.number_input("Cantidad", min_value=0.0, key="cant")

            if st.button("＋ Agregar al portafolio", use_container_width=True):
                ticker_final = opciones[seleccion]
                if ticker_final in st.session_state.portfolio["Ticker"].values:
                    st.warning(f"{ticker_final} ya existe.")
                else:
                    partes = seleccion.split("  ·  ")
                    mercado = partes[1].split("  —  ")[0].strip() if len(partes) > 1 else "N/A"
                    nombre  = partes[1].split("  —  ")[1].strip() if len(partes) > 1 and "  —  " in partes[1] else seleccion
                    nuevo = pd.DataFrame([{
                        "Ticker": ticker_final,
                        "Nombre": nombre,
                        "Compra": p_compra,
                        "Cantidad": cant,
                        "Mercado": mercado,
                    }])
                    st.session_state.portfolio = pd.concat(
                        [st.session_state.portfolio, nuevo], ignore_index=True
                    )
                    guardar_datos(st.session_state.portfolio)
                    st.success(f"✅ {ticker_final} agregado")
                    st.rerun()
        else:
            st.caption("Sin resultados.")

    # Lista del portafolio en sidebar
    st.markdown("<hr style='border-color:#1c1c30;margin:16px 0'>", unsafe_allow_html=True)
    st.markdown("<div class='label-tag'>Mis posiciones</div>", unsafe_allow_html=True)

    if st.session_state.portfolio.empty:
        st.markdown("<div style='color:#444466;font-size:13px;padding:8px 0'>Portafolio vacío. Agrega una acción ↑</div>", unsafe_allow_html=True)
    else:
        port = st.session_state.portfolio.reset_index(drop=True)
        for i in range(len(port)):
            row = port.iloc[i]
            stats = motor_avanzado(row["Ticker"])
            if stats:
                _, actual = stats
                rend = ((actual - float(row["Compra"])) / float(row["Compra"])) * 100 if float(row["Compra"]) > 0 else 0.0
                badge_class = "badge-up" if rend >= 0 else "badge-down"
                rend_str = f"{'▲' if rend>=0 else '▼'} {abs(rend):.2f}%"
            else:
                badge_class = "badge-neu"
                rend_str = "—"

            col1, col2 = st.columns([3, 2])
            col1.markdown(f"<div style='font-weight:700;font-size:14px'>{row['Ticker']}</div>"
                          f"<div style='font-size:11px;color:#444466;font-family:JetBrains Mono'>{row['Mercado']}</div>",
                          unsafe_allow_html=True)
            col2.markdown(f"<div class='{badge_class}' style='text-align:right;margin-top:4px'>{rend_str}</div>",
                          unsafe_allow_html=True)

            if st.button("✕", key=f"del_{row['Ticker']}", help="Eliminar", use_container_width=False):
                st.session_state.portfolio = (
                    st.session_state.portfolio.reset_index(drop=True)
                    .drop(index=i).reset_index(drop=True)
                )
                guardar_datos(st.session_state.portfolio)
                st.rerun()

            st.markdown("<div class='divider'></div>", unsafe_allow_html=True)


# ─────────────────────────────────────────
#  VISTA: DASHBOARD
# ─────────────────────────────────────────
if st.session_state.vista == "dashboard":

    st.markdown("""
    <div style='padding: 32px 0 8px'>
        <div class='label-tag'>RENDIMIENTO DEL PORTAFOLIO</div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.portfolio.empty:
        st.markdown("""
        <div style='background:#0e0e1e;border:1px solid #1c1c30;border-radius:16px;
                    padding:60px;text-align:center;margin-top:20px'>
            <div style='font-size:40px;margin-bottom:16px'>📈</div>
            <div style='font-size:18px;font-weight:700;color:#e8e8f0'>Portafolio vacío</div>
            <div style='color:#444466;font-size:14px;margin-top:8px'>
                Usa el panel izquierdo para buscar y agregar acciones
            </div>
        </div>
        """, unsafe_allow_html=True)

    else:
        port = st.session_state.portfolio.reset_index(drop=True)
        resumen = []
        total_actual = 0.0
        total_compra = 0.0

        for i in range(len(port)):
            row = port.iloc[i]
            stats = motor_avanzado(row["Ticker"])
            compra   = float(row["Compra"])
            cantidad = float(row["Cantidad"])
            if stats:
                trend, actual = stats
                rend      = ((actual - compra) / compra * 100) if compra > 0 else 0.0
                val_act   = actual * cantidad
                estado    = "VENDER (Techo)" if actual > trend * 1.05 else "MANTENER"
            else:
                actual, rend, val_act, estado = compra, 0.0, compra * cantidad, "SIN DATOS"

            total_actual += val_act
            total_compra += compra * cantidad
            resumen.append({
                "idx": i,
                "Ticker": row["Ticker"],
                "Nombre": row["Nombre"],
                "Mercado": row["Mercado"],
                "Precio Actual": round(actual, 2),
                "Rendimiento": round(rend, 2),
                "Valor Actual": round(val_act, 2),
                "Acción": estado,
            })

        df_res = pd.DataFrame(resumen)
        rend_total = ((total_actual - total_compra) / total_compra * 100) if total_compra > 0 else 0.0
        delta_dolar = total_actual - total_compra

        # ── Hero metrics ──
        color_hero = "#00ff9d" if rend_total >= 0 else "#ff4466"
        signo = "+" if rend_total >= 0 else ""
        st.markdown(f"""
        <div style='margin-bottom:24px'>
            <div class='hero-pct' style='color:{color_hero}'>{signo}{rend_total:.2f}%</div>
            <div style='font-family:JetBrains Mono;font-size:14px;color:{color_hero};margin-top:6px'>
                {'▲' if delta_dolar>=0 else '▼'} ${abs(delta_dolar):,.2f}
                <span style='color:#444466;margin-left:8px'>ganancia/pérdida total</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("💰 Valor Actual", f"${total_actual:,.2f}", f"{signo}${abs(delta_dolar):,.2f}")
        m2.metric("📦 Posiciones", len(df_res))
        alertas = len(df_res[df_res["Acción"] == "VENDER (Techo)"])
        m3.metric("🚨 Alertas venta", alertas)

        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

        # ── Gráfica barras rendimiento ──
        colores = ["#00ff9d" if x > 0 else "#ff4466" if x < 0 else "#444466"
                   for x in df_res["Rendimiento"]]
        fig = go.Figure(go.Bar(
            x=df_res["Ticker"],
            y=df_res["Rendimiento"],
            marker=dict(
                color=colores,
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            text=[f"{v:+.2f}%" for v in df_res["Rendimiento"]],
            textposition="outside",
            textfont=dict(family="JetBrains Mono", size=11, color="#e8e8f0"),
        ))
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0e0e1e",
            plot_bgcolor="#0e0e1e",
            font=dict(family="Syne"),
            title=dict(text="Rendimiento por posición (%)", font=dict(size=14, color="#e8e8f0")),
            margin=dict(l=16, r=16, t=48, b=16),
            height=300,
            bargap=0.35,
            xaxis=dict(showgrid=False, color="#444466"),
            yaxis=dict(gridcolor="#1c1c30", color="#444466", zeroline=True, zerolinecolor="#2a2a44"),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Tabla de posiciones ──
        st.markdown("<div class='label-tag' style='margin-top:16px'>Gestión de posiciones</div>", unsafe_allow_html=True)
        for _, r in df_res.iterrows():
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([1.5, 2, 1.5, 2.5, 0.8])
                c1.markdown(f"<div style='font-weight:700;font-size:15px'>{r['Ticker']}</div>"
                            f"<div style='font-size:11px;color:#444466;font-family:JetBrains Mono'>{r['Mercado']}</div>",
                            unsafe_allow_html=True)
                c2.markdown(f"<div style='font-size:12px;color:#888;margin-top:4px'>{r['Nombre'][:28]}</div>",
                            unsafe_allow_html=True)
                badge = "badge-up" if r["Rendimiento"] > 0 else "badge-down" if r["Rendimiento"] < 0 else "badge-neu"
                signo_r = "▲" if r["Rendimiento"] > 0 else "▼" if r["Rendimiento"] < 0 else "—"
                c3.markdown(f"<div class='{badge}' style='margin-top:6px'>{signo_r} {abs(r['Rendimiento']):.2f}%</div>",
                            unsafe_allow_html=True)
                c4.markdown(f"<div style='font-family:JetBrains Mono;font-size:13px;margin-top:4px;color:#e8e8f0'>"
                            f"${r['Valor Actual']:,.2f}</div>", unsafe_allow_html=True)

                if r["Acción"] == "VENDER (Techo)":
                    c4.markdown("<span style='color:#ff4466;font-size:11px'>🚨 Techo detectado</span>", unsafe_allow_html=True)
                elif r["Acción"] == "SIN DATOS":
                    c4.markdown("<span style='color:#888;font-size:11px'>⚠️ Sin datos</span>", unsafe_allow_html=True)
                else:
                    c4.markdown("<span style='color:#00ff9d;font-size:11px'>💎 MANTENER</span>", unsafe_allow_html=True)

                if c5.button("✕", key=f"dash_del_{r['Ticker']}", help="Eliminar"):
                    st.session_state.portfolio = (
                        st.session_state.portfolio.reset_index(drop=True)
                        .drop(index=int(r["idx"])).reset_index(drop=True)
                    )
                    guardar_datos(st.session_state.portfolio)
                    st.rerun()

                st.markdown("<div class='divider'></div>", unsafe_allow_html=True)


# ─────────────────────────────────────────
#  VISTA: COMPARACIÓN CON ETFs
# ─────────────────────────────────────────
elif st.session_state.vista == "comparacion":

    st.markdown("""
    <div style='padding: 32px 0 8px'>
        <div class='label-tag'>COMPARACIÓN DE RENDIMIENTO</div>
        <div style='font-size:28px;font-weight:800;letter-spacing:-0.5px'>
            Tu portafolio <span style='color:#444466'>vs</span> Mejores ETFs / Índices
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Controles
    col_p, col_b = st.columns([2, 3])
    with col_p:
        periodo_label = st.selectbox("Periodo", list(PERIODOS.keys()), index=2)
        periodo = PERIODOS[periodo_label]

    with col_b:
        bench_sel = st.multiselect(
            "Índices / ETFs a comparar",
            list(BENCHMARKS.keys()),
            default=["S&P 500 (SPY)", "NASDAQ 100 (QQQ)", "México BOLSA (EWW)", "Oro (GLD)"],
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Construir serie normalizada del portafolio ──
    def serie_portafolio_normalizada(port_df, period):
        """Pondera el historial por valor de compra de cada posición"""
        series_list = []
        pesos = []
        for i in range(len(port_df)):
            row = port_df.iloc[i]
            s = get_historico(row["Ticker"], period)
            if s is not None and len(s) > 1:
                peso = float(row["Compra"]) * float(row["Cantidad"])
                series_list.append(s)
                pesos.append(peso)

        if not series_list:
            return None

        # Alinear en índice común
        idx_comun = series_list[0].index
        for s in series_list[1:]:
            idx_comun = idx_comun.intersection(s.index)
        if len(idx_comun) < 2:
            return None

        total_peso = sum(pesos)
        combinada = sum(
            (s.reindex(idx_comun) / s.reindex(idx_comun).iloc[0]) * (p / total_peso)
            for s, p in zip(series_list, pesos)
        )
        # Normalizar a 100
        return (combinada / combinada.iloc[0]) * 100

    with st.spinner("Descargando datos de mercado…"):
        port = st.session_state.portfolio.reset_index(drop=True)
        serie_port = serie_portafolio_normalizada(port, periodo) if not port.empty else None

        series_bench = {}
        for nombre in bench_sel:
            cfg = BENCHMARKS[nombre]
            s = get_historico(cfg["ticker"], periodo)
            if s is not None and len(s) > 1:
                series_bench[nombre] = (s / s.iloc[0]) * 100

    # ── Figura principal ──
    fig = go.Figure()

    # Portafolio
    if serie_port is not None:
        rend_port = float(serie_port.iloc[-1]) - 100
        fig.add_trace(go.Scatter(
            x=serie_port.index,
            y=serie_port.values,
            name=f"Tu portafolio ({rend_port:+.2f}%)",
            line=dict(color="#00ff9d", width=3),
            fill="tozeroy",
            fillcolor="rgba(0,255,157,0.05)",
            hovertemplate="%{y:.2f}<extra>Tu portafolio</extra>",
        ))
    elif not port.empty:
        st.warning("No se pudo obtener historial del portafolio para el periodo seleccionado.")

    # Benchmarks
    leyenda_cards = []
    for nombre, serie in series_bench.items():
        cfg = BENCHMARKS[nombre]
        rend_b = float(serie.iloc[-1]) - 100
        supera = serie_port is not None and rend_b < rend_port
        leyenda_cards.append((nombre, cfg["color"], rend_b, supera))
        fig.add_trace(go.Scatter(
            x=serie.index,
            y=serie.values,
            name=f"{nombre} ({rend_b:+.2f}%)",
            line=dict(color=cfg["color"], width=1.8, dash="dot" if not supera else "solid"),
            hovertemplate=f"%{{y:.2f}}<extra>{nombre}</extra>",
            opacity=0.85,
        ))

    # Línea base 100
    fig.add_hline(y=100, line=dict(color="#2a2a44", dash="dash", width=1))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0e0e1e",
        plot_bgcolor="#0e0e1e",
        font=dict(family="Syne", color="#e8e8f0"),
        title=dict(
            text=f"Rendimiento normalizado — {periodo_label}  (base = 100)",
            font=dict(size=14, color="#e8e8f0"),
        ),
        legend=dict(
            bgcolor="#0a0a16", bordercolor="#1c1c30", borderwidth=1,
            font=dict(family="JetBrains Mono", size=11),
            x=0.01, y=0.99,
        ),
        margin=dict(l=16, r=16, t=56, b=16),
        height=460,
        xaxis=dict(gridcolor="#1c1c30", color="#444466", showgrid=False),
        yaxis=dict(gridcolor="#1c1c30", color="#444466", ticksuffix=""),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Cards de comparación ──
    st.markdown("<div class='label-tag' style='margin-top:8px'>Scorecard</div>", unsafe_allow_html=True)

    port_rend = float(serie_port.iloc[-1]) - 100 if serie_port is not None else None

    cols = st.columns(min(len(leyenda_cards), 4))
    for ci, (nombre, color, rend_b, _) in enumerate(leyenda_cards):
        with cols[ci % 4]:
            if port_rend is not None:
                diff = port_rend - rend_b
                gana = diff > 0
                icono = "🏆" if gana else "📉"
                diff_str = f"{'+'if gana else ''}{diff:.2f}%"
                diff_color = "#00ff9d" if gana else "#ff4466"
                verdict = "Tu portafolio GANA" if gana else "Tu portafolio PIERDE"
            else:
                icono, diff_str, diff_color, verdict = "—", "—", "#888", "Sin datos"

            st.markdown(f"""
            <div style='background:#0e0e1e;border:1px solid #1c1c30;border-left:3px solid {color};
                        border-radius:12px;padding:16px;margin-bottom:12px'>
                <div style='font-size:10px;letter-spacing:2px;color:#444466;font-family:JetBrains Mono;
                            text-transform:uppercase;margin-bottom:6px'>{nombre}</div>
                <div style='font-family:JetBrains Mono;font-size:20px;font-weight:500;
                            color:{"#00ff9d" if rend_b>=0 else "#ff4466"}'>{rend_b:+.2f}%</div>
                <div style='margin-top:10px;padding-top:10px;border-top:1px solid #1c1c30'>
                    <span style='font-size:14px'>{icono}</span>
                    <span style='font-family:JetBrains Mono;font-size:12px;color:{diff_color};margin-left:6px'>{diff_str}</span>
                    <div style='font-size:11px;color:#444466;margin-top:4px'>{verdict}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ── Tabla resumen ──
    if port_rend is not None and leyenda_cards:
        st.markdown("<div class='label-tag' style='margin-top:8px'>Ranking completo</div>", unsafe_allow_html=True)
        ranking = [("🟢 Tu portafolio", port_rend)] + [(n, r) for n, _, r, _ in leyenda_cards]
        ranking.sort(key=lambda x: x[1], reverse=True)
        for pos, (nombre, rend) in enumerate(ranking, 1):
            es_port = "portafolio" in nombre.lower()
            color_rend = "#00ff9d" if rend >= 0 else "#ff4466"
            st.markdown(f"""
            <div style='display:flex;align-items:center;gap:16px;
                        padding:10px 16px;border-radius:10px;margin-bottom:6px;
                        background:{"#00ff9d0a" if es_port else "#0a0a16"};
                        border:1px solid {"#00ff9d33" if es_port else "#1c1c30"}'>
                <div style='font-family:JetBrains Mono;color:#444466;font-size:13px;width:24px'>#{pos}</div>
                <div style='flex:1;font-weight:{"700" if es_port else "400"};font-size:14px'>{nombre}</div>
                <div style='font-family:JetBrains Mono;font-size:14px;color:{color_rend};font-weight:600'>
                    {rend:+.2f}%
                </div>
            </div>
            """, unsafe_allow_html=True)
