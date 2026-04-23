import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from itertools import combinations
import os, warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────
#  PERSISTENCIA
# ─────────────────────────────────────────
FILE_PATH = "portfolio_data.csv"

def guardar_datos(df):
    df.to_csv(FILE_PATH, index=False)

def cargar_datos():
    if os.path.exists(FILE_PATH):
        return pd.read_csv(FILE_PATH)
    return pd.DataFrame(columns=["Ticker","Nombre","Compra","Cantidad","Mercado"])

if "portfolio" not in st.session_state:
    st.session_state.portfolio = cargar_datos()
if "vista" not in st.session_state:
    st.session_state.vista = "dashboard"

# ─────────────────────────────────────────
#  CONFIG & CSS
# ─────────────────────────────────────────
st.set_page_config(page_title="AI.lino PRO", layout="wide", page_icon="📈")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap');
html,body,[data-testid="stAppViewContainer"]{background:#080810!important;color:#e8e8f0!important;font-family:'Syne',sans-serif!important}
[data-testid="stSidebar"]{background:#0c0c18!important;border-right:1px solid #1c1c30!important;min-width:290px!important;max-width:290px!important}
#MainMenu,footer,header{visibility:hidden}
[data-testid="stToolbar"]{display:none}
.block-container{padding:0 2rem 2rem 2rem!important;max-width:100%!important}
input[type="text"],input[type="number"],.stTextInput input,.stNumberInput input{background:#10101e!important;border:1px solid #2a2a44!important;border-radius:8px!important;color:#e8e8f0!important;font-family:'JetBrains Mono',monospace!important;font-size:13px!important}
[data-testid="stSelectbox"]>div>div{background:#10101e!important;border:1px solid #2a2a44!important;border-radius:8px!important;color:#e8e8f0!important}
.stButton>button{background:linear-gradient(135deg,#00ff9d18,#00ff9d33)!important;border:1px solid #00ff9d55!important;border-radius:8px!important;color:#00ff9d!important;font-family:'Syne',sans-serif!important;font-weight:700!important;font-size:13px!important}
.stButton>button:hover{background:linear-gradient(135deg,#00ff9d33,#00ff9d55)!important;box-shadow:0 0 16px #00ff9d33!important}
.stButton>button[kind="secondary"]{background:transparent!important;border:1px solid #2a2a44!important;color:#666688!important}
[data-testid="metric-container"]{background:#0e0e1e!important;border:1px solid #1c1c30!important;border-radius:12px!important;padding:16px!important}
[data-testid="stMetricValue"]{font-family:'JetBrains Mono',monospace!important;color:#00ff9d!important}
.label-tag{font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#444466;margin-bottom:8px;font-family:'JetBrains Mono',monospace}
.hero-pct{font-family:'Syne',sans-serif;font-size:56px;font-weight:800;letter-spacing:-2px;line-height:1}
.divider{border:none;border-top:1px solid #1c1c30;margin:10px 0}
.regime-bull{background:#00ff9d18;border:1px solid #00ff9d44;border-radius:10px;padding:12px 16px;color:#00ff9d;font-weight:700}
.regime-bear{background:#ff446618;border:1px solid #ff446644;border-radius:10px;padding:12px 16px;color:#ff4466;font-weight:700}
.regime-lat{background:#f59e0b18;border:1px solid #f59e0b44;border-radius:10px;padding:12px 16px;color:#f59e0b;font-weight:700}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
#  MOTOR CUANTITATIVO BASE
# ─────────────────────────────────────────
def motor_avanzado(ticker):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty: return None
        close = df["Close"]
        if hasattr(close,"columns"): close = close.iloc[:,0]
        precios = close.dropna().values.flatten().astype(float)
        if len(precios)<2: return None
        xhat,P,Q,R = precios[0],1.0,1e-5,0.01**2
        for p in precios:
            Pm=P+Q; K=Pm/(Pm+R); xhat=xhat+K*(float(p)-xhat); P=(1-K)*Pm
        return float(xhat), float(precios[-1])
    except: return None

@st.cache_data(ttl=300)
def get_historico(ticker, period, interval="1d"):
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty: return None
        close = df["Close"]
        if hasattr(close,"columns"): close = close.iloc[:,0]
        s = close.dropna()
        s.index = pd.to_datetime(s.index)
        return s
    except: return None

@st.cache_data(ttl=300)
def get_ohlcv(ticker, period="1y"):
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False)
        if df.empty: return None
        if hasattr(df.columns,"levels"): df.columns = df.columns.droplevel(1)
        df = df.dropna()
        df.index = pd.to_datetime(df.index)
        return df
    except: return None

# ─────────────────────────────────────────
#  INDICADORES TÉCNICOS
# ─────────────────────────────────────────
def calcular_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calcular_macd(series, fast=12, slow=26, signal=9):
    ema_fast   = series.ewm(span=fast, adjust=False).mean()
    ema_slow   = series.ewm(span=slow, adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line= macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram

def calcular_bollinger(series, period=20, std=2):
    sma   = series.rolling(period).mean()
    sigma = series.rolling(period).std()
    return sma + std*sigma, sma, sma - std*sigma

def senal_combinada(rsi, macd_hist, precio, bb_upper, bb_lower):
    """Score de -3 a +3 combinando señales"""
    score = 0
    if rsi < 30: score += 1
    elif rsi > 70: score -= 1
    if macd_hist > 0: score += 1
    elif macd_hist < 0: score -= 1
    if precio < bb_lower: score += 1
    elif precio > bb_upper: score -= 1
    return score

# ─────────────────────────────────────────
#  HMM DE RÉGIMEN DE MERCADO
# ─────────────────────────────────────────
def hmm_regimen(series, n_states=3, n_iter=100):
    """
    HMM Baum-Welch simplificado sobre retornos logarítmicos.
    Estados: 0=Bajista, 1=Lateral, 2=Alcista
    """
    returns = np.log(series / series.shift(1)).dropna().values
    T = len(returns)
    if T < 30: return None, None

    # Inicialización con k-means simple sobre retornos
    sorted_r = np.sort(returns)
    tercio   = T // 3
    means    = np.array([sorted_r[:tercio].mean(),
                         sorted_r[tercio:2*tercio].mean(),
                         sorted_r[2*tercio:].mean()])
    stds     = np.array([sorted_r[:tercio].std()+1e-6,
                         sorted_r[tercio:2*tercio].std()+1e-6,
                         sorted_r[2*tercio:].std()+1e-6])

    # Probabilidades iniciales y de transición
    pi  = np.array([1/3, 1/3, 1/3])
    A   = np.full((3,3), 1/3)  # Matriz de transición

    def emisiones(r, m, s):
        return np.exp(-0.5*((r-m)/s)**2) / (s*np.sqrt(2*np.pi)) + 1e-300

    for _ in range(n_iter):
        # ── Forward ──
        alpha = np.zeros((T,3))
        alpha[0] = pi * emisiones(returns[0], means, stds)
        alpha[0] /= alpha[0].sum()
        scales = np.zeros(T)
        scales[0] = alpha[0].sum() + 1e-300
        for t in range(1,T):
            em = emisiones(returns[t], means, stds)
            alpha[t] = (alpha[t-1] @ A) * em
            scales[t] = alpha[t].sum() + 1e-300
            alpha[t] /= scales[t]

        # ── Backward ──
        beta = np.zeros((T,3))
        beta[-1] = 1.0
        for t in range(T-2,-1,-1):
            em = emisiones(returns[t+1], means, stds)
            beta[t] = (A * em) @ beta[t+1]
            beta[t] /= beta[t].sum() + 1e-300

        # ── Gamma y Xi ──
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True) + 1e-300

        xi = np.zeros((T-1,3,3))
        for t in range(T-1):
            em = emisiones(returns[t+1], means, stds)
            xi[t] = alpha[t:t+1].T * A * em * beta[t+1]
            xi[t] /= xi[t].sum() + 1e-300

        # ── Re-estimación ──
        pi   = gamma[0]
        A    = xi.sum(axis=0) / (gamma[:-1].sum(axis=0, keepdims=True).T + 1e-300)
        A    /= A.sum(axis=1, keepdims=True) + 1e-300
        means = (gamma * returns[:,None]).sum(axis=0) / (gamma.sum(axis=0) + 1e-300)
        stds  = np.sqrt((gamma * (returns[:,None]-means)**2).sum(axis=0) / (gamma.sum(axis=0)+1e-300)) + 1e-6

    # Ordenar estados por media (0=bajista, 1=lateral, 2=alcista)
    orden    = np.argsort(means)
    estados  = np.argmax(gamma, axis=1)
    mapa     = {orden[i]:i for i in range(3)}
    estados  = np.array([mapa[e] for e in estados])

    return estados, series.iloc[1:].index

def nombre_regimen(estado):
    return ["🐻 BAJISTA","↔️ LATERAL","🐂 ALCISTA"][estado]

def clase_regimen(estado):
    return ["regime-bear","regime-lat","regime-bull"][estado]

def color_regimen(estado):
    return ["#ff4466","#f59e0b","#00ff9d"][estado]

# ─────────────────────────────────────────
#  KELLY CRITERION
# ─────────────────────────────────────────
def kelly_criterion(series):
    """Fracción óptima de Kelly basada en historial"""
    r = series.pct_change().dropna()
    wins  = r[r>0]
    losses= r[r<0]
    if len(wins)==0 or len(losses)==0: return 0
    p  = len(wins)/len(r)          # Prob de ganancia
    q  = 1 - p                     # Prob de pérdida
    b  = wins.mean() / abs(losses.mean()) if losses.mean()!=0 else 1
    k  = (b*p - q) / b             # Kelly formula
    return max(0.0, min(k, 0.5))   # Cap al 50% por seguridad

# ─────────────────────────────────────────
#  BACKTESTING — estrategia simple RSI+MACD
# ─────────────────────────────────────────
def backtest_estrategia(df, capital_inicial=10000):
    """
    Estrategia: COMPRAR cuando RSI<35 y MACD>0  |  VENDER cuando RSI>65 o MACD<0
    Compara contra Buy & Hold
    """
    close = df["Close"].astype(float)
    rsi   = calcular_rsi(close, 14)
    macd, sig, hist = calcular_macd(close)

    pos       = 0      # 0=fuera, 1=dentro
    capital   = capital_inicial
    acciones  = 0
    trades    = []
    portfolio_vals = []
    bnh_vals  = []
    precio_ini= float(close.iloc[0])

    for i in range(len(close)):
        p    = float(close.iloc[i])
        r    = float(rsi.iloc[i]) if not np.isnan(rsi.iloc[i]) else 50
        mh   = float(hist.iloc[i]) if not np.isnan(hist.iloc[i]) else 0
        date = close.index[i]

        # Señal de compra
        if pos == 0 and r < 35 and mh > 0 and capital > 0:
            acciones = capital / p
            capital  = 0
            pos      = 1
            trades.append({"Fecha": date, "Tipo": "COMPRA", "Precio": p, "RSI": r})

        # Señal de venta
        elif pos == 1 and (r > 65 or mh < -0.01):
            capital  = acciones * p
            acciones = 0
            pos      = 0
            trades.append({"Fecha": date, "Tipo": "VENTA", "Precio": p, "RSI": r})

        val = capital + acciones * p
        portfolio_vals.append(val)
        bnh_vals.append((capital_inicial / precio_ini) * p)

    # Cerrar posición abierta al final
    if pos == 1:
        capital = acciones * float(close.iloc[-1])

    total_return   = (capital / capital_inicial - 1) * 100
    bnh_return     = (bnh_vals[-1] / capital_inicial - 1) * 100

    # Métricas
    p_vals = pd.Series(portfolio_vals)
    daily_r= p_vals.pct_change().dropna()
    sharpe = (daily_r.mean() / daily_r.std() * np.sqrt(252)) if daily_r.std()>0 else 0
    max_dd = ((p_vals / p_vals.cummax()) - 1).min() * 100

    return {
        "portfolio_vals": portfolio_vals,
        "bnh_vals":       bnh_vals,
        "dates":          close.index.tolist(),
        "trades":         pd.DataFrame(trades) if trades else pd.DataFrame(),
        "total_return":   total_return,
        "bnh_return":     bnh_return,
        "sharpe":         sharpe,
        "max_drawdown":   max_dd,
        "n_trades":       len(trades),
    }

# ─────────────────────────────────────────
#  PAIRS TRADING
# ─────────────────────────────────────────
def analizar_par(t1, t2, period="6mo"):
    s1 = get_historico(t1, period)
    s2 = get_historico(t2, period)
    if s1 is None or s2 is None: return None

    idx = s1.index.intersection(s2.index)
    if len(idx) < 30: return None

    s1, s2 = s1.reindex(idx).astype(float), s2.reindex(idx).astype(float)

    # Correlación y ratio
    corr = s1.corr(s2)
    ratio= s1 / s2
    z    = (ratio - ratio.mean()) / ratio.std()
    z_now= float(z.iloc[-1])

    # Señal
    if z_now >  2.0: senal = f"VENDER {t1} / COMPRAR {t2}"
    elif z_now < -2.0: senal = f"COMPRAR {t1} / VENDER {t2}"
    else: senal = "NEUTRAL — spread en rango"

    return {
        "corr": corr, "z_now": z_now, "z": z,
        "ratio": ratio, "s1": s1, "s2": s2,
        "senal": senal, "idx": idx,
    }

# ─────────────────────────────────────────
#  ETFs BENCHMARK
# ─────────────────────────────────────────
BENCHMARKS = {
    "S&P 500 (SPY)":       {"ticker":"SPY",  "color":"#f59e0b"},
    "NASDAQ 100 (QQQ)":    {"ticker":"QQQ",  "color":"#6b7280"},
    "México BOLSA (EWW)":  {"ticker":"EWW",  "color":"#10b981"},
    "Bono Treasury 1-3Y":  {"ticker":"SHY",  "color":"#3b82f6"},
    "Oro (GLD)":           {"ticker":"GLD",  "color":"#eab308"},
    "Mercados Emergentes": {"ticker":"EEM",  "color":"#8b5cf6"},
    "Europa (EZU)":        {"ticker":"EZU",  "color":"#ec4899"},
    "Dividendos (VYM)":    {"ticker":"VYM",  "color":"#06b6d4"},
}
PERIODOS = {"1 semana":"5d","1 mes":"1mo","6 meses":"6mo","1 año":"1y","Máx":"5y"}

# ─────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding:20px 4px 8px'>
        <div style='font-family:Syne;font-size:22px;font-weight:800;color:#e8e8f0'>
            AI<span style='color:#00ff9d'>.lino</span> PRO
        </div>
        <div style='font-family:JetBrains Mono;font-size:10px;letter-spacing:3px;color:#444466;margin-top:2px'>
            QUANT ENGINE v3
        </div>
    </div>
    <hr style='border-color:#1c1c30;margin:8px 0 16px'>
    """, unsafe_allow_html=True)

    # Navegación
    vistas = {
        "📊  Dashboard":      "dashboard",
        "⚡  Comparación":    "comparacion",
        "🔬  Análisis Técnico":"tecnico",
        "🧬  Régimen HMM":    "hmm",
        "📈  Backtesting":    "backtest",
        "🔗  Pairs Trading":  "pairs",
        "⚖️  Kelly Sizing":   "kelly",
    }
    for label, key in vistas.items():
        active = st.session_state.vista == key
        if st.button(label, use_container_width=True, key=f"nav_{key}",
                     type="primary" if active else "secondary"):
            st.session_state.vista = key
            st.rerun()

    st.markdown("<hr style='border-color:#1c1c30;margin:12px 0'>", unsafe_allow_html=True)
    st.markdown("<div class='label-tag'>Buscar acción</div>", unsafe_allow_html=True)

    query = st.text_input("", placeholder="Tesla, Bimbo, Apple…", label_visibility="collapsed")
    if query:
        with st.spinner("Buscando…"):
            try: resultados = yf.Search(query, max_results=7).quotes
            except: resultados = []
        if resultados:
            opciones = {
                f"{s['symbol']}  ·  {s.get('exchange','?')}  —  {s.get('longname',s.get('shortname',''))}": s["symbol"]
                for s in resultados
            }
            seleccion = st.selectbox("", list(opciones.keys()), label_visibility="collapsed")
            col_a, col_b = st.columns(2)
            p_compra = col_a.number_input("Precio", min_value=0.0, key="p_compra")
            cant     = col_b.number_input("Cantidad", min_value=0.0, key="cant")
            if st.button("＋ Agregar", use_container_width=True):
                ticker_final = opciones[seleccion]
                if ticker_final in st.session_state.portfolio["Ticker"].values:
                    st.warning(f"{ticker_final} ya existe.")
                else:
                    partes  = seleccion.split("  ·  ")
                    mercado = partes[1].split("  —  ")[0].strip() if len(partes)>1 else "N/A"
                    nombre  = partes[1].split("  —  ")[1].strip() if len(partes)>1 and "  —  " in partes[1] else seleccion
                    nuevo   = pd.DataFrame([{"Ticker":ticker_final,"Nombre":nombre,"Compra":p_compra,"Cantidad":cant,"Mercado":mercado}])
                    st.session_state.portfolio = pd.concat([st.session_state.portfolio,nuevo],ignore_index=True)
                    guardar_datos(st.session_state.portfolio)
                    st.success(f"✅ {ticker_final} agregado")
                    st.rerun()
        else:
            st.caption("Sin resultados.")

    st.markdown("<hr style='border-color:#1c1c30;margin:12px 0'>", unsafe_allow_html=True)
    st.markdown("<div class='label-tag'>Mis posiciones</div>", unsafe_allow_html=True)

    port = st.session_state.portfolio.reset_index(drop=True)
    if port.empty:
        st.markdown("<div style='color:#444466;font-size:13px'>Portafolio vacío ↑</div>", unsafe_allow_html=True)
    else:
        for i in range(len(port)):
            row   = port.iloc[i]
            stats = motor_avanzado(row["Ticker"])
            if stats:
                _,actual = stats
                rend = ((actual-float(row["Compra"]))/float(row["Compra"])*100) if float(row["Compra"])>0 else 0
                badge = "badge-up" if rend>=0 else "badge-down"
                rstr  = f"{'▲' if rend>=0 else '▼'} {abs(rend):.2f}%"
            else:
                badge,rstr = "badge-neu","—"
            c1,c2 = st.columns([3,2])
            c1.markdown(f"<div style='font-weight:700;font-size:14px'>{row['Ticker']}</div>"
                        f"<div style='font-size:11px;color:#444466;font-family:JetBrains Mono'>{row['Mercado']}</div>",
                        unsafe_allow_html=True)
            c2.markdown(f"<div class='{badge}' style='text-align:right;margin-top:4px'>{rstr}</div>",
                        unsafe_allow_html=True)
            if st.button("✕", key=f"del_{row['Ticker']}", help="Eliminar"):
                st.session_state.portfolio = (
                    st.session_state.portfolio.reset_index(drop=True)
                    .drop(index=i).reset_index(drop=True)
                )
                guardar_datos(st.session_state.portfolio)
                st.rerun()
            st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════
#  VISTAS PRINCIPALES
# ═══════════════════════════════════════════════

# ─────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────
if st.session_state.vista == "dashboard":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>RENDIMIENTO DEL PORTAFOLIO</div></div>",
                unsafe_allow_html=True)

    port = st.session_state.portfolio.reset_index(drop=True)
    if port.empty:
        st.markdown("""<div style='background:#0e0e1e;border:1px solid #1c1c30;border-radius:16px;
                    padding:60px;text-align:center;margin-top:20px'>
            <div style='font-size:40px'>📈</div>
            <div style='font-size:18px;font-weight:700'>Portafolio vacío</div>
            <div style='color:#444466;font-size:14px;margin-top:8px'>Agrega acciones con el panel izquierdo</div>
        </div>""", unsafe_allow_html=True)
    else:
        resumen = []; total_act = 0; total_cmp = 0
        for i in range(len(port)):
            row   = port.iloc[i]
            stats = motor_avanzado(row["Ticker"])
            compra,cantidad = float(row["Compra"]),float(row["Cantidad"])
            if stats:
                trend,actual = stats
                rend   = ((actual-compra)/compra*100) if compra>0 else 0
                val    = actual*cantidad
                estado = "VENDER (Techo)" if actual>trend*1.05 else "MANTENER"
            else:
                actual,rend,val,estado = compra,0,compra*cantidad,"SIN DATOS"
            total_act+=val; total_cmp+=compra*cantidad
            resumen.append({"idx":i,"Ticker":row["Ticker"],"Nombre":row["Nombre"],
                            "Mercado":row["Mercado"],"Rendimiento":round(rend,2),
                            "Valor Actual":round(val,2),"Acción":estado})

        df_res = pd.DataFrame(resumen)
        rend_total = ((total_act-total_cmp)/total_cmp*100) if total_cmp>0 else 0
        delta_dol  = total_act-total_cmp
        color_h    = "#00ff9d" if rend_total>=0 else "#ff4466"
        signo      = "+" if rend_total>=0 else ""

        st.markdown(f"""<div style='margin-bottom:20px'>
            <div class='hero-pct' style='color:{color_h}'>{signo}{rend_total:.2f}%</div>
            <div style='font-family:JetBrains Mono;font-size:14px;color:{color_h};margin-top:6px'>
                {'▲' if delta_dol>=0 else '▼'} ${abs(delta_dol):,.2f}
                <span style='color:#444466;margin-left:8px'>total P&L</span>
            </div></div>""", unsafe_allow_html=True)

        m1,m2,m3 = st.columns(3)
        m1.metric("💰 Valor Actual", f"${total_act:,.2f}", f"{signo}${abs(delta_dol):,.2f}")
        m2.metric("📦 Posiciones", len(df_res))
        m3.metric("🚨 Alertas", len(df_res[df_res["Acción"]=="VENDER (Techo)"]))

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        colores = ["#00ff9d" if x>0 else "#ff4466" if x<0 else "#444466" for x in df_res["Rendimiento"]]
        fig = go.Figure(go.Bar(
            x=df_res["Ticker"], y=df_res["Rendimiento"], marker=dict(color=colores),
            text=[f"{v:+.2f}%" for v in df_res["Rendimiento"]], textposition="outside",
            textfont=dict(family="JetBrains Mono",size=11,color="#e8e8f0"),
        ))
        fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                          font=dict(family="Syne"),margin=dict(l=16,r=16,t=40,b=16),height=280,
                          bargap=0.35,xaxis=dict(showgrid=False,color="#444466"),
                          yaxis=dict(gridcolor="#1c1c30",color="#444466",zeroline=True,zerolinecolor="#2a2a44"))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("<div class='label-tag'>Gestión de posiciones</div>", unsafe_allow_html=True)
        for _,r in df_res.iterrows():
            c1,c2,c3,c4,c5 = st.columns([1.5,2,1.5,2.5,0.8])
            c1.markdown(f"<div style='font-weight:700;font-size:15px'>{r['Ticker']}</div>"
                        f"<div style='font-size:11px;color:#444466;font-family:JetBrains Mono'>{r['Mercado']}</div>",
                        unsafe_allow_html=True)
            c2.markdown(f"<div style='font-size:12px;color:#888;margin-top:4px'>{str(r['Nombre'])[:28]}</div>",
                        unsafe_allow_html=True)
            badge = "badge-up" if r["Rendimiento"]>0 else "badge-down" if r["Rendimiento"]<0 else "badge-neu"
            s2    = "▲" if r["Rendimiento"]>0 else "▼" if r["Rendimiento"]<0 else "—"
            c3.markdown(f"<div class='{badge}' style='margin-top:6px'>{s2} {abs(r['Rendimiento']):.2f}%</div>",
                        unsafe_allow_html=True)
            c4.markdown(f"<div style='font-family:JetBrains Mono;font-size:13px;margin-top:4px'>${r['Valor Actual']:,.2f}</div>",
                        unsafe_allow_html=True)
            etiqueta = ("🚨 Techo" if r["Acción"]=="VENDER (Techo)"
                        else "⚠️ Sin datos" if r["Acción"]=="SIN DATOS" else "💎 MANTENER")
            c4.markdown(f"<span style='font-size:11px'>{etiqueta}</span>", unsafe_allow_html=True)
            if c5.button("✕", key=f"dash_del_{r['Ticker']}"):
                st.session_state.portfolio = (
                    st.session_state.portfolio.reset_index(drop=True)
                    .drop(index=int(r["idx"])).reset_index(drop=True)
                )
                guardar_datos(st.session_state.portfolio)
                st.rerun()
            st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────
#  COMPARACIÓN
# ─────────────────────────────────────────
elif st.session_state.vista == "comparacion":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>TU PORTAFOLIO VS MEJORES ETFs</div>"
                "<div style='font-size:28px;font-weight:800;letter-spacing:-0.5px'>Comparación de Rendimiento</div></div>",
                unsafe_allow_html=True)

    col_p,col_b = st.columns([2,3])
    periodo_label = col_p.selectbox("Periodo",list(PERIODOS.keys()),index=2)
    periodo = PERIODOS[periodo_label]
    bench_sel = col_b.multiselect("ETFs a comparar",list(BENCHMARKS.keys()),
                    default=["S&P 500 (SPY)","NASDAQ 100 (QQQ)","México BOLSA (EWW)","Oro (GLD)"])

    def serie_port_norm(port_df, period):
        series_list=[]; pesos=[]
        for i in range(len(port_df)):
            row=port_df.iloc[i]
            s=get_historico(row["Ticker"],period)
            if s is not None and len(s)>1:
                series_list.append(s); pesos.append(float(row["Compra"])*float(row["Cantidad"]))
        if not series_list: return None
        idx_c=series_list[0].index
        for s in series_list[1:]: idx_c=idx_c.intersection(s.index)
        if len(idx_c)<2: return None
        total_p=sum(pesos)
        comb=sum((s.reindex(idx_c)/s.reindex(idx_c).iloc[0])*(p/total_p) for s,p in zip(series_list,pesos))
        return (comb/comb.iloc[0])*100

    with st.spinner("Descargando datos…"):
        port = st.session_state.portfolio.reset_index(drop=True)
        serie_port = serie_port_norm(port, periodo) if not port.empty else None
        series_bench={}
        for nb in bench_sel:
            s=get_historico(BENCHMARKS[nb]["ticker"],periodo)
            if s is not None and len(s)>1: series_bench[nb]=(s/s.iloc[0])*100

    fig = go.Figure()
    port_rend = None
    if serie_port is not None:
        port_rend = float(serie_port.iloc[-1])-100
        fig.add_trace(go.Scatter(x=serie_port.index,y=serie_port.values,
            name=f"Tu portafolio ({port_rend:+.2f}%)",
            line=dict(color="#00ff9d",width=3),fill="tozeroy",fillcolor="rgba(0,255,157,0.05)",
            hovertemplate="%{y:.2f}<extra>Tu portafolio</extra>"))

    leyenda_cards=[]
    for nb,serie in series_bench.items():
        cfg=BENCHMARKS[nb]; rb=float(serie.iloc[-1])-100
        leyenda_cards.append((nb,cfg["color"],rb))
        fig.add_trace(go.Scatter(x=serie.index,y=serie.values,
            name=f"{nb} ({rb:+.2f}%)",
            line=dict(color=cfg["color"],width=1.8),opacity=0.85,
            hovertemplate=f"%{{y:.2f}}<extra>{nb}</extra>"))

    fig.add_hline(y=100,line=dict(color="#2a2a44",dash="dash",width=1))
    fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                      font=dict(family="Syne",color="#e8e8f0"),
                      legend=dict(bgcolor="#0a0a16",bordercolor="#1c1c30",borderwidth=1,
                                  font=dict(family="JetBrains Mono",size=11)),
                      margin=dict(l=16,r=16,t=56,b=16),height=420,hovermode="x unified",
                      xaxis=dict(gridcolor="#1c1c30",color="#444466",showgrid=False),
                      yaxis=dict(gridcolor="#1c1c30",color="#444466"))
    st.plotly_chart(fig, use_container_width=True)

    if port_rend is not None and leyenda_cards:
        cols = st.columns(min(len(leyenda_cards),4))
        for ci,(nb,color,rb) in enumerate(leyenda_cards):
            diff=port_rend-rb; gana=diff>0
            with cols[ci%4]:
                st.markdown(f"""<div style='background:#0e0e1e;border:1px solid #1c1c30;
                    border-left:3px solid {color};border-radius:12px;padding:16px;margin-bottom:12px'>
                    <div style='font-size:10px;letter-spacing:2px;color:#444466;font-family:JetBrains Mono'>{nb}</div>
                    <div style='font-family:JetBrains Mono;font-size:20px;color:{"#00ff9d" if rb>=0 else "#ff4466"}'>{rb:+.2f}%</div>
                    <div style='margin-top:10px;padding-top:8px;border-top:1px solid #1c1c30'>
                        <span style='color:{"#00ff9d" if gana else "#ff4466"};font-family:JetBrains Mono;font-size:12px'>
                            {"🏆 +" if gana else "📉 "}{abs(diff):.2f}%
                        </span>
                        <div style='font-size:11px;color:#444466;margin-top:2px'>
                            {"Superando al índice" if gana else "Por debajo del índice"}
                        </div>
                    </div></div>""", unsafe_allow_html=True)

        # Ranking
        st.markdown("<div class='label-tag' style='margin-top:8px'>RANKING</div>", unsafe_allow_html=True)
        ranking=[("🟢 Tu portafolio",port_rend)]+[(n,r) for n,_,r in leyenda_cards]
        ranking.sort(key=lambda x:x[1],reverse=True)
        for pos,(nb,rend) in enumerate(ranking,1):
            es_p="portafolio" in nb.lower()
            cr="#00ff9d" if rend>=0 else "#ff4466"
            st.markdown(f"""<div style='display:flex;align-items:center;gap:16px;padding:10px 16px;
                border-radius:10px;margin-bottom:6px;background:{"#00ff9d0a" if es_p else "#0a0a16"};
                border:1px solid {"#00ff9d33" if es_p else "#1c1c30"}'>
                <div style='font-family:JetBrains Mono;color:#444466;font-size:13px;width:24px'>#{pos}</div>
                <div style='flex:1;font-weight:{"700" if es_p else "400"};font-size:14px'>{nb}</div>
                <div style='font-family:JetBrains Mono;font-size:14px;color:{cr};font-weight:600'>{rend:+.2f}%</div>
            </div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────
#  ANÁLISIS TÉCNICO — RSI + MACD + Bollinger
# ─────────────────────────────────────────
elif st.session_state.vista == "tecnico":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>ANÁLISIS TÉCNICO CUANTITATIVO</div>"
                "<div style='font-size:28px;font-weight:800'>RSI · MACD · Bollinger Bands</div></div>",
                unsafe_allow_html=True)

    port = st.session_state.portfolio.reset_index(drop=True)
    tickers_disponibles = port["Ticker"].tolist() if not port.empty else []

    col1,col2 = st.columns([2,2])
    ticker_manual = col1.text_input("O escribe cualquier ticker", placeholder="AAPL, TSLA, AMZN…")
    ticker_sel    = col2.selectbox("Desde tu portafolio", [""] + tickers_disponibles)
    ticker = ticker_manual.upper().strip() or ticker_sel
    periodo_tec = st.select_slider("Periodo", options=["3mo","6mo","1y","2y"], value="1y")

    if ticker:
        with st.spinner(f"Descargando {ticker}…"):
            df = get_ohlcv(ticker, periodo_tec)

        if df is None or df.empty:
            st.error("No se pudo obtener datos. Verifica el ticker.")
        else:
            close = df["Close"].astype(float)
            rsi   = calcular_rsi(close)
            macd_l, sig_l, hist = calcular_macd(close)
            bb_up, bb_mid, bb_lo = calcular_bollinger(close)

            # Score de señal actual
            rsi_now  = float(rsi.iloc[-1])  if not rsi.iloc[-1]  is np.nan else 50
            hist_now = float(hist.iloc[-1]) if not hist.iloc[-1] is np.nan else 0
            score    = senal_combinada(rsi_now, hist_now, float(close.iloc[-1]),
                                       float(bb_up.iloc[-1]), float(bb_lo.iloc[-1]))

            color_score = "#00ff9d" if score>0 else "#ff4466" if score<0 else "#f59e0b"
            label_score = ("🐂 ALCISTA — Señal de COMPRA" if score>=2
                           else "🐻 BAJISTA — Señal de VENTA" if score<=-2
                           else "↔️ NEUTRAL — Esperar confirmación")

            st.markdown(f"""<div style='background:#0e0e1e;border:1px solid {color_score}44;
                border-left:4px solid {color_score};border-radius:12px;padding:18px 22px;margin:16px 0'>
                <div style='font-family:JetBrains Mono;font-size:11px;color:#444466;letter-spacing:2px'>
                    SEÑAL COMBINADA — {ticker}</div>
                <div style='font-size:22px;font-weight:800;color:{color_score};margin-top:6px'>{label_score}</div>
                <div style='font-family:JetBrains Mono;font-size:13px;color:#888;margin-top:8px'>
                    RSI: {rsi_now:.1f} &nbsp;|&nbsp; MACD Hist: {hist_now:.4f} &nbsp;|&nbsp; Score: {score:+d}/3
                </div></div>""", unsafe_allow_html=True)

            # Gráfica principal con subplots
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                                row_heights=[0.55,0.25,0.20],
                                vertical_spacing=0.04,
                                subplot_titles=[f"{ticker} — Precio & Bollinger","MACD","RSI"])

            # Precio + Bollinger
            fig.add_trace(go.Scatter(x=close.index,y=bb_up,name="BB Superior",
                line=dict(color="#3b82f6",width=1,dash="dot"),showlegend=False),row=1,col=1)
            fig.add_trace(go.Scatter(x=close.index,y=bb_lo,name="BB Inferior",
                line=dict(color="#3b82f6",width=1,dash="dot"),fill="tonexty",
                fillcolor="rgba(59,130,246,0.05)",showlegend=False),row=1,col=1)
            fig.add_trace(go.Scatter(x=close.index,y=bb_mid,name="SMA20",
                line=dict(color="#6b7280",width=1),showlegend=False),row=1,col=1)
            fig.add_trace(go.Scatter(x=close.index,y=close,name="Precio",
                line=dict(color="#00ff9d",width=2)),row=1,col=1)

            # MACD
            colors_hist = ["#00ff9d" if v>=0 else "#ff4466" for v in hist]
            fig.add_trace(go.Bar(x=hist.index,y=hist,name="Histograma",
                marker_color=colors_hist,showlegend=False),row=2,col=1)
            fig.add_trace(go.Scatter(x=macd_l.index,y=macd_l,name="MACD",
                line=dict(color="#f59e0b",width=1.5)),row=2,col=1)
            fig.add_trace(go.Scatter(x=sig_l.index,y=sig_l,name="Señal",
                line=dict(color="#ec4899",width=1.5)),row=2,col=1)

            # RSI
            fig.add_trace(go.Scatter(x=rsi.index,y=rsi,name="RSI",
                line=dict(color="#8b5cf6",width=2),showlegend=False),row=3,col=1)
            fig.add_hline(y=70,line=dict(color="#ff4466",dash="dash",width=1),row=3,col=1)
            fig.add_hline(y=30,line=dict(color="#00ff9d",dash="dash",width=1),row=3,col=1)

            fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                              font=dict(family="Syne",color="#e8e8f0"),height=620,
                              margin=dict(l=16,r=16,t=40,b=16),hovermode="x unified",
                              legend=dict(bgcolor="#0a0a16",font=dict(family="JetBrains Mono",size=11)))
            for row in [1,2,3]:
                fig.update_xaxes(gridcolor="#1c1c30",color="#444466",showgrid=False,row=row,col=1)
                fig.update_yaxes(gridcolor="#1c1c30",color="#444466",row=row,col=1)
            st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────
#  HMM — RÉGIMEN DE MERCADO
# ─────────────────────────────────────────
elif st.session_state.vista == "hmm":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>HIDDEN MARKOV MODEL</div>"
                "<div style='font-size:28px;font-weight:800'>Detección de Régimen de Mercado</div></div>",
                unsafe_allow_html=True)
    st.markdown("<div style='color:#666;font-size:14px;margin-bottom:20px'>El HMM detecta automáticamente si el mercado "
                "está en fase <span style='color:#00ff9d'>alcista</span>, "
                "<span style='color:#ff4466'>bajista</span> o "
                "<span style='color:#f59e0b'>lateral</span> usando retornos logarítmicos.</div>",
                unsafe_allow_html=True)

    port = st.session_state.portfolio.reset_index(drop=True)
    col1,col2 = st.columns([2,2])
    ticker_manual = col1.text_input("Ticker", placeholder="SPY, QQQ, AAPL…")
    ticker_port   = col2.selectbox("O desde portafolio", [""] + port["Ticker"].tolist())
    ticker_hmm    = ticker_manual.upper().strip() or ticker_port
    periodo_hmm   = st.select_slider("Periodo análisis", options=["6mo","1y","2y","5y"], value="2y")

    if ticker_hmm:
        with st.spinner("Corriendo HMM Baum-Welch…"):
            serie = get_historico(ticker_hmm, periodo_hmm)

        if serie is None:
            st.error("No se pudo obtener datos.")
        else:
            estados, fechas = hmm_regimen(serie)
            if estados is None:
                st.warning("Datos insuficientes para HMM.")
            else:
                estado_actual = estados[-1]
                n_bull = (estados==2).sum()
                n_lat  = (estados==1).sum()
                n_bear = (estados==0).sum()
                total  = len(estados)

                # Estado actual
                clase = clase_regimen(estado_actual)
                st.markdown(f"""<div class='{clase}' style='margin:16px 0'>
                    <div style='font-size:11px;letter-spacing:2px;font-family:JetBrains Mono;opacity:0.7'>
                        RÉGIMEN ACTUAL — {ticker_hmm}</div>
                    <div style='font-size:26px;margin-top:4px'>{nombre_regimen(estado_actual)}</div>
                </div>""", unsafe_allow_html=True)

                # Distribución de regímenes
                c1,c2,c3 = st.columns(3)
                c1.metric("🐂 Alcista", f"{n_bull/total*100:.1f}%", f"{n_bull} días")
                c2.metric("↔️ Lateral",  f"{n_lat/total*100:.1f}%",  f"{n_lat} días")
                c3.metric("🐻 Bajista", f"{n_bear/total*100:.1f}%", f"{n_bear} días")

                # Gráfica de regímenes sobre precio
                colores_reg = [color_regimen(e) for e in estados]
                fig = make_subplots(rows=2,cols=1,shared_xaxes=True,
                                    row_heights=[0.7,0.3],vertical_spacing=0.04,
                                    subplot_titles=[f"{ticker_hmm} — Precio con Régimen","Estado HMM"])

                fig.add_trace(go.Scatter(x=fechas,y=serie.iloc[1:].values,
                    name="Precio",line=dict(color="#e8e8f0",width=2)),row=1,col=1)

                # Sombreado por régimen
                for e, color, lbl in [(2,"#00ff9d22","Alcista"),(1,"#f59e0b22","Lateral"),(0,"#ff446622","Bajista")]:
                    mask = estados==e
                    x_fill=[]; y_hi=[]; y_lo=[]
                    for j,m in enumerate(mask):
                        if m:
                            x_fill.append(fechas[j])
                            y_hi.append(float(serie.iloc[j+1]))
                            y_lo.append(0)
                    if x_fill:
                        fig.add_trace(go.Scatter(
                            x=x_fill+x_fill[::-1],
                            y=[serie.values.max()]*len(x_fill)+[serie.values.min()]*len(x_fill),
                            fill="toself",fillcolor=color,line=dict(width=0),
                            name=lbl,showlegend=True,opacity=0.5),row=1,col=1)

                # Timeline de estados
                fig.add_trace(go.Scatter(x=fechas,y=estados,
                    mode="markers",marker=dict(color=colores_reg,size=4,symbol="square"),
                    name="Estado",showlegend=False),row=2,col=1)
                fig.update_yaxes(tickvals=[0,1,2],ticktext=["Bajista","Lateral","Alcista"],row=2,col=1)

                fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                                  font=dict(family="Syne",color="#e8e8f0"),height=500,
                                  margin=dict(l=16,r=16,t=40,b=16),
                                  legend=dict(bgcolor="#0a0a16",font=dict(family="JetBrains Mono",size=11)))
                for row in [1,2]:
                    fig.update_xaxes(gridcolor="#1c1c30",color="#444466",showgrid=False,row=row,col=1)
                    fig.update_yaxes(gridcolor="#1c1c30",color="#444466",row=row,col=1)
                st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────
#  BACKTESTING
# ─────────────────────────────────────────
elif st.session_state.vista == "backtest":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>MOTOR DE BACKTESTING</div>"
                "<div style='font-size:28px;font-weight:800'>Estrategia RSI + MACD vs Buy & Hold</div></div>",
                unsafe_allow_html=True)

    port = st.session_state.portfolio.reset_index(drop=True)
    col1,col2,col3 = st.columns([2,2,1])
    ticker_manual = col1.text_input("Ticker", placeholder="AAPL, MSFT, SPY…")
    ticker_port   = col2.selectbox("O desde portafolio", [""] + port["Ticker"].tolist())
    capital_ini   = col3.number_input("Capital $", min_value=100.0, value=10000.0, step=1000.0)
    ticker_bt     = ticker_manual.upper().strip() or ticker_port
    periodo_bt    = st.select_slider("Periodo", options=["6mo","1y","2y","5y"], value="2y")

    if ticker_bt:
        with st.spinner("Corriendo backtest…"):
            df_bt = get_ohlcv(ticker_bt, periodo_bt)

        if df_bt is None:
            st.error("No se pudo obtener datos.")
        else:
            res = backtest_estrategia(df_bt, capital_ini)

            color_strat = "#00ff9d" if res["total_return"]>=0 else "#ff4466"
            color_bnh   = "#f59e0b" if res["bnh_return"]>=0 else "#ff4466"
            gana_strat  = res["total_return"] > res["bnh_return"]

            # Métricas
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("📈 Estrategia",   f"{res['total_return']:+.2f}%")
            c2.metric("📊 Buy & Hold",   f"{res['bnh_return']:+.2f}%")
            c3.metric("⚡ Sharpe Ratio", f"{res['sharpe']:.3f}")
            c4.metric("📉 Max Drawdown", f"{res['max_drawdown']:.2f}%")

            # Veredicto
            diff_bt = res["total_return"]-res["bnh_return"]
            color_v = "#00ff9d" if gana_strat else "#ff4466"
            veredicto = (f"✅ La estrategia SUPERA a Buy & Hold por {abs(diff_bt):.2f}%"
                         if gana_strat else f"❌ Buy & Hold supera a la estrategia por {abs(diff_bt):.2f}%")
            st.markdown(f"""<div style='background:#0e0e1e;border:1px solid {color_v}44;
                border-left:4px solid {color_v};border-radius:12px;padding:16px 20px;margin:16px 0'>
                <div style='font-size:16px;font-weight:700;color:{color_v}'>{veredicto}</div>
                <div style='font-family:JetBrains Mono;font-size:12px;color:#666;margin-top:6px'>
                    {res['n_trades']} operaciones ejecutadas en el periodo
                </div></div>""", unsafe_allow_html=True)

            # Gráfica de equity curves
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=res["dates"],y=res["portfolio_vals"],
                name=f"Estrategia RSI+MACD ({res['total_return']:+.2f}%)",
                line=dict(color="#00ff9d",width=2.5),
                fill="tozeroy",fillcolor="rgba(0,255,157,0.04)"))
            fig.add_trace(go.Scatter(x=res["dates"],y=res["bnh_vals"],
                name=f"Buy & Hold ({res['bnh_return']:+.2f}%)",
                line=dict(color="#f59e0b",width=2,dash="dot")))

            # Marcar trades
            if not res["trades"].empty:
                compras = res["trades"][res["trades"]["Tipo"]=="COMPRA"]
                ventas  = res["trades"][res["trades"]["Tipo"]=="VENTA"]
                if not compras.empty:
                    fig.add_trace(go.Scatter(
                        x=compras["Fecha"],y=compras["Precio"],mode="markers",
                        marker=dict(color="#00ff9d",size=8,symbol="triangle-up"),
                        name="Compra"))
                if not ventas.empty:
                    fig.add_trace(go.Scatter(
                        x=ventas["Fecha"],y=ventas["Precio"],mode="markers",
                        marker=dict(color="#ff4466",size=8,symbol="triangle-down"),
                        name="Venta"))

            fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                              font=dict(family="Syne",color="#e8e8f0"),height=420,
                              margin=dict(l=16,r=16,t=40,b=16),hovermode="x unified",
                              legend=dict(bgcolor="#0a0a16",font=dict(family="JetBrains Mono",size=11)),
                              xaxis=dict(gridcolor="#1c1c30",color="#444466",showgrid=False),
                              yaxis=dict(gridcolor="#1c1c30",color="#444466",title="Valor del portafolio ($)"))
            st.plotly_chart(fig, use_container_width=True)

            # Tabla de trades
            if not res["trades"].empty:
                st.markdown("<div class='label-tag'>Log de operaciones</div>", unsafe_allow_html=True)
                st.dataframe(
                    res["trades"].style.applymap(
                        lambda v: "color:#00ff9d" if v=="COMPRA" else "color:#ff4466" if v=="VENTA" else "",
                        subset=["Tipo"]
                    ),
                    use_container_width=True, height=220
                )

# ─────────────────────────────────────────
#  PAIRS TRADING
# ─────────────────────────────────────────
elif st.session_state.vista == "pairs":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>PAIRS TRADING — ARBITRAJE ESTADÍSTICO</div>"
                "<div style='font-size:28px;font-weight:800'>Detectar Divergencias entre Activos Correlacionados</div></div>",
                unsafe_allow_html=True)
    st.markdown("<div style='color:#666;font-size:14px;margin-bottom:20px'>"
                "Cuando dos activos históricamente correlacionados se separan, "
                "existe una oportunidad estadística de que converjan de nuevo.</div>",
                unsafe_allow_html=True)

    port = st.session_state.portfolio.reset_index(drop=True)
    tickers_port = port["Ticker"].tolist()

    col1,col2,col3 = st.columns(3)
    t1 = col1.text_input("Ticker 1", value=tickers_port[0] if len(tickers_port)>0 else "AAPL")
    t2 = col2.text_input("Ticker 2", value=tickers_port[1] if len(tickers_port)>1 else "MSFT")
    periodo_pairs = col3.selectbox("Periodo", ["3mo","6mo","1y"], index=1)

    # Auto-detectar pares del portafolio
    if len(tickers_port)>=2:
        with st.expander("🔍 Auto-detectar mejores pares del portafolio"):
            with st.spinner("Analizando correlaciones…"):
                resultados_pares=[]
                for ta,tb in combinations(tickers_port,2):
                    res_p=analizar_par(ta,tb,periodo_pairs)
                    if res_p:
                        resultados_pares.append({
                            "Par":f"{ta} / {tb}",
                            "Correlación":round(res_p["corr"],3),
                            "Z-Score":round(res_p["z_now"],2),
                            "Señal":res_p["senal"]
                        })
                if resultados_pares:
                    df_pares=pd.DataFrame(resultados_pares).sort_values("Correlación",ascending=False)
                    st.dataframe(df_pares,use_container_width=True,height=200)

    if t1 and t2:
        with st.spinner(f"Analizando {t1.upper()} / {t2.upper()}…"):
            res_par = analizar_par(t1.upper(), t2.upper(), periodo_pairs)

        if res_par is None:
            st.error("No se pudo obtener datos para el par.")
        else:
            corr_color = "#00ff9d" if res_par["corr"]>0.7 else "#f59e0b" if res_par["corr"]>0.4 else "#ff4466"
            z_color    = "#ff4466" if abs(res_par["z_now"])>2 else "#f59e0b" if abs(res_par["z_now"])>1 else "#00ff9d"

            c1,c2,c3 = st.columns(3)
            c1.metric("📊 Correlación", f"{res_par['corr']:.3f}")
            c2.metric("📐 Z-Score actual", f"{res_par['z_now']:.2f}")
            c3.metric("📍 Señal", "⚡ ACTIVA" if abs(res_par["z_now"])>2 else "💤 NEUTRAL")

            senal_color="#ff4466" if abs(res_par["z_now"])>2 else "#444466"
            st.markdown(f"""<div style='background:#0e0e1e;border:1px solid {senal_color}44;
                border-left:4px solid {senal_color};border-radius:12px;padding:16px 20px;margin:12px 0'>
                <div style='font-size:15px;font-weight:700;color:{senal_color}'>{res_par["senal"]}</div>
                <div style='font-family:JetBrains Mono;font-size:12px;color:#666;margin-top:4px'>
                    Z-Score > ±2.0 = señal estadística válida (confianza ~95%)
                </div></div>""", unsafe_allow_html=True)

            # Gráfica doble
            fig = make_subplots(rows=2,cols=1,shared_xaxes=True,
                                row_heights=[0.6,0.4],vertical_spacing=0.06,
                                subplot_titles=[f"Precios normalizados: {t1.upper()} vs {t2.upper()}","Z-Score del ratio"])

            s1n=(res_par["s1"]/res_par["s1"].iloc[0])*100
            s2n=(res_par["s2"]/res_par["s2"].iloc[0])*100
            fig.add_trace(go.Scatter(x=res_par["idx"],y=s1n,name=t1.upper(),
                line=dict(color="#00ff9d",width=2)),row=1,col=1)
            fig.add_trace(go.Scatter(x=res_par["idx"],y=s2n,name=t2.upper(),
                line=dict(color="#f59e0b",width=2)),row=1,col=1)

            z_colors=["#ff4466" if abs(v)>2 else "#f59e0b" if abs(v)>1 else "#444466" for v in res_par["z"]]
            fig.add_trace(go.Bar(x=res_par["idx"],y=res_par["z"],
                marker_color=z_colors,name="Z-Score",showlegend=False),row=2,col=1)
            fig.add_hline(y=2,line=dict(color="#ff4466",dash="dash",width=1),row=2,col=1)
            fig.add_hline(y=-2,line=dict(color="#ff4466",dash="dash",width=1),row=2,col=1)
            fig.add_hline(y=0,line=dict(color="#444466",width=1),row=2,col=1)

            fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                              font=dict(family="Syne",color="#e8e8f0"),height=500,
                              margin=dict(l=16,r=16,t=40,b=16),
                              legend=dict(bgcolor="#0a0a16",font=dict(family="JetBrains Mono",size=11)))
            for row in [1,2]:
                fig.update_xaxes(gridcolor="#1c1c30",color="#444466",showgrid=False,row=row,col=1)
                fig.update_yaxes(gridcolor="#1c1c30",color="#444466",row=row,col=1)
            st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────
#  KELLY CRITERION — POSITION SIZING
# ─────────────────────────────────────────
elif st.session_state.vista == "kelly":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>KELLY CRITERION — POSITION SIZING</div>"
                "<div style='font-size:28px;font-weight:800'>Tamaño Óptimo de Posición</div></div>",
                unsafe_allow_html=True)
    st.markdown("<div style='color:#666;font-size:14px;margin-bottom:20px'>"
                "El Criterio de Kelly calcula matemáticamente qué fracción de tu capital "
                "deberías arriesgar en cada posición para maximizar el crecimiento a largo plazo "
                "sin arriesgarte a la ruina. Renaissance usa variantes de este modelo.</div>",
                unsafe_allow_html=True)

    capital_total = st.number_input("Capital total disponible ($)", min_value=100.0, value=10000.0, step=500.0)

    port = st.session_state.portfolio.reset_index(drop=True)
    tickers_analizar = port["Ticker"].tolist()

    ticker_extra = st.text_input("Agregar ticker para analizar (opcional)", placeholder="NVDA, TSLA…")
    if ticker_extra.strip():
        tickers_analizar.append(ticker_extra.upper().strip())

    if not tickers_analizar:
        st.info("Agrega acciones a tu portafolio o escribe un ticker arriba.")
    else:
        with st.spinner("Calculando Kelly para cada posición…"):
            resultados_kelly=[]
            for tk in tickers_analizar:
                serie = get_historico(tk, "1y")
                if serie is not None and len(serie)>30:
                    k = kelly_criterion(serie)
                    r = serie.pct_change().dropna()
                    wins  = r[r>0]; losses = r[r<0]
                    resultados_kelly.append({
                        "Ticker":       tk,
                        "Kelly %":      round(k*100,2),
                        "Kelly/2 %":    round(k*50,2),   # Fracción conservadora
                        "$ Sugerido":   round(k*capital_total,2),
                        "$ Cons.":      round(k*0.5*capital_total,2),
                        "P(ganancia)":  round(len(wins)/len(r)*100,1),
                        "Win/Loss":     round(wins.mean()/abs(losses.mean()),2) if losses.mean()!=0 else 0,
                    })
                else:
                    resultados_kelly.append({
                        "Ticker":tk,"Kelly %":0,"Kelly/2 %":0,
                        "$ Sugerido":0,"$ Cons.":0,"P(ganancia)":0,"Win/Loss":0
                    })

        df_kelly = pd.DataFrame(resultados_kelly).sort_values("Kelly %",ascending=False)

        # Gráfica de barras Kelly
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_kelly["Ticker"], y=df_kelly["Kelly %"],
            name="Kelly completo",
            marker_color="#00ff9d",opacity=0.7,
            text=[f"{v:.1f}%" for v in df_kelly["Kelly %"]],textposition="outside",
            textfont=dict(family="JetBrains Mono",size=11)
        ))
        fig.add_trace(go.Bar(
            x=df_kelly["Ticker"], y=df_kelly["Kelly/2 %"],
            name="Kelly/2 (conservador)",
            marker_color="#3b82f6",opacity=0.9,
            text=[f"{v:.1f}%" for v in df_kelly["Kelly/2 %"]],textposition="inside",
            textfont=dict(family="JetBrains Mono",size=10)
        ))
        fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                          font=dict(family="Syne",color="#e8e8f0"),height=320,
                          barmode="group",bargap=0.2,
                          margin=dict(l=16,r=16,t=40,b=16),
                          legend=dict(bgcolor="#0a0a16",font=dict(family="JetBrains Mono",size=11)),
                          xaxis=dict(showgrid=False,color="#444466"),
                          yaxis=dict(gridcolor="#1c1c30",color="#444466",title="% del capital"))
        st.plotly_chart(fig, use_container_width=True)

        # Tabla detallada
        st.markdown("<div class='label-tag'>Desglose por posición</div>", unsafe_allow_html=True)
        for _,r in df_kelly.iterrows():
            k_pct = r["Kelly %"]
            color_k = "#00ff9d" if k_pct>15 else "#f59e0b" if k_pct>5 else "#666"
            st.markdown(f"""<div style='background:#0e0e1e;border:1px solid #1c1c30;
                border-left:3px solid {color_k};border-radius:12px;padding:14px 18px;margin-bottom:8px'>
                <div style='display:flex;justify-content:space-between;align-items:center'>
                    <div>
                        <span style='font-weight:800;font-size:15px'>{r['Ticker']}</span>
                        <span style='font-family:JetBrains Mono;font-size:12px;color:#666;margin-left:12px'>
                            P(win): {r['P(ganancia)']}% &nbsp;|&nbsp; W/L ratio: {r['Win/Loss']:.2f}
                        </span>
                    </div>
                    <div style='text-align:right'>
                        <span style='font-family:JetBrains Mono;font-size:18px;color:{color_k};font-weight:600'>
                            {k_pct:.1f}%
                        </span>
                        <div style='font-size:11px;color:#666;font-family:JetBrains Mono'>
                            ${r['$ Sugerido']:,.0f} full · ${r['$ Cons.']:,.0f} conservador
                        </div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)

        st.markdown("""<div style='background:#f59e0b0e;border:1px solid #f59e0b33;border-radius:10px;
            padding:14px 18px;margin-top:8px;font-size:13px;color:#f59e0b'>
            ⚠️ <strong>Kelly/2 es más robusto en la práctica.</strong>
            El Kelly completo asume distribuciones estables — en mercados reales,
            la versión conservadora reduce el riesgo de drawdowns severos.
            Renaissance usa variantes fraccionarias ajustadas por correlación entre posiciones.
        </div>""", unsafe_allow_html=True)
