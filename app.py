import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from itertools import combinations
import os, warnings, hashlib, json, base64, io
warnings.filterwarnings("ignore")

# ── Audio TTS via Web Speech API (sin dependencias extra) ──
def audio_tts_html(texto, autoplay=False):
    """Genera un widget HTML con Web Speech API para leer el texto en voz alta"""
    # Limpiar texto para JS
    texto_js = texto.replace("'", "\\'").replace("\n", " ").replace('"', '\\"')
    auto = "true" if autoplay else "false"
    return f"""
    <div style='background:#0e0e1e;border:1px solid #1c1c30;border-radius:10px;
                padding:10px 14px;display:flex;align-items:center;gap:10px;margin:8px 0'>
        <button id='tts_play' onclick='ttsToggle()'
            style='background:linear-gradient(135deg,#00ff9d22,#00ff9d44);
                   border:1px solid #00ff9d55;border-radius:8px;
                   color:#00ff9d;font-family:JetBrains Mono,monospace;
                   font-size:13px;font-weight:700;padding:6px 14px;cursor:pointer'>
            🔊 Escuchar análisis
        </button>
        <span id='tts_status' style='font-family:JetBrains Mono;font-size:11px;color:#444466'></span>
    </div>
    <script>
    var _tts_utt = null;
    var _tts_playing = false;
    function ttsToggle() {{
        if (_tts_playing) {{
            window.speechSynthesis.cancel();
            _tts_playing = false;
            document.getElementById('tts_play').textContent = '🔊 Escuchar análisis';
            document.getElementById('tts_status').textContent = '';
            return;
        }}
        window.speechSynthesis.cancel();
        _tts_utt = new SpeechSynthesisUtterance('{texto_js}');
        _tts_utt.lang = 'es-MX';
        _tts_utt.rate = 0.95;
        _tts_utt.pitch = 1.0;
        // Elegir voz en español si está disponible
        var voices = window.speechSynthesis.getVoices();
        var esVoice = voices.find(v => v.lang.startsWith('es'));
        if (esVoice) _tts_utt.voice = esVoice;
        _tts_utt.onstart  = function() {{
            _tts_playing = true;
            document.getElementById('tts_play').textContent = '⏹ Detener';
            document.getElementById('tts_status').textContent = '▶ reproduciendo…';
        }};
        _tts_utt.onend = function() {{
            _tts_playing = false;
            document.getElementById('tts_play').textContent = '🔊 Escuchar análisis';
            document.getElementById('tts_status').textContent = '✓ listo';
        }};
        window.speechSynthesis.speak(_tts_utt);
        {"window.speechSynthesis.speak(_tts_utt);" if autoplay else ""}
    }}
    // Cargar voces (Chrome las carga async)
    if (window.speechSynthesis.onvoiceschanged !== undefined) {{
        window.speechSynthesis.onvoiceschanged = function() {{}};
    }}
    </script>
    """

# ─────────────────────────────────────────
#  MULTI-USUARIO — cada usuario tiene su
#  propia carpeta con sus datos separados
# ─────────────────────────────────────────
USERS_FILE = "users.json"
DATA_DIR   = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def cargar_usuarios() -> dict:
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f:
            return json.load(f)
    return {}

def guardar_usuarios(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def registrar_usuario(username: str, password: str) -> tuple[bool, str]:
    users = cargar_usuarios()
    u = username.lower().strip()
    if not u or len(u) < 3:
        return False, "El usuario debe tener al menos 3 caracteres."
    if not password or len(password) < 4:
        return False, "La contraseña debe tener al menos 4 caracteres."
    if u in users:
        return False, "Ese usuario ya existe."
    users[u] = hash_password(password)
    guardar_usuarios(users)
    os.makedirs(f"{DATA_DIR}/{u}", exist_ok=True)
    return True, "✅ Cuenta creada. Ya puedes iniciar sesión."

def verificar_login(username: str, password: str) -> bool:
    users = cargar_usuarios()
    u = username.lower().strip()
    return u in users and users[u] == hash_password(password)

# Rutas de datos por usuario
def portfolio_path(u):  return f"{DATA_DIR}/{u}/portfolio.csv"
def watchlist_path(u):  return f"{DATA_DIR}/{u}/watchlist.csv"

def guardar_datos(df, u):
    os.makedirs(f"{DATA_DIR}/{u}", exist_ok=True)
    df.to_csv(portfolio_path(u), index=False)

def cargar_datos(u):
    p = portfolio_path(u)
    if os.path.exists(p):
        df = pd.read_csv(p)
        # Compatibilidad hacia atrás — si no existe columna Costo, calcularla
        if "Costo" not in df.columns:
            df["Costo"] = df["Compra"] * df["Cantidad"]
        return df
    return pd.DataFrame(columns=["Ticker","Nombre","Compra","Cantidad","Costo","Mercado"])

def guardar_watchlist(df, u):
    os.makedirs(f"{DATA_DIR}/{u}", exist_ok=True)
    df.to_csv(watchlist_path(u), index=False)

def cargar_watchlist(u):
    p = watchlist_path(u)
    if os.path.exists(p):
        return pd.read_csv(p)
    return pd.DataFrame(columns=["Ticker","Nombre","Mercado"])

# ── Session state base ──
if "logged_in"    not in st.session_state: st.session_state.logged_in    = False
if "username"     not in st.session_state: st.session_state.username     = ""
if "auth_mode"    not in st.session_state: st.session_state.auth_mode    = "login"
if "portfolio"    not in st.session_state: st.session_state.portfolio    = pd.DataFrame()
if "watchlist"    not in st.session_state: st.session_state.watchlist    = pd.DataFrame()
if "vista"        not in st.session_state: st.session_state.vista        = "dashboard"
if "moneda_base"  not in st.session_state: st.session_state.moneda_base  = "USD"
if "refresh_tick" not in st.session_state: st.session_state.refresh_tick = 0

# ─────────────────────────────────────────
#  CONFIG & CSS
# ─────────────────────────────────────────
st.set_page_config(page_title="AI.lino PRO", layout="wide", page_icon="📈")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap');

html,body,[data-testid="stAppViewContainer"]{
    background:#080810!important;color:#e8e8f0!important;font-family:'Syne',sans-serif!important}

[data-testid="stSidebar"]{
    background:#0c0c18!important;
    border-right:1px solid #1c1c30!important;
    min-width:300px!important;max-width:300px!important;
}

/* ══════════════════════════════════════
   EDGE BUTTON — botón nativo estilizado
   Funciona tanto abierto como cerrado
   ══════════════════════════════════════ */

/* Contenedor del botón cuando sidebar está CERRADO */
[data-testid="stSidebarCollapsedControl"] {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    height: 100vh !important;
    width: 20px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    z-index: 999999 !important;
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* La línea verde del edge cuando está CERRADO */
[data-testid="stSidebarCollapsedControl"]::before {
    content: '' !important;
    position: absolute !important;
    top: 0 !important; left: 9px !important;
    width: 2px !important; height: 100% !important;
    background: linear-gradient(180deg,
        transparent 0%,
        #00ff9d55 20%,
        #00ff9d 50%,
        #00ff9d55 80%,
        transparent 100%) !important;
    pointer-events: none !important;
}

/* El botón dentro del contenedor CERRADO */
[data-testid="stSidebarCollapsedControl"] button {
    position: absolute !important;
    top: 50% !important;
    left: 0 !important;
    transform: translateY(-50%) !important;
    width: 20px !important;
    height: 52px !important;
    padding: 0 !important;
    background: linear-gradient(160deg, #00ff9d, #00cc7a) !important;
    border: none !important;
    border-radius: 0 10px 10px 0 !important;
    box-shadow: 3px 0 16px #00ff9d77 !important;
    cursor: pointer !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    transition: width 0.15s, box-shadow 0.15s !important;
    z-index: 999999 !important;
}
[data-testid="stSidebarCollapsedControl"] button:hover {
    width: 26px !important;
    box-shadow: 4px 0 24px #00ff9dcc !important;
}
[data-testid="stSidebarCollapsedControl"] button svg {
    fill: #080810 !important;
    width: 14px !important;
    height: 14px !important;
}

/* Botón para CERRAR el sidebar (dentro del sidebar, esquina superior) */
[data-testid="stSidebar"] button[kind="header"],
[data-testid="stSidebarContent"] button[kind="header"] {
    position: fixed !important;
    top: 50% !important;
    left: 294px !important;
    transform: translateY(-50%) !important;
    width: 20px !important;
    height: 52px !important;
    padding: 0 !important;
    background: linear-gradient(160deg, #00ff9d, #00cc7a) !important;
    border: none !important;
    border-radius: 0 10px 10px 0 !important;
    box-shadow: 3px 0 16px #00ff9d77 !important;
    cursor: pointer !important;
    z-index: 999999 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    transition: width 0.15s !important;
}
[data-testid="stSidebar"] button[kind="header"]:hover,
[data-testid="stSidebarContent"] button[kind="header"]:hover {
    width: 26px !important;
    box-shadow: 4px 0 24px #00ff9dcc !important;
}
[data-testid="stSidebar"] button[kind="header"] svg,
[data-testid="stSidebarContent"] button[kind="header"] svg {
    fill: #080810 !important;
    width: 14px !important;
    height: 14px !important;
}

/* Solo ocultar el menú y footer — NO el header/toolbar donde vive el botón >> */
#MainMenu { visibility: hidden !important; }
footer    { visibility: hidden !important; }
.block-container{padding:0 2rem 2rem 2rem!important;max-width:100%!important}

input[type="text"],input[type="number"],.stTextInput input,.stNumberInput input{
    background:#10101e!important;border:1px solid #2a2a44!important;
    border-radius:8px!important;color:#e8e8f0!important;
    font-family:'JetBrains Mono',monospace!important;font-size:13px!important}
[data-testid="stSelectbox"]>div>div{
    background:#10101e!important;border:1px solid #2a2a44!important;
    border-radius:8px!important;color:#e8e8f0!important}

.stButton>button{
    background:linear-gradient(135deg,#00ff9d18,#00ff9d33)!important;
    border:1px solid #00ff9d55!important;border-radius:8px!important;
    color:#00ff9d!important;font-family:'Syne',sans-serif!important;
    font-weight:700!important;font-size:13px!important}
.stButton>button:hover{
    background:linear-gradient(135deg,#00ff9d33,#00ff9d55)!important;
    box-shadow:0 0 16px #00ff9d33!important}
.stButton>button[kind="secondary"]{
    background:transparent!important;border:1px solid #2a2a44!important;color:#666688!important}

[data-testid="metric-container"]{
    background:#0e0e1e!important;border:1px solid #1c1c30!important;
    border-radius:12px!important;padding:16px!important}
[data-testid="stMetricValue"]{font-family:'JetBrains Mono',monospace!important;color:#00ff9d!important}

.label-tag{font-size:10px;letter-spacing:3px;text-transform:uppercase;
    color:#444466;margin-bottom:8px;font-family:'JetBrains Mono',monospace}
.hero-pct{font-family:'Syne',sans-serif;font-size:56px;font-weight:800;letter-spacing:-2px;line-height:1}
.divider{border:none;border-top:1px solid #1c1c30;margin:10px 0}
.regime-bull{background:#00ff9d18;border:1px solid #00ff9d44;border-radius:10px;padding:12px 16px;color:#00ff9d;font-weight:700}
.regime-bear{background:#ff446618;border:1px solid #ff446644;border-radius:10px;padding:12px 16px;color:#ff4466;font-weight:700}
.regime-lat{background:#f59e0b18;border:1px solid #f59e0b44;border-radius:10px;padding:12px 16px;color:#f59e0b;font-weight:700}

.stock-card-rocket{background:linear-gradient(135deg,#00ff9d22,#00ff9d08);border:1px solid #00ff9d66;border-left:4px solid #00ff9d;border-radius:12px;padding:12px 14px;margin-bottom:8px;box-shadow:0 0 18px #00ff9d22}
.stock-card-up{background:linear-gradient(135deg,#22c55e22,#22c55e08);border:1px solid #22c55e55;border-left:4px solid #22c55e;border-radius:12px;padding:12px 14px;margin-bottom:8px}
.stock-card-neutral{background:linear-gradient(135deg,#f59e0b18,#f59e0b05);border:1px solid #f59e0b44;border-left:4px solid #f59e0b;border-radius:12px;padding:12px 14px;margin-bottom:8px}
.stock-card-down{background:linear-gradient(135deg,#ef444418,#ef444405);border:1px solid #ef444455;border-left:4px solid #ef4444;border-radius:12px;padding:12px 14px;margin-bottom:8px}
.stock-card-crash{background:linear-gradient(135deg,#ff004433,#ff004410);border:1px solid #ff0044;border-left:4px solid #ff0044;border-radius:12px;padding:12px 14px;margin-bottom:8px;box-shadow:0 0 18px #ff004433;animation:pulse-red 2s infinite}
@keyframes pulse-red{0%,100%{box-shadow:0 0 12px #ff004433}50%{box-shadow:0 0 28px #ff004466}}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
#  MOTOR CUANTITATIVO BASE
# ─────────────────────────────────────────
def motor_avanzado(ticker):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty: return None

        # FIX — extracción segura: funciona con Serie plana Y con DataFrame MultiIndex
        raw = df["Close"]
        if isinstance(raw, pd.DataFrame):
            close = raw.iloc[:, 0]
        elif isinstance(raw, pd.Series):
            close = raw
        else:
            return None

        precios = close.dropna().values.flatten().astype(float)
        if len(precios) < 2: return None

        xhat, P, Q, R = precios[0], 1.0, 1e-5, 0.01**2
        for p in precios:
            Pm = P + Q
            K  = Pm / (Pm + R)
            xhat = xhat + K * (float(p) - xhat)
            P    = (1 - K) * Pm

        return float(xhat), float(precios[-1])
    except:
        return None

@st.cache_data(ttl=300)
def _get_historico_raw(ticker, period, interval="1d"):
    """Descarga histórico con auto-retry de sufijos de mercado"""
    sufijos = ["", ".MX", ".BA", ".SA", ".L", ".PA", ".DE", ".MC", ".MI"]
    base = ticker.upper().strip().split(".")[0]

    for sfx in sufijos:
        t = base + sfx
        try:
            df = yf.download(t, period=period, interval=interval, progress=False)
            if df.empty: continue
            raw = df["Close"]
            if isinstance(raw, pd.DataFrame):
                s = raw.iloc[:, 0]
            elif isinstance(raw, pd.Series):
                s = raw
            else:
                continue
            s = s.dropna()
            if len(s) < 2: continue
            s.index = pd.to_datetime(s.index)
            return s, t
        except:
            continue
    return None, ticker

def resolver_ticker(ticker, period="1y"):
    s, _ = _get_historico_raw(ticker, period)
    return s

def get_historico(ticker, period, interval="1d"):
    s, _ = _get_historico_raw(ticker, period, interval)
    return s

@st.cache_data(ttl=300)
def get_ohlcv(ticker, period="1y"):
    """Descarga OHLCV completo con auto-retry de sufijos"""
    sufijos = ["", ".MX", ".BA", ".SA", ".L", ".PA", ".DE", ".MC", ".MI"]
    base = ticker.upper().strip().split(".")[0]
    for sfx in sufijos:
        t = base + sfx
        try:
            df = yf.download(t, period=period, interval="1d", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            df = df.dropna()
            df.index = pd.to_datetime(df.index)
            if len(df) < 2: continue
            return df
        except:
            continue
    return None

@st.cache_data(ttl=600)
def get_precio_actual(ticker):
    """Obtiene precio actual y datos básicos para mostrar en el buscador"""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        precio = (info.get("currentPrice") or info.get("regularMarketPrice")
                  or info.get("previousClose") or 0.0)
        return {
            "precio":    float(precio),
            "nombre":    info.get("longName") or info.get("shortName", ticker),
            "moneda":    info.get("currency", "USD"),
            "exchange":  info.get("exchange") or info.get("fullExchangeName", ""),
            "sector":    info.get("sector", "—"),
            "industria": info.get("industry", "—"),
        }
    except:
        return None

@st.cache_data(ttl=600)
def get_fundamentales(ticker):
    """Extrae métricas fundamentales via yfinance"""
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        def _f(k, dec=2):
            v = info.get(k)
            return round(float(v), dec) if v is not None else None
        def _fmt_mkt(v):
            if v is None: return "—"
            if v >= 1e12: return f"${v/1e12:.2f}T"
            if v >= 1e9:  return f"${v/1e9:.2f}B"
            if v >= 1e6:  return f"${v/1e6:.2f}M"
            return f"${v:,.0f}"
        return {
            # Valuación
            "pe_ratio":       _f("trailingPE"),
            "pe_forward":     _f("forwardPE"),
            "pb_ratio":       _f("priceToBook"),
            "ps_ratio":       _f("priceToSalesTrailing12Months"),
            "peg":            _f("pegRatio"),
            "ev_ebitda":      _f("enterpriseToEbitda"),
            # Rentabilidad
            "roe":            _f("returnOnEquity", 4),
            "roa":            _f("returnOnAssets", 4),
            "margen_bruto":   _f("grossMargins", 4),
            "margen_neto":    _f("profitMargins", 4),
            "margen_op":      _f("operatingMargins", 4),
            # Por acción
            "eps_ttm":        _f("trailingEps"),
            "eps_fwd":        _f("forwardEps"),
            "bvps":           _f("bookValue"),
            "div_yield":      _f("dividendYield", 4),
            "div_rate":       _f("dividendRate"),
            "payout":         _f("payoutRatio", 4),
            # Tamaño
            "mkt_cap":        _fmt_mkt(info.get("marketCap")),
            "enterprise_val": _fmt_mkt(info.get("enterpriseValue")),
            "revenue":        _fmt_mkt(info.get("totalRevenue")),
            "ebitda":         _fmt_mkt(info.get("ebitda")),
            # Deuda
            "debt_equity":    _f("debtToEquity"),
            "current_ratio":  _f("currentRatio"),
            "quick_ratio":    _f("quickRatio"),
            # Crecimiento
            "rev_growth":     _f("revenueGrowth", 4),
            "earn_growth":    _f("earningsGrowth", 4),
            # Info
            "nombre":         info.get("longName", ticker),
            "sector":         info.get("sector", "—"),
            "industria":      info.get("industry", "—"),
            "pais":           info.get("country", "—"),
            "bolsa":          info.get("exchange", "—"),
            "moneda":         info.get("currency", "USD"),
            "descripcion":    info.get("longBusinessSummary", ""),
            "precio":         float(info.get("currentPrice") or info.get("regularMarketPrice") or 0),
            "52w_high":       _f("fiftyTwoWeekHigh"),
            "52w_low":        _f("fiftyTwoWeekLow"),
            "beta":           _f("beta"),
            "empleados":      info.get("fullTimeEmployees"),
        }
    except:
        return None

# ─────────────────────────────────────────
#  TIPO DE CAMBIO — conversión multi-divisa
# ─────────────────────────────────────────
# TTL corto para datos frescos en tiempo real
@st.cache_data(ttl=60)
def get_tipo_cambio(moneda_origen, moneda_destino):
    """Obtiene el tipo de cambio entre dos monedas via yfinance"""
    if moneda_origen == moneda_destino:
        return 1.0
    par = f"{moneda_origen}{moneda_destino}=X"
    try:
        t = yf.Ticker(par)
        precio = (t.info.get("regularMarketPrice") or
                  t.info.get("currentPrice") or
                  t.info.get("previousClose"))
        if precio:
            return float(precio)
    except:
        pass
    return 1.0

@st.cache_data(ttl=60)
def get_moneda_ticker(ticker):
    """Detecta la moneda de cotización de un ticker"""
    try:
        info = yf.Ticker(ticker).info
        return info.get("currency", "USD").upper()
    except:
        # Inferir por sufijo
        if ticker.endswith(".MX"): return "MXN"
        if ticker.endswith(".L"):  return "GBP"
        if ticker.endswith(".PA") or ticker.endswith(".DE") or ticker.endswith(".MC"): return "EUR"
        if ticker.endswith(".SA"): return "BRL"
        return "USD"

# ─────────────────────────────────────────
#  MOTOR CUANTITATIVO — con conversión divisa
# ─────────────────────────────────────────
# TTL=60s para precios casi en tiempo real
@st.cache_data(ttl=60)
def motor_avanzado(ticker):
    """Kalman filter + precio actual. TTL=60s para refresh frecuente."""
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty: return None
        raw = df["Close"]
        if isinstance(raw, pd.DataFrame): close = raw.iloc[:, 0]
        elif isinstance(raw, pd.Series):  close = raw
        else: return None
        precios = close.dropna().values.flatten().astype(float)
        if len(precios) < 2: return None
        xhat, P, Q, R = precios[0], 1.0, 1e-5, 0.01**2
        for p in precios:
            Pm = P + Q; K = Pm / (Pm + R)
            xhat = xhat + K * (float(p) - xhat); P = (1 - K) * Pm
        moneda = get_moneda_ticker(ticker)
        return float(xhat), float(precios[-1]), moneda
    except:
        return None

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
    score = 0
    if rsi < 30: score += 1
    elif rsi > 70: score -= 1
    if macd_hist > 0: score += 1
    elif macd_hist < 0: score -= 1
    if precio < bb_lower: score += 1
    elif precio > bb_upper: score -= 1
    return score

# ─────────────────────────────────────────
#  HMM BIDIMENSIONAL — Simons style
#  Dimensión 1: retornos logarítmicos
#  Dimensión 2: volatilidad intrínseca
#              (desviación estándar móvil)
# ─────────────────────────────────────────
def hmm_regimen(series, n_states=3, n_iter=100, vol_window=10):
    """
    HMM Baum-Welch con observaciones 2D:
      obs[:,0] = log-retornos  (dirección)
      obs[:,1] = vol móvil normalizada (intensidad)
    Estados: 0=Bajista, 1=Lateral, 2=Alcista
    """
    log_ret = np.log(series / series.shift(1)).dropna()
    # Volatilidad intrínseca: std móvil de los retornos
    vol_raw = log_ret.rolling(vol_window).std().dropna()

    # Alinear ambas series al índice más corto
    idx_com = log_ret.index.intersection(vol_raw.index)
    ret = log_ret.reindex(idx_com).values.astype(float)
    vol = vol_raw.reindex(idx_com).values.astype(float)

    T = len(ret)
    if T < 30: return None, None

    # Normalizar vol a media 0, std 1 para misma escala que retornos
    vol_mean = vol.mean()
    vol_std  = vol.std() + 1e-9
    vol_norm = (vol - vol_mean) / vol_std

    # Observaciones 2D: [ret, vol_norm]
    obs = np.stack([ret, vol_norm], axis=1)  # (T, 2)

    # ── Inicializar con k-means 1D sobre retornos ──
    sorted_idx = np.argsort(ret)
    tercio = T // 3
    # Medias 2D por estado inicial
    means = np.array([
        obs[sorted_idx[:tercio]].mean(axis=0),
        obs[sorted_idx[tercio:2*tercio]].mean(axis=0),
        obs[sorted_idx[2*tercio:]].mean(axis=0),
    ])  # (3, 2)

    # Covarianzas diagonales por estado (independencia entre dims)
    covs = np.array([
        np.diag(obs[sorted_idx[:tercio]].var(axis=0) + 1e-6),
        np.diag(obs[sorted_idx[tercio:2*tercio]].var(axis=0) + 1e-6),
        np.diag(obs[sorted_idx[2*tercio:]].var(axis=0) + 1e-6),
    ])  # (3, 2, 2)

    pi = np.array([1/3, 1/3, 1/3])
    A  = np.full((3, 3), 1/3)

    def log_gauss_2d(x, m, C):
        """Log-verosimilitud gaussiana 2D con covarianza diagonal"""
        diff = x - m
        inv_diag = 1.0 / np.diag(C)
        return -0.5 * (np.sum(diff**2 * inv_diag) + np.log(np.linalg.det(C)) + 2*np.log(2*np.pi))

    def emisiones_2d(t_obs):
        """Probabilidades de emisión para una observación"""
        e = np.array([np.exp(log_gauss_2d(t_obs, means[k], covs[k])) + 1e-300
                      for k in range(3)])
        return e

    for _ in range(n_iter):
        # ── Forward ──
        alpha = np.zeros((T, 3))
        alpha[0] = pi * emisiones_2d(obs[0])
        alpha[0] /= alpha[0].sum() + 1e-300
        for t in range(1, T):
            em = emisiones_2d(obs[t])
            alpha[t] = (alpha[t-1] @ A) * em
            alpha[t] /= alpha[t].sum() + 1e-300

        # ── Backward ──
        beta = np.zeros((T, 3))
        beta[-1] = 1.0
        for t in range(T-2, -1, -1):
            em = emisiones_2d(obs[t+1])
            beta[t] = (A * em) @ beta[t+1]
            beta[t] /= beta[t].sum() + 1e-300

        # ── Gamma y Xi ──
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True) + 1e-300

        xi = np.zeros((T-1, 3, 3))
        for t in range(T-1):
            em = emisiones_2d(obs[t+1])
            xi[t] = alpha[t:t+1].T * A * em * beta[t+1]
            xi[t] /= xi[t].sum() + 1e-300

        # ── Re-estimación ──
        pi = gamma[0]
        A  = xi.sum(axis=0) / (gamma[:-1].sum(axis=0, keepdims=True).T + 1e-300)
        A /= A.sum(axis=1, keepdims=True) + 1e-300

        g_sum = gamma.sum(axis=0)  # (3,)
        for k in range(3):
            w = gamma[:, k]  # pesos del estado k
            means[k] = (w[:, None] * obs).sum(axis=0) / (w.sum() + 1e-300)
            diff = obs - means[k]
            covs[k] = np.diag(
                (w[:, None] * diff**2).sum(axis=0) / (w.sum() + 1e-300) + 1e-6
            )

    # ── Ordenar estados por retorno medio (dim 0) ──
    orden   = np.argsort(means[:, 0])   # bajista→lateral→alcista
    estados = np.argmax(gamma, axis=1)
    mapa    = {orden[i]: i for i in range(3)}
    estados = np.array([mapa[e] for e in estados])

    # Devolver índice alineado al obs (sin los primeros vol_window días)
    return estados, series.reindex(idx_com).index

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
    r = series.pct_change().dropna()
    wins  = r[r>0]; losses= r[r<0]
    if len(wins)==0 or len(losses)==0: return 0
    p  = len(wins)/len(r); q  = 1 - p
    b  = wins.mean() / abs(losses.mean()) if losses.mean()!=0 else 1
    k  = (b*p - q) / b
    return max(0.0, min(k, 0.5))

# ─────────────────────────────────────────
#  BACKTESTING
# ─────────────────────────────────────────
def backtest_estrategia(df, capital_inicial=10000):
    close = df["Close"].astype(float)
    rsi   = calcular_rsi(close, 14)
    macd, sig, hist = calcular_macd(close)
    pos=0; capital=capital_inicial; acciones=0; trades=[]; portfolio_vals=[]; bnh_vals=[]
    precio_ini= float(close.iloc[0])
    for i in range(len(close)):
        p=float(close.iloc[i]); r=float(rsi.iloc[i]) if not np.isnan(rsi.iloc[i]) else 50
        mh=float(hist.iloc[i]) if not np.isnan(hist.iloc[i]) else 0; date=close.index[i]
        if pos==0 and r<35 and mh>0 and capital>0:
            acciones=capital/p; capital=0; pos=1
            trades.append({"Fecha":date,"Tipo":"COMPRA","Precio":p,"RSI":r})
        elif pos==1 and (r>65 or mh<-0.01):
            capital=acciones*p; acciones=0; pos=0
            trades.append({"Fecha":date,"Tipo":"VENTA","Precio":p,"RSI":r})
        portfolio_vals.append(capital+acciones*p)
        bnh_vals.append((capital_inicial/precio_ini)*p)
    if pos==1: capital=acciones*float(close.iloc[-1])
    total_return=(capital/capital_inicial-1)*100
    bnh_return=(bnh_vals[-1]/capital_inicial-1)*100
    p_vals=pd.Series(portfolio_vals); daily_r=p_vals.pct_change().dropna()
    sharpe=(daily_r.mean()/daily_r.std()*np.sqrt(252)) if daily_r.std()>0 else 0
    max_dd=((p_vals/p_vals.cummax())-1).min()*100
    return {"portfolio_vals":portfolio_vals,"bnh_vals":bnh_vals,"dates":close.index.tolist(),
            "trades":pd.DataFrame(trades) if trades else pd.DataFrame(),
            "total_return":total_return,"bnh_return":bnh_return,"sharpe":sharpe,"max_drawdown":max_dd,"n_trades":len(trades)}

# ─────────────────────────────────────────
#  PAIRS TRADING
# ─────────────────────────────────────────
def analizar_par(t1, t2, period="6mo"):
    s1=get_historico(t1,period); s2=get_historico(t2,period)
    if s1 is None or s2 is None: return None
    idx=s1.index.intersection(s2.index)
    if len(idx)<30: return None
    s1,s2=s1.reindex(idx).astype(float),s2.reindex(idx).astype(float)
    corr=s1.corr(s2); ratio=s1/s2; z=(ratio-ratio.mean())/ratio.std(); z_now=float(z.iloc[-1])
    if z_now>2.0: senal=f"VENDER {t1} / COMPRAR {t2}"
    elif z_now<-2.0: senal=f"COMPRAR {t1} / VENDER {t2}"
    else: senal="NEUTRAL — spread en rango"
    return {"corr":corr,"z_now":z_now,"z":z,"ratio":ratio,"s1":s1,"s2":s2,"senal":senal,"idx":idx}

# ─────────────────────────────────────────
#  BENCHMARKS
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
#  PANTALLA DE LOGIN / REGISTRO
# ─────────────────────────────────────────
if not st.session_state.logged_in:
    # Centrar con columnas
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("""
        <div style='text-align:center;padding:40px 0 24px'>
            <div style='font-family:Syne;font-size:36px;font-weight:800;color:#e8e8f0'>
                AI<span style='color:#00ff9d'>.lino</span> PRO
            </div>
            <div style='font-family:JetBrains Mono;font-size:11px;letter-spacing:3px;
                        color:#444466;margin-top:4px'>QUANT ENGINE · MULTI-USUARIO</div>
        </div>
        """, unsafe_allow_html=True)

        modo = st.radio("", ["🔑  Iniciar sesión", "📝  Crear cuenta"],
                        horizontal=True, label_visibility="collapsed")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        user_in = st.text_input("Usuario", placeholder="tu_usuario", key="auth_user")
        pass_in = st.text_input("Contraseña", type="password", placeholder="••••••••", key="auth_pass")

        if modo == "🔑  Iniciar sesión":
            if st.button("Entrar →", use_container_width=True):
                if verificar_login(user_in, pass_in):
                    u = user_in.lower().strip()
                    st.session_state.logged_in = True
                    st.session_state.username  = u
                    st.session_state.portfolio = cargar_datos(u)
                    st.session_state.watchlist = cargar_watchlist(u)
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        else:
            if st.button("Crear cuenta →", use_container_width=True):
                ok, msg = registrar_usuario(user_in, pass_in)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

        st.markdown("""
        <div style='text-align:center;margin-top:24px;font-size:12px;color:#444466'>
            Cada usuario tiene su portafolio y seguimiento privado e independiente.
        </div>
        """, unsafe_allow_html=True)

    st.stop()   # ← nada más se ejecuta si no hay sesión

# ── Shortcut al usuario activo ──
U = st.session_state.username

# ─────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style='padding:20px 4px 8px'>
        <div style='font-family:Syne;font-size:22px;font-weight:800;color:#e8e8f0'>
            AI<span style='color:#00ff9d'>.lino</span> PRO
        </div>
        <div style='font-family:JetBrains Mono;font-size:10px;letter-spacing:3px;color:#444466;margin-top:2px'>
            QUANT ENGINE v3
        </div>
        <div style='margin-top:10px;background:#00ff9d11;border:1px solid #00ff9d33;
                    border-radius:8px;padding:6px 10px;font-family:JetBrains Mono;
                    font-size:12px;color:#00ff9d'>
            👤 {U}
        </div>
    </div>
    <hr style='border-color:#1c1c30;margin:8px 0 12px'>
    """, unsafe_allow_html=True)

    if st.button("🚪 Cerrar sesión", use_container_width=True, type="secondary"):
        st.session_state.logged_in = False
        st.session_state.username  = ""
        st.session_state.portfolio = pd.DataFrame()
        st.session_state.watchlist = pd.DataFrame()
        st.session_state.vista     = "dashboard"
        st.rerun()

    # ── Moneda base ──
    st.markdown("<div class='label-tag' style='margin-top:10px'>Moneda base</div>",
                unsafe_allow_html=True)
    moneda_opts = {"🇺🇸 USD": "USD", "🇲🇽 MXN": "MXN", "🇪🇺 EUR": "EUR"}
    moneda_sel = st.radio("", list(moneda_opts.keys()),
                          index=list(moneda_opts.values()).index(st.session_state.moneda_base),
                          horizontal=True, label_visibility="collapsed")
    st.session_state.moneda_base = moneda_opts[moneda_sel]
    MONEDA = st.session_state.moneda_base

    # ── Auto-refresh ──
    import time as _time
    ahora = _time.strftime("%H:%M:%S")
    st.markdown(f"""
    <div style='background:#0a0a16;border:1px solid #1c1c30;border-radius:8px;
                padding:8px 12px;margin:8px 0;display:flex;justify-content:space-between;
                align-items:center'>
        <span style='font-family:JetBrains Mono;font-size:10px;color:#444466'>
            🔄 Última act.
        </span>
        <span style='font-family:JetBrains Mono;font-size:11px;color:#00ff9d'>{ahora}</span>
    </div>
    """, unsafe_allow_html=True)

    # Auto-refresh cada 60 segundos usando st.rerun con time_input dummy
    # Streamlit no tiene auto-refresh nativo, usamos fragment trick vía JS
    st.components.v1.html("""
    <script>
    // Recargar la página cada 60 segundos para obtener precios frescos
    if (!window._ailino_refresh) {
        window._ailino_refresh = true;
        setTimeout(function refresh() {
            // Simular click en cualquier widget para forzar rerun de Streamlit
            var btns = window.parent.document.querySelectorAll('[data-testid="stButton"] button');
            // En lugar de click, usar postMessage a Streamlit
            window.parent.postMessage({type: 'streamlit:rerun'}, '*');
            setTimeout(refresh, 60000);
        }, 60000);
    }
    </script>
    """, height=0)

    vistas = {
        "📊  Dashboard":        "dashboard",
        "👁️  Seguimiento":      "seguimiento",
        "⚡  Comparación":      "comparacion",
        "🔬  Análisis Técnico": "tecnico",
        "📋  Fundamental":      "fundamental",
        "🧬  Régimen HMM":      "hmm",
        "📈  Backtesting":      "backtest",
        "🔗  Pairs Trading":    "pairs",
        "⚖️  Kelly Sizing":     "kelly",
        "🧪  Lab Quant":        "lab",
        "🎯  Motor Decisión":   "motor",
        "🔬  Validación Pro":   "validacion",
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
            ticker_final = opciones[seleccion]
            partes  = seleccion.split("  ·  ")
            mercado = partes[1].split("  —  ")[0].strip() if len(partes)>1 else "N/A"
            nombre  = partes[1].split("  —  ")[1].strip() if len(partes)>1 and "  —  " in partes[1] else seleccion

            # ── Tarjeta con precio actual y datos clave ──
            with st.spinner("Obteniendo precio…"):
                info_vivo = get_precio_actual(ticker_final)

            if info_vivo and info_vivo["precio"] > 0:
                p_vivo   = info_vivo["precio"]
                moneda   = info_vivo["moneda"]
                sector   = info_vivo["sector"]
                st.markdown(f"""
                <div style='background:#0a0a20;border:1px solid #00ff9d44;border-radius:10px;
                            padding:12px 14px;margin:8px 0'>
                    <div style='font-size:11px;color:#444466;font-family:JetBrains Mono;
                                letter-spacing:1px;margin-bottom:4px'>{ticker_final} · {info_vivo["exchange"]}</div>
                    <div style='font-size:11px;color:#888;margin-bottom:6px'>{info_vivo["nombre"][:40]}</div>
                    <div style='display:flex;justify-content:space-between;align-items:center'>
                        <span style='font-family:JetBrains Mono;font-size:20px;
                                     font-weight:700;color:#00ff9d'>{moneda} {p_vivo:,.4f}</span>
                        <span style='font-size:11px;color:#556;font-family:JetBrains Mono'>{sector}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                precio_sugerido = p_vivo
            else:
                precio_sugerido = 0.0
                st.caption("No se pudo obtener precio en tiempo real.")

            # ── Costo base con precio sugerido pre-llenado ──
            st.markdown("""<div style='font-size:10px;letter-spacing:2px;color:#444466;
                        font-family:JetBrains Mono;margin:8px 0 4px'>COSTO BASE</div>""",
                        unsafe_allow_html=True)

            col_a, col_b = st.columns(2)
            costo_total = col_a.number_input(
                "Total invertido $",
                min_value=0.0, value=0.0, step=10.0,
                key="costo_total",
                help="Cuánto dinero pusiste en total (ej: $500)"
            )
            cant = col_b.number_input(
                "Acciones (fracciones ok)",
                min_value=0.0, value=0.0, step=0.001,
                format="%.4f",
                key="cant",
                help="Pueden ser fracciones (ej: 0.5, 1.25)"
            )

            # Si tiene precio vivo y pone solo acciones, calcular costo automático
            if cant > 0 and costo_total == 0 and precio_sugerido > 0:
                costo_auto = cant * precio_sugerido
                st.markdown(f"""
                <div style='background:#3b82f611;border:1px solid #3b82f644;border-radius:8px;
                            padding:8px 12px;margin:4px 0;font-family:JetBrains Mono;font-size:12px'>
                    <span style='color:#3b82f6'>💡 Costo estimado al precio actual:</span>
                    <span style='color:#e8e8f0;font-weight:700;margin-left:6px'>${costo_auto:,.2f}</span>
                </div>""", unsafe_allow_html=True)

            if cant > 0 and costo_total > 0:
                precio_promedio = costo_total / cant
                st.markdown(f"""
                <div style='background:#00ff9d0a;border:1px solid #00ff9d33;
                            border-radius:8px;padding:8px 12px;margin:6px 0;
                            font-family:JetBrains Mono;font-size:12px'>
                    <span style='color:#444466'>Precio promedio pagado:</span>
                    <span style='color:#00ff9d;font-weight:700;margin-left:8px'>${precio_promedio:,.4f}</span>
                    {"&nbsp;&nbsp;<span style='color:#f59e0b'>⚠️ pagaste más que el precio actual</span>" if precio_sugerido > 0 and precio_promedio > precio_sugerido else ""}
                </div>""", unsafe_allow_html=True)
            else:
                precio_promedio = costo_total / cant if cant > 0 else 0.0

            # ── Dos botones: portafolio o seguimiento ──
            st.markdown("<div style='font-size:10px;letter-spacing:2px;color:#444466;font-family:JetBrains Mono;margin-top:8px'>¿DÓNDE AGREGAR?</div>", unsafe_allow_html=True)
            ba, bb = st.columns(2)
            add_port  = ba.button("💼 Portafolio",  key="btn_add_port",  use_container_width=True)
            add_watch = bb.button("👁️ Seguimiento", key="btn_add_watch", use_container_width=True)

            if add_port:
                if ticker_final in st.session_state.portfolio["Ticker"].values:
                    st.warning(f"{ticker_final} ya está en el portafolio.")
                elif costo_total <= 0 or cant <= 0:
                    st.error("Ingresa el total invertido y las acciones.")
                else:
                    nuevo = pd.DataFrame([{
                        "Ticker":   ticker_final,
                        "Nombre":   nombre,
                        "Compra":   round(precio_promedio, 6),   # precio por acción
                        "Cantidad": round(cant, 6),               # soporta fracciones
                        "Costo":    round(costo_total, 2),        # total invertido real
                        "Mercado":  mercado,
                    }])
                    st.session_state.portfolio = pd.concat([st.session_state.portfolio,nuevo],ignore_index=True)
                    guardar_datos(st.session_state.portfolio, U)
                    st.success(f"✅ {ticker_final} → Portafolio | ${costo_total:.2f} · {cant:.4f} acc")
                    st.rerun()

            if add_watch:
                if ticker_final in st.session_state.watchlist["Ticker"].values:
                    st.warning(f"{ticker_final} ya está en Seguimiento.")
                else:
                    nuevo = pd.DataFrame([{"Ticker":ticker_final,"Nombre":nombre,"Mercado":mercado}])
                    st.session_state.watchlist = pd.concat([st.session_state.watchlist,nuevo],ignore_index=True)
                    guardar_watchlist(st.session_state.watchlist, U)
                    st.success(f"👁️ {ticker_final} → Seguimiento")
                    st.rerun()
        else:
            st.caption("Sin resultados.")

    st.markdown("<hr style='border-color:#1c1c30;margin:12px 0'>", unsafe_allow_html=True)
    st.markdown("<div class='label-tag'>Mis posiciones</div>", unsafe_allow_html=True)

    port = st.session_state.portfolio.reset_index(drop=True)
    if port.empty:
        st.markdown("<div style='color:#444466;font-size:13px;padding:8px 0'>Portafolio vacío ↑</div>", unsafe_allow_html=True)
    else:
        for i in range(len(port)):
            row   = port.iloc[i]
            stats = motor_avanzado(row["Ticker"])
            if stats:
                trend, actual, moneda_acc = stats
                compra  = float(row["Compra"])
                rend    = ((actual - compra) / compra * 100) if compra > 0 else 0.0
                techo   = actual > trend * 1.05
            else:
                moneda_acc = "USD"
                rend  = None
                techo = False

            # ── Paleta por rendimiento ──
            if rend is None:
                card_class="stock-card-neutral"; emoji="⚪"; rend_str="Sin datos"; rend_color="#888"; barra_pct=50; barra_color="#888"
            elif rend >= 15:
                card_class="stock-card-rocket"; emoji="🚀"; rend_str=f"▲ {rend:.2f}%"; rend_color="#00ff9d"; barra_pct=min(100,int(rend*2)); barra_color="#00ff9d"
            elif rend >= 5:
                card_class="stock-card-up"; emoji="📈"; rend_str=f"▲ {rend:.2f}%"; rend_color="#22c55e"; barra_pct=min(100,int(rend*4)); barra_color="#22c55e"
            elif rend >= -3:
                card_class="stock-card-neutral"; emoji="↔️"; rend_str=f"{'▲' if rend>=0 else '▼'} {abs(rend):.2f}%"; rend_color="#f59e0b"; barra_pct=50; barra_color="#f59e0b"
            elif rend >= -10:
                card_class="stock-card-down"; emoji="📉"; rend_str=f"▼ {abs(rend):.2f}%"; rend_color="#ef4444"; barra_pct=max(0,int(50+rend*2)); barra_color="#ef4444"
            else:
                card_class="stock-card-crash"; emoji="🔴"; rend_str=f"▼ {abs(rend):.2f}%"; rend_color="#ff0044"; barra_pct=max(0,int(50+rend)); barra_color="#ff0044"

            # ── Si hay alerta de techo, sobreescribir card a modo alerta ──
            if techo:
                card_class = "stock-card-crash"
                emoji      = "🚨"

            # ── Badge de alerta de venta ──
            alerta_html = ""
            if techo:
                alerta_html = """
                <div style='margin-top:8px;background:#ff004422;border:1px solid #ff0044;
                            border-radius:6px;padding:5px 8px;text-align:center;
                            font-family:JetBrains Mono;font-size:11px;font-weight:700;
                            color:#ff0044;letter-spacing:1px;
                            animation:pulse-red 1.5s infinite'>
                    🚨 ALERTA — CONSIDERAR VENTA
                </div>"""

            st.markdown(f"""
            <div class='{card_class}'>
                <div style='display:flex;justify-content:space-between;align-items:flex-start'>
                    <div>
                        <span style='font-size:16px'>{emoji}</span>
                        <span style='font-weight:800;font-size:15px;margin-left:6px'>{row['Ticker']}</span>
                        <div style='font-size:10px;color:#556;font-family:JetBrains Mono;margin-top:2px;letter-spacing:1px'>{row['Mercado']}</div>
                    </div>
                    <div style='text-align:right'>
                        <div style='font-family:JetBrains Mono;font-size:15px;font-weight:700;color:{rend_color}'>{rend_str}</div>
                        <div style='font-size:10px;color:#556;font-family:JetBrains Mono'>
                            {float(row['Cantidad']):.4f} acc · ${float(row['Compra']):.4f}
                        </div>
                    </div>
                </div>
                <div style='margin-top:8px;background:#ffffff11;border-radius:4px;height:4px;overflow:hidden'>
                    <div style='width:{barra_pct}%;height:100%;background:{barra_color};border-radius:4px'></div>
                </div>
                {alerta_html}
            </div>
            """, unsafe_allow_html=True)

            if st.button("✕ Eliminar", key=f"del_{row['Ticker']}", use_container_width=True):
                st.session_state.portfolio = (
                    st.session_state.portfolio.reset_index(drop=True)
                    .drop(index=i).reset_index(drop=True)
                )
                guardar_datos(st.session_state.portfolio, U)
                st.rerun()

# ═══════════════════════════════════════════════
#  VISTAS PRINCIPALES
# ═══════════════════════════════════════════════

if st.session_state.vista == "dashboard":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>RENDIMIENTO DEL PORTAFOLIO</div></div>", unsafe_allow_html=True)
    port = st.session_state.portfolio.reset_index(drop=True)
    if port.empty:
        st.markdown("""<div style='background:#0e0e1e;border:1px solid #1c1c30;border-radius:16px;
                    padding:60px;text-align:center;margin-top:20px'>
            <div style='font-size:40px'>📈</div>
            <div style='font-size:18px;font-weight:700'>Portafolio vacío</div>
            <div style='color:#444466;font-size:14px;margin-top:8px'>Agrega acciones con el panel izquierdo</div>
        </div>""", unsafe_allow_html=True)
    else:
        MONEDA = st.session_state.moneda_base
        resumen=[]; total_act=0; total_cmp=0
        for i in range(len(port)):
            row=port.iloc[i]; stats=motor_avanzado(row["Ticker"])
            compra   = float(row["Compra"])
            cantidad = float(row["Cantidad"])
            costo_base = float(row["Costo"]) if "Costo" in row.index and float(row.get("Costo",0))>0 \
                         else compra * cantidad
            if stats:
                trend, actual, moneda_acc = stats
                # Conversión de divisa al precio actual
                fx = get_tipo_cambio(moneda_acc, MONEDA)
                actual_conv    = actual    * fx
                costo_base_conv= costo_base * get_tipo_cambio(
                    moneda_acc if moneda_acc else "USD", MONEDA)
                rend = ((actual_conv*cantidad - costo_base_conv) / costo_base_conv * 100) \
                       if costo_base_conv > 0 else 0
                val  = actual_conv * cantidad
                estado = "VENDER (Techo)" if actual > trend * 1.05 else "MANTENER"
                precio_str = f"{moneda_acc} {actual:,.2f} → {MONEDA} {actual_conv:,.2f}"
            else:
                moneda_acc = "USD"
                actual, rend, val, estado = compra, 0, costo_base, "SIN DATOS"
                costo_base_conv = costo_base
                precio_str = "—"
            total_act += val; total_cmp += costo_base_conv
            resumen.append({"idx":i,"Ticker":row["Ticker"],"Nombre":row["Nombre"],
                            "Mercado":row["Mercado"],"Moneda":moneda_acc,
                            "Rendimiento":round(rend,2),
                            "Valor Actual":round(val,2),"Costo Base":round(costo_base_conv,2),
                            "Acciones":round(cantidad,4),"Acción":estado,
                            "Precio":precio_str})
        df_res=pd.DataFrame(resumen)
        rend_total=((total_act-total_cmp)/total_cmp*100) if total_cmp>0 else 0
        delta=total_act-total_cmp
        color_h="#00ff9d" if rend_total>=0 else "#ff4466"
        signo="+" if rend_total>=0 else ""

        # Símbolo de moneda
        SIM = {"USD":"$","MXN":"$","EUR":"€"}.get(MONEDA,"$")

        st.markdown(f"""<div style='margin-bottom:20px'>
            <div class='hero-pct' style='color:{color_h}'>{signo}{rend_total:.2f}%</div>
            <div style='font-family:JetBrains Mono;font-size:14px;color:{color_h};margin-top:6px'>
                {'▲' if delta>=0 else '▼'} {SIM}{abs(delta):,.2f} {MONEDA}
                <span style='color:#444466;margin-left:8px'>total P&L</span>
            </div></div>""", unsafe_allow_html=True)
        m1,m2,m3=st.columns(3)
        m1.metric(f"💰 Valor Actual ({MONEDA})",f"{SIM}{total_act:,.2f}",f"{signo}{SIM}{abs(delta):,.2f}")
        m2.metric("📦 Posiciones",len(df_res))
        alertas_df = df_res[df_res["Acción"]=="VENDER (Techo)"]
        m3.metric("🚨 Alertas",len(alertas_df))

        # ── Banner de alertas grandes ──
        if not alertas_df.empty:
            tickers_alerta = " · ".join(alertas_df["Ticker"].tolist())
            st.markdown(f"""
            <div style='background:linear-gradient(135deg,#ff004433,#ff004418);
                        border:2px solid #ff0044;border-radius:14px;
                        padding:18px 22px;margin:12px 0;
                        animation:pulse-red 1.5s infinite;'>
                <div style='font-family:JetBrains Mono;font-size:11px;letter-spacing:3px;
                            color:#ff004499;text-transform:uppercase;margin-bottom:6px'>
                    ⚠️ Alerta Kalman — Techo detectado
                </div>
                <div style='font-size:22px;font-weight:800;color:#ff0044;letter-spacing:-0.5px'>
                    🚨 CONSIDERAR VENTA
                </div>
                <div style='font-family:JetBrains Mono;font-size:15px;color:#ff4466;
                            margin-top:8px;font-weight:600'>
                    {tickers_alerta}
                </div>
                <div style='font-size:12px;color:#ff004488;margin-top:6px'>
                    El precio superó +5% la tendencia filtrada por Kalman — señal de sobrecompra
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        colores=["#00ff9d" if x>0 else "#ff4466" if x<0 else "#444466" for x in df_res["Rendimiento"]]
        fig=go.Figure(go.Bar(x=df_res["Ticker"],y=df_res["Rendimiento"],marker=dict(color=colores),
            text=[f"{v:+.2f}%" for v in df_res["Rendimiento"]],textposition="outside",
            textfont=dict(family="JetBrains Mono",size=11,color="#e8e8f0")))
        fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                          font=dict(family="Syne"),margin=dict(l=16,r=16,t=40,b=16),height=280,
                          bargap=0.35,xaxis=dict(showgrid=False,color="#444466"),
                          yaxis=dict(gridcolor="#1c1c30",color="#444466",zeroline=True,zerolinecolor="#2a2a44"))
        st.plotly_chart(fig, use_container_width=True)

        # ── Cards visuales por estado ──
        st.markdown("<div class='label-tag' style='margin-top:8px'>Posiciones</div>", unsafe_allow_html=True)

        # Agrupar por estado
        grupos = {
            "🚨 Alerta Venta":  df_res[df_res["Acción"]=="VENDER (Techo)"],
            "💎 Mantener":      df_res[df_res["Acción"]=="MANTENER"],
            "⚠️ Sin Datos":     df_res[df_res["Acción"]=="SIN DATOS"],
        }
        colores_grupo = {
            "🚨 Alerta Venta": ("#ff0044","#ff004422","#ff004466"),
            "💎 Mantener":     ("#00ff9d","#00ff9d11","#00ff9d44"),
            "⚠️ Sin Datos":    ("#888","#88888811","#88888844"),
        }

        for grupo_label, grupo_df in grupos.items():
            if grupo_df.empty: continue
            color_txt, color_bg, color_bdr = colores_grupo[grupo_label]
            st.markdown(f"""
            <div style='font-size:11px;letter-spacing:2px;color:{color_txt};
                        font-family:JetBrains Mono;text-transform:uppercase;
                        margin:16px 0 8px;font-weight:700'>{grupo_label}</div>
            """, unsafe_allow_html=True)

            # Grid de 3 columnas
            cols = st.columns(3)
            for ci, (_, r) in enumerate(grupo_df.iterrows()):
                rend = r["Rendimiento"]
                rend_color = "#00ff9d" if rend>0 else "#ff4466" if rend<0 else "#888"
                signo_r = "▲" if rend>0 else "▼" if rend<0 else "—"
                with cols[ci % 3]:
                    st.markdown(f"""
                    <div style='background:{color_bg};border:1px solid {color_bdr};
                                border-radius:12px;padding:14px 12px;margin-bottom:10px;
                                text-align:center'>
                        <div style='font-weight:800;font-size:16px;letter-spacing:0.5px'>{r['Ticker']}</div>
                        <div style='font-size:10px;color:#556;font-family:JetBrains Mono;margin:2px 0 8px'>{r['Mercado']}</div>
                        <div style='font-family:JetBrains Mono;font-size:18px;font-weight:700;color:{rend_color}'>
                            {signo_r} {abs(rend):.1f}%
                        </div>
                        <div style='font-size:11px;color:#666;margin-top:4px;font-family:JetBrains Mono'>
                            ${r['Valor Actual']:,.0f}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button("✕", key=f"card_del_{r['Ticker']}", use_container_width=True):
                        st.session_state.portfolio=(
                            st.session_state.portfolio.reset_index(drop=True)
                            .drop(index=int(r["idx"])).reset_index(drop=True)
                        )
                        guardar_datos(st.session_state.portfolio, U); st.rerun()

elif st.session_state.vista == "seguimiento":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>RADAR DE MERCADO</div>"
                "<div style='font-size:28px;font-weight:800'>👁️ Seguimiento</div></div>",
                unsafe_allow_html=True)
    st.markdown("<div style='color:#666;font-size:14px;margin-bottom:20px'>"
                "Acciones en radar — sin posición abierta. Mismo motor cuantitativo que el portafolio.</div>",
                unsafe_allow_html=True)

    watch = st.session_state.watchlist.reset_index(drop=True)

    if watch.empty:
        st.markdown("""<div style='background:#0e0e1e;border:1px solid #1c1c30;border-radius:16px;
                    padding:60px;text-align:center;margin-top:20px'>
            <div style='font-size:40px'>👁️</div>
            <div style='font-size:18px;font-weight:700;margin-top:12px'>Sin acciones en seguimiento</div>
            <div style='color:#444466;font-size:14px;margin-top:8px'>
                Al agregar una acción en el sidebar, elige "Seguimiento"
            </div>
        </div>""", unsafe_allow_html=True)
    else:
        # ── Procesar datos de cada acción en watchlist ──
        watch_data = []
        for i in range(len(watch)):
            row   = watch.iloc[i]
            stats = motor_avanzado(row["Ticker"])
            serie = get_historico(row["Ticker"], "1mo")
            if stats:
                trend, actual = stats
                techo  = actual > trend * 1.05
                # RSI rápido
                if serie is not None and len(serie) > 14:
                    rsi_s  = calcular_rsi(serie.astype(float))
                    rsi_now= float(rsi_s.iloc[-1]) if not np.isnan(rsi_s.iloc[-1]) else 50
                else:
                    rsi_now = 50
                # Variación 1 mes
                if serie is not None and len(serie) > 1:
                    var_mes = (float(serie.iloc[-1]) / float(serie.iloc[0]) - 1) * 100
                else:
                    var_mes = 0.0
            else:
                actual = techo = None
                rsi_now = 50
                var_mes = 0.0

            watch_data.append({
                "idx": i, "Ticker": row["Ticker"], "Nombre": row["Nombre"],
                "Mercado": row["Mercado"], "Precio": actual,
                "Var1m": round(var_mes, 2), "RSI": round(rsi_now, 1),
                "Techo": techo,
            })

        # ── Grid de cards ──
        cols = st.columns(3)
        for ci, d in enumerate(watch_data):
            precio_str = f"${d['Precio']:,.2f}" if d["Precio"] else "—"
            var_color  = "#00ff9d" if d["Var1m"] >= 0 else "#ff4466"
            var_str    = f"{'▲' if d['Var1m']>=0 else '▼'} {abs(d['Var1m']):.1f}%"

            # Color del borde según señal
            if d["Techo"]:
                bdr_color = "#ff0044"; bg_color = "#ff004418"; estado_str = "🚨 TECHO"
            elif d["RSI"] < 35:
                bdr_color = "#00ff9d"; bg_color = "#00ff9d11"; estado_str = "🟢 COMPRA"
            elif d["RSI"] > 65:
                bdr_color = "#f59e0b"; bg_color = "#f59e0b11"; estado_str = "🟡 SOBRECOMPRA"
            else:
                bdr_color = "#2a2a44"; bg_color = "#0e0e1e";   estado_str = "⚪ NEUTRAL"

            # RSI bar fill
            rsi_pct = int(d["RSI"])
            rsi_color = "#00ff9d" if d["RSI"]<35 else "#ff4466" if d["RSI"]>65 else "#f59e0b"

            with cols[ci % 3]:
                st.markdown(f"""
                <div style='background:{bg_color};border:1px solid {bdr_color};
                            border-radius:14px;padding:16px 14px;margin-bottom:12px'>
                    <div style='display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px'>
                        <div>
                            <div style='font-weight:800;font-size:17px'>{d['Ticker']}</div>
                            <div style='font-size:10px;color:#556;font-family:JetBrains Mono;letter-spacing:1px'>{d['Mercado']}</div>
                        </div>
                        <div style='font-size:11px;font-weight:700;color:{bdr_color};
                                    font-family:JetBrains Mono;text-align:right'>{estado_str}</div>
                    </div>
                    <div style='font-family:JetBrains Mono;font-size:20px;font-weight:700;
                                color:#e8e8f0;margin-bottom:6px'>{precio_str}</div>
                    <div style='display:flex;justify-content:space-between;margin-bottom:10px'>
                        <span style='font-family:JetBrains Mono;font-size:12px;color:{var_color}'>{var_str} 1m</span>
                        <span style='font-family:JetBrains Mono;font-size:12px;color:{rsi_color}'>RSI {d['RSI']}</span>
                    </div>
                    <div style='background:#ffffff11;border-radius:4px;height:4px;overflow:hidden'>
                        <div style='width:{rsi_pct}%;height:100%;background:{rsi_color};border-radius:4px'></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("✕ Quitar", key=f"watch_del_{d['Ticker']}", use_container_width=True):
                    st.session_state.watchlist = (
                        st.session_state.watchlist.reset_index(drop=True)
                        .drop(index=d["idx"]).reset_index(drop=True)
                    )
                    guardar_watchlist(st.session_state.watchlist, U)
                    st.rerun()

        # ── Tabla resumen ──
        st.markdown("<div class='label-tag' style='margin-top:16px'>Resumen</div>", unsafe_allow_html=True)
        for d in watch_data:
            precio_str = f"${d['Precio']:,.2f}" if d["Precio"] else "—"
            var_color  = "#00ff9d" if d["Var1m"] >= 0 else "#ff4466"
            rsi_color  = "#00ff9d" if d["RSI"]<35 else "#ff4466" if d["RSI"]>65 else "#f59e0b"
            if d["Techo"]:
                señal_str = "🚨 TECHO — Considerar entrada corta"
                señal_col = "#ff0044"
            elif d["RSI"] < 35:
                señal_str = "🟢 RSI bajo — Posible oportunidad de compra"
                señal_col = "#00ff9d"
            elif d["RSI"] > 65:
                señal_str = "🟡 RSI alto — Esperar corrección"
                señal_col = "#f59e0b"
            else:
                señal_str = "⚪ Sin señal clara — Seguir monitoreando"
                señal_col = "#666"

            st.markdown(f"""
            <div style='background:#0a0a16;border:1px solid #1c1c30;border-radius:10px;
                        padding:12px 16px;margin-bottom:6px;
                        display:flex;align-items:center;justify-content:space-between'>
                <div>
                    <span style='font-weight:700;font-size:15px'>{d['Ticker']}</span>
                    <span style='font-size:11px;color:#556;font-family:JetBrains Mono;margin-left:10px'>{d['Nombre'][:25]}</span>
                </div>
                <div style='text-align:center'>
                    <span style='font-family:JetBrains Mono;font-size:14px;color:#e8e8f0'>{precio_str}</span>
                </div>
                <div style='text-align:right'>
                    <div style='font-size:12px;color:{señal_col};font-weight:600'>{señal_str}</div>
                    <div style='font-family:JetBrains Mono;font-size:11px;color:{var_color}'>{d['Var1m']:+.1f}% 1m &nbsp;|&nbsp; <span style='color:{rsi_color}'>RSI {d['RSI']}</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

elif st.session_state.vista == "comparacion":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>TU PORTAFOLIO VS MEJORES ETFs</div>"
                "<div style='font-size:28px;font-weight:800;letter-spacing:-0.5px'>Comparación de Rendimiento</div></div>",unsafe_allow_html=True)
    col_p,col_b=st.columns([2,3])
    periodo_label=col_p.selectbox("Periodo",list(PERIODOS.keys()),index=2)
    periodo=PERIODOS[periodo_label]
    bench_sel=col_b.multiselect("ETFs a comparar",list(BENCHMARKS.keys()),
                    default=["S&P 500 (SPY)","NASDAQ 100 (QQQ)","México BOLSA (EWW)","Oro (GLD)"])
    def serie_port_norm(port_df, period):
        series_list=[]; pesos=[]
        for i in range(len(port_df)):
            row=port_df.iloc[i]; s=get_historico(row["Ticker"],period)
            if s is not None and len(s)>1: series_list.append(s); pesos.append(float(row["Compra"])*float(row["Cantidad"]))
        if not series_list: return None
        idx_c=series_list[0].index
        for s in series_list[1:]: idx_c=idx_c.intersection(s.index)
        if len(idx_c)<2: return None
        total_p=sum(pesos)
        comb=sum((s.reindex(idx_c)/s.reindex(idx_c).iloc[0])*(p/total_p) for s,p in zip(series_list,pesos))
        return (comb/comb.iloc[0])*100
    with st.spinner("Descargando datos…"):
        port=st.session_state.portfolio.reset_index(drop=True)
        serie_port=serie_port_norm(port,periodo) if not port.empty else None
        series_bench={}
        for nb in bench_sel:
            s=get_historico(BENCHMARKS[nb]["ticker"],periodo)
            if s is not None and len(s)>1: series_bench[nb]=(s/s.iloc[0])*100
    fig=go.Figure(); port_rend=None
    if serie_port is not None:
        port_rend=float(serie_port.iloc[-1])-100
        fig.add_trace(go.Scatter(x=serie_port.index,y=serie_port.values,
            name=f"Tu portafolio ({port_rend:+.2f}%)",
            line=dict(color="#00ff9d",width=3),fill="tozeroy",fillcolor="rgba(0,255,157,0.05)",
            hovertemplate="%{y:.2f}<extra>Tu portafolio</extra>"))
    leyenda_cards=[]
    for nb,serie in series_bench.items():
        cfg=BENCHMARKS[nb]; rb=float(serie.iloc[-1])-100
        leyenda_cards.append((nb,cfg["color"],rb))
        fig.add_trace(go.Scatter(x=serie.index,y=serie.values,name=f"{nb} ({rb:+.2f}%)",
            line=dict(color=cfg["color"],width=1.8),opacity=0.85,
            hovertemplate=f"%{{y:.2f}}<extra>{nb}</extra>"))
    fig.add_hline(y=100,line=dict(color="#2a2a44",dash="dash",width=1))
    fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                      font=dict(family="Syne",color="#e8e8f0"),
                      legend=dict(bgcolor="#0a0a16",bordercolor="#1c1c30",borderwidth=1,font=dict(family="JetBrains Mono",size=11)),
                      margin=dict(l=16,r=16,t=56,b=16),height=420,hovermode="x unified",
                      xaxis=dict(gridcolor="#1c1c30",color="#444466",showgrid=False),
                      yaxis=dict(gridcolor="#1c1c30",color="#444466"))
    st.plotly_chart(fig, use_container_width=True)
    if port_rend is not None and leyenda_cards:
        cols=st.columns(min(len(leyenda_cards),4))
        for ci,(nb,color,rb) in enumerate(leyenda_cards):
            diff=port_rend-rb; gana=diff>0
            with cols[ci%4]:
                st.markdown(f"""<div style='background:#0e0e1e;border:1px solid #1c1c30;
                    border-left:3px solid {color};border-radius:12px;padding:16px;margin-bottom:12px'>
                    <div style='font-size:10px;letter-spacing:2px;color:#444466;font-family:JetBrains Mono'>{nb}</div>
                    <div style='font-family:JetBrains Mono;font-size:20px;color:{"#00ff9d" if rb>=0 else "#ff4466"}'>{rb:+.2f}%</div>
                    <div style='margin-top:10px;padding-top:8px;border-top:1px solid #1c1c30'>
                        <span style='color:{"#00ff9d" if gana else "#ff4466"};font-family:JetBrains Mono;font-size:12px'>
                            {"🏆 +" if gana else "📉 "}{abs(diff):.2f}%</span>
                        <div style='font-size:11px;color:#444466;margin-top:2px'>{"Superando al índice" if gana else "Por debajo del índice"}</div>
                    </div></div>""", unsafe_allow_html=True)
        st.markdown("<div class='label-tag' style='margin-top:8px'>RANKING</div>", unsafe_allow_html=True)
        ranking=[("🟢 Tu portafolio",port_rend)]+[(n,r) for n,_,r in leyenda_cards]
        ranking.sort(key=lambda x:x[1],reverse=True)
        for pos,(nb,rend) in enumerate(ranking,1):
            es_p="portafolio" in nb.lower(); cr="#00ff9d" if rend>=0 else "#ff4466"
            st.markdown(f"""<div style='display:flex;align-items:center;gap:16px;padding:10px 16px;
                border-radius:10px;margin-bottom:6px;background:{"#00ff9d0a" if es_p else "#0a0a16"};
                border:1px solid {"#00ff9d33" if es_p else "#1c1c30"}'>
                <div style='font-family:JetBrains Mono;color:#444466;font-size:13px;width:24px'>#{pos}</div>
                <div style='flex:1;font-weight:{"700" if es_p else "400"};font-size:14px'>{nb}</div>
                <div style='font-family:JetBrains Mono;font-size:14px;color:{cr};font-weight:600'>{rend:+.2f}%</div>
            </div>""", unsafe_allow_html=True)

elif st.session_state.vista == "tecnico":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>ANÁLISIS TÉCNICO CUANTITATIVO</div>"
                "<div style='font-size:28px;font-weight:800'>RSI · MACD · Bollinger Bands</div></div>",unsafe_allow_html=True)
    port=st.session_state.portfolio.reset_index(drop=True)
    tickers_disponibles=port["Ticker"].tolist() if not port.empty else []
    col1,col2=st.columns([2,2])
    ticker_manual=col1.text_input("O escribe cualquier ticker",placeholder="AAPL, TSLA, AMZN…")
    ticker_sel=col2.selectbox("Desde tu portafolio",[""]+tickers_disponibles)
    ticker=ticker_manual.upper().strip() or ticker_sel
    periodo_tec=st.select_slider("Periodo",options=["3mo","6mo","1y","2y"],value="1y")
    if ticker:
        with st.spinner(f"Descargando {ticker}…"): df=get_ohlcv(ticker,periodo_tec)
        if df is None or df.empty: st.error("No se pudo obtener datos.")
        else:
            close=df["Close"].astype(float); rsi=calcular_rsi(close)
            macd_l,sig_l,hist=calcular_macd(close); bb_up,bb_mid,bb_lo=calcular_bollinger(close)
            rsi_now=float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50
            hist_now=float(hist.iloc[-1]) if not np.isnan(hist.iloc[-1]) else 0
            score=senal_combinada(rsi_now,hist_now,float(close.iloc[-1]),float(bb_up.iloc[-1]),float(bb_lo.iloc[-1]))
            color_score="#00ff9d" if score>0 else "#ff4466" if score<0 else "#f59e0b"
            label_score=("🐂 ALCISTA — Señal de COMPRA" if score>=2 else "🐻 BAJISTA — Señal de VENTA" if score<=-2 else "↔️ NEUTRAL — Esperar confirmación")
            st.markdown(f"""<div style='background:#0e0e1e;border:1px solid {color_score}44;
                border-left:4px solid {color_score};border-radius:12px;padding:18px 22px;margin:16px 0'>
                <div style='font-family:JetBrains Mono;font-size:11px;color:#444466;letter-spacing:2px'>SEÑAL COMBINADA — {ticker}</div>
                <div style='font-size:22px;font-weight:800;color:{color_score};margin-top:6px'>{label_score}</div>
                <div style='font-family:JetBrains Mono;font-size:13px;color:#888;margin-top:8px'>
                    RSI: {rsi_now:.1f} &nbsp;|&nbsp; MACD Hist: {hist_now:.4f} &nbsp;|&nbsp; Score: {score:+d}/3
                </div></div>""", unsafe_allow_html=True)

            # ── Audio TTS del análisis técnico ──
            texto_audio = (
                f"Análisis técnico de {ticker}. "
                f"{label_score}. "
                f"RSI actual: {rsi_now:.0f}. "
                f"{'El RSI está sobrecomprado, considera salir.' if rsi_now > 70 else 'El RSI está sobrevendido, posible oportunidad de compra.' if rsi_now < 30 else 'El RSI está en zona neutral.'} "
                f"MACD histograma: {'positivo, momentum alcista.' if hist_now > 0 else 'negativo, momentum bajista.'} "
                f"Score combinado: {score} de 3. "
                f"{'Señal fuerte de compra.' if score >= 2 else 'Señal fuerte de venta.' if score <= -2 else 'Sin señal clara, esperar confirmación.'}"
            )
            st.components.v1.html(audio_tts_html(texto_audio), height=60)
            fig=make_subplots(rows=3,cols=1,shared_xaxes=True,row_heights=[0.55,0.25,0.20],
                              vertical_spacing=0.04,subplot_titles=[f"{ticker} — Precio & Bollinger","MACD","RSI"])
            fig.add_trace(go.Scatter(x=close.index,y=bb_up,name="BB Superior",line=dict(color="#3b82f6",width=1,dash="dot"),showlegend=False),row=1,col=1)
            fig.add_trace(go.Scatter(x=close.index,y=bb_lo,name="BB Inferior",line=dict(color="#3b82f6",width=1,dash="dot"),fill="tonexty",fillcolor="rgba(59,130,246,0.05)",showlegend=False),row=1,col=1)
            fig.add_trace(go.Scatter(x=close.index,y=bb_mid,name="SMA20",line=dict(color="#6b7280",width=1),showlegend=False),row=1,col=1)
            fig.add_trace(go.Scatter(x=close.index,y=close,name="Precio",line=dict(color="#00ff9d",width=2)),row=1,col=1)
            colors_hist=["#00ff9d" if v>=0 else "#ff4466" for v in hist]
            fig.add_trace(go.Bar(x=hist.index,y=hist,name="Histograma",marker_color=colors_hist,showlegend=False),row=2,col=1)
            fig.add_trace(go.Scatter(x=macd_l.index,y=macd_l,name="MACD",line=dict(color="#f59e0b",width=1.5)),row=2,col=1)
            fig.add_trace(go.Scatter(x=sig_l.index,y=sig_l,name="Señal",line=dict(color="#ec4899",width=1.5)),row=2,col=1)
            fig.add_trace(go.Scatter(x=rsi.index,y=rsi,name="RSI",line=dict(color="#8b5cf6",width=2),showlegend=False),row=3,col=1)
            fig.add_hline(y=70,line=dict(color="#ff4466",dash="dash",width=1),row=3,col=1)
            fig.add_hline(y=30,line=dict(color="#00ff9d",dash="dash",width=1),row=3,col=1)
            fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                              font=dict(family="Syne",color="#e8e8f0"),height=620,margin=dict(l=16,r=16,t=40,b=16),
                              hovermode="x unified",legend=dict(bgcolor="#0a0a16",font=dict(family="JetBrains Mono",size=11)))
            for row in [1,2,3]:
                fig.update_xaxes(gridcolor="#1c1c30",color="#444466",showgrid=False,row=row,col=1)
                fig.update_yaxes(gridcolor="#1c1c30",color="#444466",row=row,col=1)
            st.plotly_chart(fig, use_container_width=True)

elif st.session_state.vista == "hmm":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>HIDDEN MARKOV MODEL</div>"
                "<div style='font-size:28px;font-weight:800'>Detección de Régimen de Mercado</div></div>",unsafe_allow_html=True)
    st.markdown("<div style='color:#666;font-size:14px;margin-bottom:20px'>El HMM detecta automáticamente si el mercado "
                "está en fase <span style='color:#00ff9d'>alcista</span>, <span style='color:#ff4466'>bajista</span> o "
                "<span style='color:#f59e0b'>lateral</span> usando retornos logarítmicos.</div>",unsafe_allow_html=True)
    port=st.session_state.portfolio.reset_index(drop=True)
    col1,col2=st.columns([2,2])
    ticker_manual=col1.text_input("Ticker",placeholder="AAPL, GMEXICO.MX, PE&OLES.MX…")
    ticker_port=col2.selectbox("O desde portafolio",[""]+port["Ticker"].tolist())
    ticker_hmm=ticker_manual.upper().strip() or ticker_port
    periodo_hmm=st.select_slider("Periodo análisis",options=["6mo","1y","2y","5y"],value="2y")

    # ── Guía de tickers por mercado ──
    with st.expander("📖 ¿Cómo escribir tickers de México, Europa y otros mercados?"):
        st.markdown("""
        <div style='font-family:JetBrains Mono;font-size:12px;line-height:2'>
        <b style='color:#00ff9d'>🇺🇸 USA</b> — sin sufijo: <code>AAPL</code>, <code>TSLA</code>, <code>SPY</code><br>
        <b style='color:#f59e0b'>🇲🇽 México (BMV)</b> — sufijo <code>.MX</code>: <code>GMEXICO.MX</code>, <code>FEMSAUBD.MX</code>, <code>PE&OLES.MX</code>, <code>WALMEX.MX</code><br>
        <b style='color:#3b82f6'>🇬🇧 Londres</b> — sufijo <code>.L</code>: <code>HSBA.L</code>, <code>BP.L</code><br>
        <b style='color:#ec4899'>🇪🇺 París</b> — sufijo <code>.PA</code>: <code>MC.PA</code> (LVMH), <code>AIR.PA</code> (Airbus)<br>
        <b style='color:#8b5cf6'>🇩🇪 Frankfurt</b> — sufijo <code>.DE</code>: <code>SAP.DE</code>, <code>BMW.DE</code><br>
        <b style='color:#06b6d4'>🇪🇸 Madrid</b> — sufijo <code>.MC</code>: <code>SAN.MC</code> (Santander)<br>
        <b style='color:#10b981'>🇧🇷 Brasil</b> — sufijo <code>.SA</code>: <code>PETR4.SA</code> (Petrobras)<br>
        <b style='color:#eab308'>🇦🇷 Argentina</b> — sufijo <code>.BA</code>: <code>GGAL.BA</code><br>
        </div>
        <div style='margin-top:8px;font-size:11px;color:#666'>
        💡 Si no sabes el ticker exacto, búscalo primero en el panel izquierdo — el buscador lo encuentra automáticamente.
        </div>
        """, unsafe_allow_html=True)

    if ticker_hmm:
        with st.spinner("Corriendo HMM Baum-Welch…"):
            serie = get_historico(ticker_hmm, periodo_hmm)
            # Intentar con sufijo .MX si falla y no tiene sufijo
            ticker_usado = ticker_hmm
            if serie is None and "." not in ticker_hmm:
                serie = get_historico(ticker_hmm + ".MX", periodo_hmm)
                if serie is not None:
                    ticker_usado = ticker_hmm + ".MX"

        if serie is None:
            st.error(f"No se pudo obtener datos para **{ticker_hmm}**.")
            st.markdown(f"""
            <div style='background:#f59e0b11;border:1px solid #f59e0b44;border-radius:10px;
                        padding:14px 16px;margin-top:8px;font-size:13px'>
                <b style='color:#f59e0b'>💡 Sugerencias:</b><br>
                • Si es empresa <b>mexicana</b>, agrega <code>.MX</code> → <code>{ticker_hmm}.MX</code><br>
                • Si es empresa <b>europea</b>, agrega el sufijo de su bolsa (ver guía arriba)<br>
                • Usa el <b>buscador del panel izquierdo</b> para encontrar el ticker correcto
            </div>
            """, unsafe_allow_html=True)
        else:
            if ticker_usado != ticker_hmm:
                st.info(f"💡 Ticker ajustado automáticamente: **{ticker_hmm}** → **{ticker_usado}**")
            estados,fechas=hmm_regimen(serie)
            if estados is None: st.warning("Datos insuficientes para HMM.")
            else:
                estado_actual=estados[-1]; n_bull=(estados==2).sum(); n_lat=(estados==1).sum(); n_bear=(estados==0).sum(); total=len(estados)
                clase=clase_regimen(estado_actual)
                st.markdown(f"""<div class='{clase}' style='margin:16px 0'>
                    <div style='font-size:11px;letter-spacing:2px;font-family:JetBrains Mono;opacity:0.7'>RÉGIMEN ACTUAL — {ticker_usado}</div>
                    <div style='font-size:26px;margin-top:4px'>{nombre_regimen(estado_actual)}</div>
                </div>""", unsafe_allow_html=True)
                c1,c2,c3=st.columns(3)
                c1.metric("🐂 Alcista",f"{n_bull/total*100:.1f}%",f"{n_bull} días")
                c2.metric("↔️ Lateral",f"{n_lat/total*100:.1f}%",f"{n_lat} días")
                c3.metric("🐻 Bajista",f"{n_bear/total*100:.1f}%",f"{n_bear} días")
                colores_reg=[color_regimen(e) for e in estados]
                fig=make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[0.7,0.3],vertical_spacing=0.04,
                                  subplot_titles=[f"{ticker_hmm} — Precio con Régimen","Estado HMM"])
                fig.add_trace(go.Scatter(x=fechas,y=serie.reindex(fechas).values,name="Precio",line=dict(color="#e8e8f0",width=2)),row=1,col=1)

                # Sombreado por régimen usando vrect — evita el problema de
                # concatenar timestamps con [::-1] que rompe Plotly
                precio_vals = serie.reindex(fechas).values
                y_max = float(np.nanmax(precio_vals)) if len(precio_vals) else 1
                y_min = float(np.nanmin(precio_vals)) if len(precio_vals) else 0

                for e, color_fill, lbl in [(2,"rgba(0,255,157,0.15)","Alcista"),
                                           (1,"rgba(245,158,11,0.15)","Lateral"),
                                           (0,"rgba(255,68,102,0.15)","Bajista")]:
                    mask = estados == e
                    # Detectar bloques continuos de cada estado
                    in_block = False
                    x0 = None
                    for j, m in enumerate(mask):
                        fecha_j = fechas[j]
                        if m and not in_block:
                            x0 = fecha_j
                            in_block = True
                        elif not m and in_block:
                            fig.add_vrect(
                                x0=x0, x1=fechas[j-1],
                                fillcolor=color_fill, line_width=0,
                                row=1, col=1
                            )
                            in_block = False
                    # Cerrar bloque si termina en el último dato
                    if in_block and x0 is not None:
                        fig.add_vrect(
                            x0=x0, x1=fechas[-1],
                            fillcolor=color_fill, line_width=0,
                            row=1, col=1
                        )
                    # Agregar leyenda manual como scatter invisible
                    fig.add_trace(go.Scatter(
                        x=[None], y=[None],
                        mode="markers",
                        marker=dict(color=color_fill.replace("0.15","1"), size=10, symbol="square"),
                        name=lbl, showlegend=True
                    ), row=1, col=1)
                fig.add_trace(go.Scatter(x=fechas,y=estados,mode="markers",
                    marker=dict(color=colores_reg,size=4,symbol="square"),name="Estado",showlegend=False),row=2,col=1)
                fig.update_yaxes(tickvals=[0,1,2],ticktext=["Bajista","Lateral","Alcista"],row=2,col=1)
                fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                                  font=dict(family="Syne",color="#e8e8f0"),height=500,margin=dict(l=16,r=16,t=40,b=16),
                                  legend=dict(bgcolor="#0a0a16",font=dict(family="JetBrains Mono",size=11)))
                for row in [1,2]:
                    fig.update_xaxes(gridcolor="#1c1c30",color="#444466",showgrid=False,row=row,col=1)
                    fig.update_yaxes(gridcolor="#1c1c30",color="#444466",row=row,col=1)
                st.plotly_chart(fig, use_container_width=True)

elif st.session_state.vista == "backtest":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>MOTOR DE BACKTESTING</div>"
                "<div style='font-size:28px;font-weight:800'>Estrategia RSI + MACD vs Buy & Hold</div></div>",unsafe_allow_html=True)
    port=st.session_state.portfolio.reset_index(drop=True)
    col1,col2,col3=st.columns([2,2,1])
    ticker_manual=col1.text_input("Ticker",placeholder="AAPL, MSFT, SPY…")
    ticker_port=col2.selectbox("O desde portafolio",[""]+port["Ticker"].tolist())
    capital_ini=col3.number_input("Capital $",min_value=100.0,value=10000.0,step=1000.0)
    ticker_bt=ticker_manual.upper().strip() or ticker_port
    periodo_bt=st.select_slider("Periodo",options=["6mo","1y","2y","5y"],value="2y")
    if ticker_bt:
        with st.spinner("Corriendo backtest…"): df_bt=get_ohlcv(ticker_bt,periodo_bt)
        if df_bt is None: st.error("No se pudo obtener datos.")
        else:
            res=backtest_estrategia(df_bt,capital_ini)
            gana_strat=res["total_return"]>res["bnh_return"]
            c1,c2,c3,c4=st.columns(4)
            c1.metric("📈 Estrategia",f"{res['total_return']:+.2f}%")
            c2.metric("📊 Buy & Hold",f"{res['bnh_return']:+.2f}%")
            c3.metric("⚡ Sharpe Ratio",f"{res['sharpe']:.3f}")
            c4.metric("📉 Max Drawdown",f"{res['max_drawdown']:.2f}%")
            diff_bt=res["total_return"]-res["bnh_return"]; color_v="#00ff9d" if gana_strat else "#ff4466"
            veredicto=(f"✅ La estrategia SUPERA a Buy & Hold por {abs(diff_bt):.2f}%" if gana_strat else f"❌ Buy & Hold supera a la estrategia por {abs(diff_bt):.2f}%")
            st.markdown(f"""<div style='background:#0e0e1e;border:1px solid {color_v}44;border-left:4px solid {color_v};
                border-radius:12px;padding:16px 20px;margin:16px 0'>
                <div style='font-size:16px;font-weight:700;color:{color_v}'>{veredicto}</div>
                <div style='font-family:JetBrains Mono;font-size:12px;color:#666;margin-top:6px'>{res['n_trades']} operaciones ejecutadas</div>
            </div>""", unsafe_allow_html=True)
            fig=go.Figure()
            fig.add_trace(go.Scatter(x=res["dates"],y=res["portfolio_vals"],name=f"Estrategia RSI+MACD ({res['total_return']:+.2f}%)",line=dict(color="#00ff9d",width=2.5),fill="tozeroy",fillcolor="rgba(0,255,157,0.04)"))
            fig.add_trace(go.Scatter(x=res["dates"],y=res["bnh_vals"],name=f"Buy & Hold ({res['bnh_return']:+.2f}%)",line=dict(color="#f59e0b",width=2,dash="dot")))
            if not res["trades"].empty:
                compras=res["trades"][res["trades"]["Tipo"]=="COMPRA"]; ventas=res["trades"][res["trades"]["Tipo"]=="VENTA"]
                if not compras.empty: fig.add_trace(go.Scatter(x=compras["Fecha"],y=compras["Precio"],mode="markers",marker=dict(color="#00ff9d",size=8,symbol="triangle-up"),name="Compra"))
                if not ventas.empty: fig.add_trace(go.Scatter(x=ventas["Fecha"],y=ventas["Precio"],mode="markers",marker=dict(color="#ff4466",size=8,symbol="triangle-down"),name="Venta"))
            fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                              font=dict(family="Syne",color="#e8e8f0"),height=420,margin=dict(l=16,r=16,t=40,b=16),
                              hovermode="x unified",legend=dict(bgcolor="#0a0a16",font=dict(family="JetBrains Mono",size=11)),
                              xaxis=dict(gridcolor="#1c1c30",color="#444466",showgrid=False),
                              yaxis=dict(gridcolor="#1c1c30",color="#444466",title="Valor ($)"))
            st.plotly_chart(fig, use_container_width=True)
            if not res["trades"].empty:
                st.markdown("<div class='label-tag'>Log de operaciones</div>", unsafe_allow_html=True)
                trades_df = res["trades"].copy()
                try:
                    # pandas >= 2.1 usa .map(), versiones anteriores usan .applymap()
                    styled = trades_df.style.map(
                        lambda v: "color:#00ff9d" if v=="COMPRA" else "color:#ff4466" if v=="VENTA" else "",
                        subset=["Tipo"]
                    )
                except AttributeError:
                    styled = trades_df.style.applymap(
                        lambda v: "color:#00ff9d" if v=="COMPRA" else "color:#ff4466" if v=="VENTA" else "",
                        subset=["Tipo"]
                    )
                st.dataframe(styled, use_container_width=True, height=220)

elif st.session_state.vista == "pairs":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>PAIRS TRADING — ARBITRAJE ESTADÍSTICO</div>"
                "<div style='font-size:28px;font-weight:800'>Detectar Divergencias entre Activos Correlacionados</div></div>",unsafe_allow_html=True)
    port=st.session_state.portfolio.reset_index(drop=True); tickers_port=port["Ticker"].tolist()
    col1,col2,col3=st.columns(3)
    t1=col1.text_input("Ticker 1",value=tickers_port[0] if len(tickers_port)>0 else "AAPL")
    t2=col2.text_input("Ticker 2",value=tickers_port[1] if len(tickers_port)>1 else "MSFT")
    periodo_pairs=col3.selectbox("Periodo",["3mo","6mo","1y"],index=1)
    if len(tickers_port)>=2:
        with st.expander("🔍 Auto-detectar mejores pares del portafolio"):
            with st.spinner("Analizando correlaciones…"):
                resultados_pares=[]
                for ta,tb in combinations(tickers_port,2):
                    res_p=analizar_par(ta,tb,periodo_pairs)
                    if res_p: resultados_pares.append({"Par":f"{ta} / {tb}","Correlación":round(res_p["corr"],3),"Z-Score":round(res_p["z_now"],2),"Señal":res_p["senal"]})
                if resultados_pares:
                    df_pares=pd.DataFrame(resultados_pares).sort_values("Correlación",ascending=False)
                    st.dataframe(df_pares,use_container_width=True,height=200)
    if t1 and t2:
        with st.spinner(f"Analizando {t1.upper()} / {t2.upper()}…"): res_par=analizar_par(t1.upper(),t2.upper(),periodo_pairs)
        if res_par is None: st.error("No se pudo obtener datos para el par.")
        else:
            c1,c2,c3=st.columns(3)
            c1.metric("📊 Correlación",f"{res_par['corr']:.3f}")
            c2.metric("📐 Z-Score actual",f"{res_par['z_now']:.2f}")
            c3.metric("📍 Señal","⚡ ACTIVA" if abs(res_par["z_now"])>2 else "💤 NEUTRAL")
            senal_color="#ff4466" if abs(res_par["z_now"])>2 else "#444466"
            st.markdown(f"""<div style='background:#0e0e1e;border:1px solid {senal_color}44;border-left:4px solid {senal_color};
                border-radius:12px;padding:16px 20px;margin:12px 0'>
                <div style='font-size:15px;font-weight:700;color:{senal_color}'>{res_par["senal"]}</div>
                <div style='font-family:JetBrains Mono;font-size:12px;color:#666;margin-top:4px'>Z-Score > ±2.0 = señal estadística válida (~95%)</div>
            </div>""", unsafe_allow_html=True)
            fig=make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[0.6,0.4],vertical_spacing=0.06,
                              subplot_titles=[f"Precios normalizados: {t1.upper()} vs {t2.upper()}","Z-Score del ratio"])
            s1n=(res_par["s1"]/res_par["s1"].iloc[0])*100; s2n=(res_par["s2"]/res_par["s2"].iloc[0])*100
            fig.add_trace(go.Scatter(x=res_par["idx"],y=s1n,name=t1.upper(),line=dict(color="#00ff9d",width=2)),row=1,col=1)
            fig.add_trace(go.Scatter(x=res_par["idx"],y=s2n,name=t2.upper(),line=dict(color="#f59e0b",width=2)),row=1,col=1)
            z_colors=["#ff4466" if abs(v)>2 else "#f59e0b" if abs(v)>1 else "#444466" for v in res_par["z"]]
            fig.add_trace(go.Bar(x=res_par["idx"],y=res_par["z"],marker_color=z_colors,name="Z-Score",showlegend=False),row=2,col=1)
            fig.add_hline(y=2,line=dict(color="#ff4466",dash="dash",width=1),row=2,col=1)
            fig.add_hline(y=-2,line=dict(color="#ff4466",dash="dash",width=1),row=2,col=1)
            fig.add_hline(y=0,line=dict(color="#444466",width=1),row=2,col=1)
            fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                              font=dict(family="Syne",color="#e8e8f0"),height=500,margin=dict(l=16,r=16,t=40,b=16),
                              legend=dict(bgcolor="#0a0a16",font=dict(family="JetBrains Mono",size=11)))
            for row in [1,2]:
                fig.update_xaxes(gridcolor="#1c1c30",color="#444466",showgrid=False,row=row,col=1)
                fig.update_yaxes(gridcolor="#1c1c30",color="#444466",row=row,col=1)
            st.plotly_chart(fig, use_container_width=True)

elif st.session_state.vista == "kelly":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>KELLY CRITERION — POSITION SIZING</div>"
                "<div style='font-size:28px;font-weight:800'>Tamaño Óptimo de Posición</div></div>",unsafe_allow_html=True)
    capital_total=st.number_input("Capital total disponible ($)",min_value=100.0,value=10000.0,step=500.0)
    port=st.session_state.portfolio.reset_index(drop=True); tickers_analizar=port["Ticker"].tolist()
    ticker_extra=st.text_input("Agregar ticker para analizar (opcional)",placeholder="NVDA, TSLA…")
    if ticker_extra.strip(): tickers_analizar.append(ticker_extra.upper().strip())
    if not tickers_analizar: st.info("Agrega acciones a tu portafolio o escribe un ticker arriba.")
    else:
        with st.spinner("Calculando Kelly…"):
            resultados_kelly=[]
            for tk in tickers_analizar:
                serie=get_historico(tk,"1y")
                if serie is not None and len(serie)>30:
                    k=kelly_criterion(serie); r=serie.pct_change().dropna()
                    wins=r[r>0]; losses=r[r<0]
                    resultados_kelly.append({"Ticker":tk,"Kelly %":round(k*100,2),"Kelly/2 %":round(k*50,2),
                        "$ Sugerido":round(k*capital_total,2),"$ Cons.":round(k*0.5*capital_total,2),
                        "P(ganancia)":round(len(wins)/len(r)*100,1),
                        "Win/Loss":round(wins.mean()/abs(losses.mean()),2) if losses.mean()!=0 else 0})
                else: resultados_kelly.append({"Ticker":tk,"Kelly %":0,"Kelly/2 %":0,"$ Sugerido":0,"$ Cons.":0,"P(ganancia)":0,"Win/Loss":0})
        df_kelly=pd.DataFrame(resultados_kelly).sort_values("Kelly %",ascending=False)
        fig=go.Figure()
        fig.add_trace(go.Bar(x=df_kelly["Ticker"],y=df_kelly["Kelly %"],name="Kelly completo",marker_color="#00ff9d",opacity=0.7,text=[f"{v:.1f}%" for v in df_kelly["Kelly %"]],textposition="outside",textfont=dict(family="JetBrains Mono",size=11)))
        fig.add_trace(go.Bar(x=df_kelly["Ticker"],y=df_kelly["Kelly/2 %"],name="Kelly/2 (conservador)",marker_color="#3b82f6",opacity=0.9,text=[f"{v:.1f}%" for v in df_kelly["Kelly/2 %"]],textposition="inside",textfont=dict(family="JetBrains Mono",size=10)))
        fig.update_layout(template="plotly_dark",paper_bgcolor="#0e0e1e",plot_bgcolor="#0e0e1e",
                          font=dict(family="Syne",color="#e8e8f0"),height=320,barmode="group",bargap=0.2,
                          margin=dict(l=16,r=16,t=40,b=16),legend=dict(bgcolor="#0a0a16",font=dict(family="JetBrains Mono",size=11)),
                          xaxis=dict(showgrid=False,color="#444466"),yaxis=dict(gridcolor="#1c1c30",color="#444466",title="% del capital"))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("<div class='label-tag'>Desglose por posición</div>",unsafe_allow_html=True)
        for _,r in df_kelly.iterrows():
            k_pct=r["Kelly %"]; color_k="#00ff9d" if k_pct>15 else "#f59e0b" if k_pct>5 else "#666"
            st.markdown(f"""<div style='background:#0e0e1e;border:1px solid #1c1c30;border-left:3px solid {color_k};
                border-radius:12px;padding:14px 18px;margin-bottom:8px'>
                <div style='display:flex;justify-content:space-between;align-items:center'>
                    <div><span style='font-weight:800;font-size:15px'>{r['Ticker']}</span>
                        <span style='font-family:JetBrains Mono;font-size:12px;color:#666;margin-left:12px'>
                            P(win): {r['P(ganancia)']}% &nbsp;|&nbsp; W/L: {r['Win/Loss']:.2f}</span></div>
                    <div style='text-align:right'>
                        <span style='font-family:JetBrains Mono;font-size:18px;color:{color_k};font-weight:600'>{k_pct:.1f}%</span>
                        <div style='font-size:11px;color:#666;font-family:JetBrains Mono'>${r['$ Sugerido']:,.0f} full · ${r['$ Cons.']:,.0f} cons.</div>
                    </div>
                </div></div>""", unsafe_allow_html=True)
        st.markdown("""<div style='background:#f59e0b0e;border:1px solid #f59e0b33;border-radius:10px;padding:14px 18px;margin-top:8px;font-size:13px;color:#f59e0b'>
            ⚠️ <strong>Kelly/2 es más robusto en la práctica.</strong> El Kelly completo asume distribuciones estables.
            Renaissance usa variantes fraccionarias ajustadas por correlación entre posiciones.</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────
#  ANÁLISIS FUNDAMENTAL
# ─────────────────────────────────────────
elif st.session_state.vista == "fundamental":
    st.markdown("<div style='padding:28px 0 4px'><div class='label-tag'>ANÁLISIS FUNDAMENTAL</div>"
                "<div style='font-size:28px;font-weight:800'>📋 Radiografía de la Empresa</div></div>",
                unsafe_allow_html=True)

    port = st.session_state.portfolio.reset_index(drop=True)
    col1, col2 = st.columns([2, 2])
    ticker_manual = col1.text_input("Ticker", placeholder="AAPL, GMEXICO.MX, TSLA…", key="fund_ticker")
    ticker_port   = col2.selectbox("O desde portafolio", [""] + port["Ticker"].tolist(), key="fund_port")
    ticker_f = ticker_manual.upper().strip() or ticker_port

    if not ticker_f:
        st.markdown("""<div style='background:#0e0e1e;border:1px solid #1c1c30;border-radius:14px;
                    padding:48px;text-align:center'>
            <div style='font-size:32px'>📋</div>
            <div style='font-size:16px;font-weight:700;margin-top:12px'>Escribe un ticker para analizar</div>
            <div style='color:#444466;font-size:13px;margin-top:6px'>Funciona con USA, México (.MX), Europa y más</div>
        </div>""", unsafe_allow_html=True)
    else:
        with st.spinner(f"Obteniendo fundamentales de {ticker_f}…"):
            fd = get_fundamentales(ticker_f)
            if fd is None and "." not in ticker_f:
                fd = get_fundamentales(ticker_f + ".MX")
                if fd: ticker_f = ticker_f + ".MX"

        if fd is None:
            st.error(f"No se encontraron datos para {ticker_f}.")
        else:
            # ── Header empresa ──
            precio_color = "#00ff9d" if fd["precio"] > 0 else "#888"
            st.markdown(f"""
            <div style='background:#0e0e1e;border:1px solid #1c1c30;border-radius:16px;
                        padding:24px;margin:16px 0'>
                <div style='font-size:11px;color:#444466;font-family:JetBrains Mono;
                            letter-spacing:2px;margin-bottom:4px'>
                    {ticker_f} · {fd["bolsa"]} · {fd["moneda"]}
                </div>
                <div style='font-size:22px;font-weight:800;margin-bottom:4px'>{fd["nombre"]}</div>
                <div style='font-size:13px;color:#888;margin-bottom:12px'>
                    {fd["sector"]} › {fd["industria"]} · {fd["pais"]}
                </div>
                <div style='display:flex;gap:32px;flex-wrap:wrap'>
                    <div>
                        <div style='font-size:10px;color:#444466;font-family:JetBrains Mono'>PRECIO ACTUAL</div>
                        <div style='font-family:JetBrains Mono;font-size:26px;font-weight:700;
                                    color:{precio_color}'>{fd["moneda"]} {fd["precio"]:,.2f}</div>
                    </div>
                    <div>
                        <div style='font-size:10px;color:#444466;font-family:JetBrains Mono'>MKT CAP</div>
                        <div style='font-family:JetBrains Mono;font-size:20px;font-weight:600;color:#e8e8f0'>{fd["mkt_cap"]}</div>
                    </div>
                    <div>
                        <div style='font-size:10px;color:#444466;font-family:JetBrains Mono'>52W HIGH / LOW</div>
                        <div style='font-family:JetBrains Mono;font-size:14px;color:#e8e8f0'>
                            <span style='color:#00ff9d'>{fd["52w_high"] or "—"}</span>
                            <span style='color:#444466'> / </span>
                            <span style='color:#ff4466'>{fd["52w_low"] or "—"}</span>
                        </div>
                    </div>
                    <div>
                        <div style='font-size:10px;color:#444466;font-family:JetBrains Mono'>BETA</div>
                        <div style='font-family:JetBrains Mono;font-size:18px;
                                    color:{"#f59e0b" if fd["beta"] and abs(fd["beta"])>1.5 else "#e8e8f0"}'>{fd["beta"] or "—"}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            def metrica_card(label, valor, sufijo="", color_fn=None, ayuda=""):
                if valor is None: val_str, color = "—", "#666"
                else:
                    if sufijo == "%": val_str = f"{valor*100:.1f}%"
                    elif sufijo == "x": val_str = f"{valor:.2f}x"
                    else: val_str = f"{valor}"
                    color = color_fn(valor) if color_fn else "#e8e8f0"
                return f"""<div style='background:#0a0a16;border:1px solid #1c1c30;border-radius:10px;
                                padding:12px 14px;'>
                    <div style='font-size:9px;letter-spacing:2px;color:#444466;
                                font-family:JetBrains Mono;text-transform:uppercase;margin-bottom:4px'>{label}</div>
                    <div style='font-family:JetBrains Mono;font-size:18px;font-weight:700;color:{color}'>{val_str}</div>
                    {"<div style='font-size:10px;color:#444;margin-top:2px'>"+ayuda+"</div>" if ayuda else ""}
                </div>"""

            # ── VALUACIÓN ──
            st.markdown("<div class='label-tag' style='margin-top:8px'>VALUACIÓN</div>", unsafe_allow_html=True)
            c1,c2,c3,c4,c5,c6 = st.columns(6)
            for col, lbl, val, sfx, cfn, tip in [
                (c1,"P/E Trailing",fd["pe_ratio"],"x",
                 lambda v: "#00ff9d" if v<15 else "#f59e0b" if v<25 else "#ff4466","<15 barato"),
                (c2,"P/E Forward",fd["pe_forward"],"x",
                 lambda v: "#00ff9d" if v<15 else "#f59e0b" if v<25 else "#ff4466","expectativa"),
                (c3,"P/B Ratio",fd["pb_ratio"],"x",
                 lambda v: "#00ff9d" if v<1.5 else "#f59e0b" if v<3 else "#ff4466","<1 infravalorado"),
                (c4,"P/S Ratio",fd["ps_ratio"],"x",
                 lambda v: "#00ff9d" if v<2 else "#f59e0b" if v<5 else "#ff4466","ventas"),
                (c5,"PEG",fd["peg"],"x",
                 lambda v: "#00ff9d" if v<1 else "#f59e0b" if v<2 else "#ff4466","<1 buen precio"),
                (c6,"EV/EBITDA",fd["ev_ebitda"],"x",
                 lambda v: "#00ff9d" if v<10 else "#f59e0b" if v<20 else "#ff4466","<10 atractivo"),
            ]:
                col.markdown(metrica_card(lbl, val, sfx, cfn, tip), unsafe_allow_html=True)

            # ── RENTABILIDAD ──
            st.markdown("<div class='label-tag' style='margin-top:16px'>RENTABILIDAD</div>", unsafe_allow_html=True)
            c1,c2,c3,c4 = st.columns(4)
            for col, lbl, val, tip in [
                (c1,"ROE",fd["roe"],"retorno sobre equity"),
                (c2,"ROA",fd["roa"],"retorno sobre activos"),
                (c3,"Margen Bruto",fd["margen_bruto"],"gross margin"),
                (c4,"Margen Neto",fd["margen_neto"],"net margin"),
            ]:
                color_fn = lambda v: "#00ff9d" if v>0.15 else "#f59e0b" if v>0.05 else "#ff4466"
                col.markdown(metrica_card(lbl, val, "%", color_fn, tip), unsafe_allow_html=True)

            # ── POR ACCIÓN & DIVIDENDOS ──
            st.markdown("<div class='label-tag' style='margin-top:16px'>POR ACCIÓN & DIVIDENDOS</div>", unsafe_allow_html=True)
            c1,c2,c3,c4,c5 = st.columns(5)
            c1.markdown(metrica_card("EPS TTM", fd["eps_ttm"], "",
                lambda v: "#00ff9d" if v>0 else "#ff4466"), unsafe_allow_html=True)
            c2.markdown(metrica_card("EPS Forward", fd["eps_fwd"], "",
                lambda v: "#00ff9d" if v>0 else "#ff4466"), unsafe_allow_html=True)
            c3.markdown(metrica_card("Book Value", fd["bvps"], ""), unsafe_allow_html=True)
            c4.markdown(metrica_card("Div. Yield", fd["div_yield"], "%",
                lambda v: "#00ff9d" if v>0.03 else "#f59e0b" if v>0 else "#666",
                f"${fd['div_rate'] or 0:.2f}/acc"), unsafe_allow_html=True)
            c5.markdown(metrica_card("Payout Ratio", fd["payout"], "%",
                lambda v: "#00ff9d" if v<0.5 else "#f59e0b" if v<0.8 else "#ff4466"), unsafe_allow_html=True)

            # ── SALUD FINANCIERA ──
            st.markdown("<div class='label-tag' style='margin-top:16px'>SALUD FINANCIERA</div>", unsafe_allow_html=True)
            c1,c2,c3,c4,c5 = st.columns(5)
            c1.markdown(metrica_card("Deuda/Equity", fd["debt_equity"], "x",
                lambda v: "#00ff9d" if v<50 else "#f59e0b" if v<150 else "#ff4466"), unsafe_allow_html=True)
            c2.markdown(metrica_card("Current Ratio", fd["current_ratio"], "x",
                lambda v: "#00ff9d" if v>2 else "#f59e0b" if v>1 else "#ff4466",
                ">2 saludable"), unsafe_allow_html=True)
            c3.markdown(metrica_card("Quick Ratio", fd["quick_ratio"], "x",
                lambda v: "#00ff9d" if v>1 else "#ff4466"), unsafe_allow_html=True)
            c4.markdown(metrica_card("Revenue", None, ""), unsafe_allow_html=True) if True else None
            c4.markdown(f"""<div style='background:#0a0a16;border:1px solid #1c1c30;border-radius:10px;padding:12px 14px'>
                <div style='font-size:9px;letter-spacing:2px;color:#444466;font-family:JetBrains Mono;text-transform:uppercase;margin-bottom:4px'>REVENUE</div>
                <div style='font-family:JetBrains Mono;font-size:16px;font-weight:700;color:#e8e8f0'>{fd["revenue"]}</div>
            </div>""", unsafe_allow_html=True)
            c5.markdown(f"""<div style='background:#0a0a16;border:1px solid #1c1c30;border-radius:10px;padding:12px 14px'>
                <div style='font-size:9px;letter-spacing:2px;color:#444466;font-family:JetBrains Mono;text-transform:uppercase;margin-bottom:4px'>EBITDA</div>
                <div style='font-family:JetBrains Mono;font-size:16px;font-weight:700;color:#e8e8f0'>{fd["ebitda"]}</div>
            </div>""", unsafe_allow_html=True)

            # ── CRECIMIENTO ──
            st.markdown("<div class='label-tag' style='margin-top:16px'>CRECIMIENTO</div>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            c1.markdown(metrica_card("Crec. Revenue", fd["rev_growth"], "%",
                lambda v: "#00ff9d" if v>0.15 else "#f59e0b" if v>0 else "#ff4466"), unsafe_allow_html=True)
            c2.markdown(metrica_card("Crec. Ganancias", fd["earn_growth"], "%",
                lambda v: "#00ff9d" if v>0.15 else "#f59e0b" if v>0 else "#ff4466"), unsafe_allow_html=True)
            c3.markdown(f"""<div style='background:#0a0a16;border:1px solid #1c1c30;border-radius:10px;padding:12px 14px'>
                <div style='font-size:9px;letter-spacing:2px;color:#444466;font-family:JetBrains Mono;text-transform:uppercase;margin-bottom:4px'>EMPLEADOS</div>
                <div style='font-family:JetBrains Mono;font-size:18px;font-weight:700;color:#e8e8f0'>
                    {f"{fd['empleados']:,}" if fd["empleados"] else "—"}
                </div>
            </div>""", unsafe_allow_html=True)

            # ── DESCRIPCIÓN ──
            if fd["descripcion"]:
                st.markdown("<div class='label-tag' style='margin-top:16px'>SOBRE LA EMPRESA</div>", unsafe_allow_html=True)
                st.markdown(f"""<div style='background:#0a0a16;border:1px solid #1c1c30;border-radius:12px;
                            padding:18px;font-size:13px;color:#aaa;line-height:1.7'>
                    {fd["descripcion"][:600]}{"…" if len(fd["descripcion"])>600 else ""}
                </div>""", unsafe_allow_html=True)

            # ── SEMÁFORO GENERAL ──
            scores = []
            if fd["pe_ratio"]: scores.append(2 if fd["pe_ratio"]<15 else 1 if fd["pe_ratio"]<25 else 0)
            if fd["roe"]: scores.append(2 if fd["roe"]>0.15 else 1 if fd["roe"]>0.05 else 0)
            if fd["margen_neto"]: scores.append(2 if fd["margen_neto"]>0.15 else 1 if fd["margen_neto"]>0.05 else 0)
            if fd["debt_equity"]: scores.append(2 if fd["debt_equity"]<50 else 1 if fd["debt_equity"]<150 else 0)
            if fd["current_ratio"]: scores.append(2 if fd["current_ratio"]>2 else 1 if fd["current_ratio"]>1 else 0)
            if fd["rev_growth"]: scores.append(2 if fd["rev_growth"]>0.15 else 1 if fd["rev_growth"]>0 else 0)

            if scores:
                prom = sum(scores)/len(scores)
                if prom >= 1.5:
                    semaforo_color, semaforo_txt = "#00ff9d", "🟢 FUNDAMENTALES SÓLIDOS"
                elif prom >= 0.8:
                    semaforo_color, semaforo_txt = "#f59e0b", "🟡 FUNDAMENTALES MIXTOS"
                else:
                    semaforo_color, semaforo_txt = "#ff4466", "🔴 FUNDAMENTALES DÉBILES"

                st.markdown(f"""
                <div style='background:{semaforo_color}11;border:2px solid {semaforo_color}44;
                            border-radius:12px;padding:16px 20px;margin-top:16px;
                            display:flex;align-items:center;justify-content:space-between'>
                    <div style='font-size:18px;font-weight:800;color:{semaforo_color}'>{semaforo_txt}</div>
                    <div style='font-family:JetBrains Mono;font-size:13px;color:#666'>
                        Score: {prom:.1f}/2.0 ({len(scores)} métricas)
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # ── Audio TTS del análisis fundamental ──
                pe_txt = f"P E de {fd['pe_ratio']:.1f}, " if fd["pe_ratio"] else ""
                roe_txt = f"ROE de {fd['roe']*100:.1f} por ciento, " if fd["roe"] else ""
                div_txt = f"dividendo de {fd['div_yield']*100:.1f} por ciento, " if fd["div_yield"] else ""
                crec_txt = f"crecimiento de ingresos de {fd['rev_growth']*100:.1f} por ciento, " if fd["rev_growth"] else ""
                beta_txt = f"beta de {fd['beta']:.2f}, lo que indica {'alta volatilidad' if fd['beta'] and fd['beta']>1.5 else 'volatilidad moderada' if fd['beta'] and fd['beta']>1 else 'baja volatilidad'}, " if fd["beta"] else ""
                texto_fund = (
                    f"Análisis fundamental de {fd['nombre']}. "
                    f"Sector: {fd['sector']}. "
                    f"Capitalización de mercado: {fd['mkt_cap']}. "
                    f"Precio actual: {fd['moneda']} {fd['precio']:.2f}. "
                    f"{pe_txt}{roe_txt}{div_txt}{crec_txt}{beta_txt}"
                    f"Evaluación general: {semaforo_txt.split(' ', 1)[1]}. "
                    f"Score fundamental: {prom:.1f} sobre 2 puntos."
                )
                st.components.v1.html(audio_tts_html(texto_fund), height=60)

# ═══════════════════════════════════════════════════════════
#  🧪 LAB QUANT — Motor cuantitativo avanzado
# ═══════════════════════════════════════════════════════════
elif st.session_state.vista == "lab":
    import time as _t

    st.markdown("""
    <div style='padding:28px 0 8px'>
        <div class='label-tag'>LABORATORIO CUANTITATIVO</div>
        <div style='font-size:28px;font-weight:800;letter-spacing:-0.5px'>🧪 Lab Quant</div>
        <div style='color:#666;font-size:13px;margin-top:6px'>
            Walk-Forward · HMM Ensemble · Particle Filter · Kelly con Correlaciones
        </div>
    </div>
    """, unsafe_allow_html=True)

    port = st.session_state.portfolio.reset_index(drop=True)
    tickers_port = port["Ticker"].tolist() if not port.empty else []

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Walk-Forward",
        "🧬 HMM Ensemble",
        "🌊 Particle Filter",
        "⚖️ Kelly Correlaciones"
    ])

    # ─────────────────────────────────────────
    #  TAB 1 — WALK-FORWARD OPTIMIZATION
    # ─────────────────────────────────────────
    with tab1:
        st.markdown("""
        <div style='color:#888;font-size:13px;margin-bottom:16px'>
        Divide el historial en ventanas: entrena la estrategia en cada ventana
        y valida en la siguiente. Mide si la estrategia es consistente en el tiempo
        o solo funcionó por suerte en un período específico.
        </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        wf_ticker  = col1.text_input("Ticker", value=tickers_port[0] if tickers_port else "SPY", key="wf_t")
        wf_ventana = col2.selectbox("Ventana entrenamiento", [60,90,120,180], index=1, key="wf_v")
        wf_test    = col3.selectbox("Ventana validación (días)", [20,30,45,60], index=1, key="wf_te")
        wf_capital = st.number_input("Capital inicial $", value=10000.0, step=1000.0, key="wf_c")

        if st.button("▶ Ejecutar Walk-Forward", use_container_width=True, key="wf_run"):
            with st.spinner("Ejecutando walk-forward optimization…"):

                df_wf = get_ohlcv(wf_ticker, "5y")
                if df_wf is None or len(df_wf) < wf_ventana + wf_test + 30:
                    st.error("Datos insuficientes. Intenta con período más corto o ticker diferente.")
                else:
                    close_wf = df_wf["Close"].astype(float)

                    def run_estrategia_ventana(prices_train, prices_test, capital):
                        """RSI+MACD calibrado en train, ejecutado en test"""
                        # Calcular señales sobre train para definir umbrales óptimos
                        rsi_tr   = calcular_rsi(prices_train)
                        macd_tr, _, hist_tr = calcular_macd(prices_train)

                        # Umbral RSI adaptativo: percentil 25 y 75 del train
                        rsi_vals = rsi_tr.dropna().values
                        umbral_bajo = float(np.percentile(rsi_vals, 25)) if len(rsi_vals) else 35
                        umbral_alto = float(np.percentile(rsi_vals, 75)) if len(rsi_vals) else 65

                        # Ejecutar en test
                        rsi_te   = calcular_rsi(pd.concat([prices_train.iloc[-30:], prices_test]))
                        _, _, hist_te = calcular_macd(pd.concat([prices_train.iloc[-30:], prices_test]))
                        rsi_te   = rsi_te.iloc[-len(prices_test):]
                        hist_te  = hist_te.iloc[-len(prices_test):]

                        pos = 0; cap = capital; acc = 0
                        vals = []; trades_n = 0; wins = 0

                        for j in range(len(prices_test)):
                            p  = float(prices_test.iloc[j])
                            r  = float(rsi_te.iloc[j])  if not np.isnan(rsi_te.iloc[j])  else 50
                            mh = float(hist_te.iloc[j]) if not np.isnan(hist_te.iloc[j]) else 0
                            precio_entrada = None

                            if pos == 0 and r < umbral_bajo and mh > 0 and cap > 0:
                                acc = cap / p; cap = 0; pos = 1
                                precio_entrada = p; trades_n += 1
                            elif pos == 1 and (r > umbral_alto or mh < -0.005):
                                ganancia = (p - precio_entrada) if precio_entrada else 0
                                if ganancia > 0: wins += 1
                                cap = acc * p; acc = 0; pos = 0

                            vals.append(cap + acc * p)

                        if pos == 1: cap = acc * float(prices_test.iloc[-1])
                        final = cap
                        ret   = (final / capital - 1) * 100
                        bnh   = (float(prices_test.iloc[-1]) / float(prices_test.iloc[0]) - 1) * 100

                        s = pd.Series(vals)
                        dr = s.pct_change().dropna()
                        sharpe = float(dr.mean() / dr.std() * np.sqrt(252)) if dr.std() > 0 else 0
                        maxdd  = float(((s / s.cummax()) - 1).min() * 100)
                        calmar = abs(ret / maxdd) if maxdd != 0 else 0
                        wr     = (wins / trades_n * 100) if trades_n > 0 else 0

                        return {
                            "retorno":  round(ret, 2),
                            "bnh":      round(bnh, 2),
                            "sharpe":   round(sharpe, 3),
                            "calmar":   round(calmar, 3),
                            "max_dd":   round(maxdd, 2),
                            "win_rate": round(wr, 1),
                            "n_trades": trades_n,
                            "vals":     vals,
                        }

                    # Construir ventanas
                    resultados_wf = []
                    n    = len(close_wf)
                    paso = wf_test
                    start = wf_ventana

                    while start + wf_test <= n:
                        train = close_wf.iloc[start - wf_ventana : start]
                        test  = close_wf.iloc[start : start + wf_test]
                        res   = run_estrategia_ventana(train, test, wf_capital)
                        res["fecha_inicio"] = str(test.index[0].date())
                        res["fecha_fin"]    = str(test.index[-1].date())
                        resultados_wf.append(res)
                        start += paso

                    df_wf_res = pd.DataFrame(resultados_wf)

                    # ── Métricas globales ──
                    wins_total  = (df_wf_res["retorno"] > df_wf_res["bnh"]).sum()
                    total_v     = len(df_wf_res)
                    pct_supera  = wins_total / total_v * 100 if total_v else 0
                    sharpe_med  = df_wf_res["sharpe"].mean()
                    calmar_med  = df_wf_res["calmar"].mean()
                    wr_med      = df_wf_res["win_rate"].mean()
                    ret_med     = df_wf_res["retorno"].mean()
                    dd_med      = df_wf_res["max_dd"].mean()

                    color_v = "#00ff9d" if pct_supera >= 60 else "#f59e0b" if pct_supera >= 45 else "#ff4466"
                    veredicto = ("✅ ESTRATEGIA ROBUSTA" if pct_supera >= 60
                                 else "⚠️ RESULTADOS MIXTOS" if pct_supera >= 45
                                 else "❌ ESTRATEGIA DÉBIL")

                    st.markdown(f"""
                    <div style='background:{color_v}11;border:2px solid {color_v}44;
                                border-radius:14px;padding:20px 24px;margin:16px 0'>
                        <div style='font-size:22px;font-weight:800;color:{color_v};margin-bottom:12px'>
                            {veredicto}
                        </div>
                        <div style='display:flex;gap:32px;flex-wrap:wrap;font-family:JetBrains Mono'>
                            <div>
                                <div style='font-size:10px;color:#444466;letter-spacing:2px'>SUPERA B&H</div>
                                <div style='font-size:20px;color:{color_v};font-weight:700'>
                                    {wins_total}/{total_v} ventanas ({pct_supera:.0f}%)
                                </div>
                            </div>
                            <div>
                                <div style='font-size:10px;color:#444466;letter-spacing:2px'>SHARPE MEDIO</div>
                                <div style='font-size:20px;color:{"#00ff9d" if sharpe_med>1 else "#f59e0b" if sharpe_med>0 else "#ff4466"};font-weight:700'>
                                    {sharpe_med:.3f}
                                </div>
                            </div>
                            <div>
                                <div style='font-size:10px;color:#444466;letter-spacing:2px'>CALMAR RATIO</div>
                                <div style='font-size:20px;color:{"#00ff9d" if calmar_med>1 else "#f59e0b"};font-weight:700'>
                                    {calmar_med:.3f}
                                </div>
                            </div>
                            <div>
                                <div style='font-size:10px;color:#444466;letter-spacing:2px'>WIN RATE REAL</div>
                                <div style='font-size:20px;color:{"#00ff9d" if wr_med>55 else "#f59e0b" if wr_med>45 else "#ff4466"};font-weight:700'>
                                    {wr_med:.1f}%
                                </div>
                            </div>
                            <div>
                                <div style='font-size:10px;color:#444466;letter-spacing:2px'>MAX DRAWDOWN</div>
                                <div style='font-size:20px;color:{"#00ff9d" if abs(dd_med)<10 else "#f59e0b" if abs(dd_med)<20 else "#ff4466"};font-weight:700'>
                                    {dd_med:.1f}%
                                </div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Gráfica retorno por ventana vs B&H
                    fig_wf = go.Figure()
                    fig_wf.add_trace(go.Bar(
                        x=df_wf_res["fecha_inicio"],
                        y=df_wf_res["retorno"],
                        name="Estrategia RSI+MACD",
                        marker_color=["#00ff9d" if r > b else "#ff4466"
                                      for r, b in zip(df_wf_res["retorno"], df_wf_res["bnh"])],
                        opacity=0.85,
                    ))
                    fig_wf.add_trace(go.Scatter(
                        x=df_wf_res["fecha_inicio"],
                        y=df_wf_res["bnh"],
                        name="Buy & Hold",
                        line=dict(color="#f59e0b", width=2, dash="dot"),
                        mode="lines+markers",
                    ))
                    fig_wf.add_hline(y=0, line=dict(color="#2a2a44", width=1))
                    fig_wf.update_layout(
                        template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                        font=dict(family="Syne", color="#e8e8f0"),
                        title=f"Retorno por ventana de {wf_test} días — {wf_ticker}",
                        height=320, margin=dict(l=16,r=16,t=48,b=16),
                        xaxis=dict(showgrid=False, color="#444466"),
                        yaxis=dict(gridcolor="#1c1c30", color="#444466", ticksuffix="%"),
                        legend=dict(bgcolor="#0a0a16", font=dict(family="JetBrains Mono", size=11)),
                        barmode="overlay",
                    )
                    st.plotly_chart(fig_wf, use_container_width=True)

                    # Tabla detallada
                    st.markdown("<div class='label-tag'>Detalle por ventana</div>", unsafe_allow_html=True)
                    for _, row_wf in df_wf_res.iterrows():
                        supera = row_wf["retorno"] > row_wf["bnh"]
                        c = "#00ff9d" if supera else "#ff4466"
                        st.markdown(f"""
                        <div style='background:#0a0a16;border:1px solid {"#00ff9d33" if supera else "#ff446633"};
                                    border-left:3px solid {c};border-radius:8px;
                                    padding:10px 14px;margin-bottom:6px;
                                    display:flex;gap:20px;flex-wrap:wrap;align-items:center;
                                    font-family:JetBrains Mono;font-size:12px'>
                            <span style='color:#666'>{row_wf["fecha_inicio"]} → {row_wf["fecha_fin"]}</span>
                            <span style='color:{c};font-weight:700'>Estrategia: {row_wf["retorno"]:+.1f}%</span>
                            <span style='color:#f59e0b'>B&H: {row_wf["bnh"]:+.1f}%</span>
                            <span style='color:#888'>Sharpe: {row_wf["sharpe"]:.2f}</span>
                            <span style='color:#888'>WinRate: {row_wf["win_rate"]:.0f}%</span>
                            <span style='color:#888'>Trades: {row_wf["n_trades"]}</span>
                            <span style='color:{"#ff4466" if row_wf["max_dd"]<-15 else "#f59e0b"}'>DD: {row_wf["max_dd"]:.1f}%</span>
                        </div>
                        """, unsafe_allow_html=True)

    # ─────────────────────────────────────────
    #  TAB 2 — HMM ENSEMBLE
    # ─────────────────────────────────────────
    with tab2:
        st.markdown("""
        <div style='color:#888;font-size:13px;margin-bottom:16px'>
        Entrena 3 HMMs independientes con ventanas históricas diferentes.
        El régimen final se decide por votación ponderada. Más robusto que un solo HMM
        porque reduce el sobreajuste a un período específico.
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([2, 2])
        ens_ticker = col1.text_input("Ticker", value=tickers_port[0] if tickers_port else "SPY", key="ens_t")
        ens_period = col2.select_slider("Periodo", options=["1y","2y","3y","5y"], value="2y", key="ens_p")

        if st.button("▶ Ejecutar HMM Ensemble", use_container_width=True, key="ens_run"):
            with st.spinner("Entrenando ensemble de 3 HMMs…"):
                serie_ens = get_historico(ens_ticker, ens_period)
                if serie_ens is None or len(serie_ens) < 120:
                    st.error("Datos insuficientes.")
                else:
                    # Tres HMMs con ventanas distintas
                    ventanas = [
                        ("Corto (6m)",  serie_ens.iloc[-126:]),
                        ("Medio (1a)",  serie_ens.iloc[-252:] if len(serie_ens)>=252 else serie_ens),
                        ("Largo (2a)",  serie_ens),
                    ]
                    resultados_ens = []
                    for nombre_v, serie_v in ventanas:
                        estados_v, fechas_v = hmm_regimen(serie_v)
                        if estados_v is not None:
                            resultados_ens.append((nombre_v, estados_v, fechas_v, serie_v))

                    if not resultados_ens:
                        st.error("No se pudo entrenar ningún HMM.")
                    else:
                        # Índice común a todos los HMMs
                        idx_comun = resultados_ens[0][2]
                        for _, _, fechas_v, _ in resultados_ens[1:]:
                            idx_comun = idx_comun.intersection(fechas_v)

                        # Votación ponderada: largo tiene más peso
                        pesos = [0.25, 0.35, 0.40]
                        votos = np.zeros((len(idx_comun), 3))  # prob por estado

                        for (nombre_v, estados_v, fechas_v, _), peso in zip(resultados_ens, pesos):
                            for j, fecha in enumerate(idx_comun):
                                if fecha in fechas_v:
                                    idx_f = list(fechas_v).index(fecha)
                                    if idx_f < len(estados_v):
                                        votos[j, estados_v[idx_f]] += peso

                        estados_ensemble = np.argmax(votos, axis=1)
                        confianza        = votos.max(axis=1)  # qué tan unánime fue la votación

                        estado_actual  = int(estados_ensemble[-1])
                        conf_actual    = float(confianza[-1])
                        n_bull = (estados_ensemble == 2).sum()
                        n_lat  = (estados_ensemble == 1).sum()
                        n_bear = (estados_ensemble == 0).sum()
                        total_e = len(estados_ensemble)

                        # Acuerdo entre HMMs en el período reciente
                        acuerdo_reciente = confianza[-20:].mean() if len(confianza) >= 20 else confianza.mean()

                        clase_e = clase_regimen(estado_actual)
                        color_e = color_regimen(estado_actual)
                        conf_color = "#00ff9d" if conf_actual > 0.7 else "#f59e0b" if conf_actual > 0.5 else "#ff4466"

                        st.markdown(f"""
                        <div class='{clase_e}' style='margin:16px 0;display:flex;
                                    justify-content:space-between;align-items:center'>
                            <div>
                                <div style='font-size:11px;letter-spacing:2px;
                                            font-family:JetBrains Mono;opacity:0.7'>
                                    RÉGIMEN ENSEMBLE — {ens_ticker}
                                </div>
                                <div style='font-size:26px;margin-top:4px'>
                                    {nombre_regimen(estado_actual)}
                                </div>
                            </div>
                            <div style='text-align:right'>
                                <div style='font-size:10px;color:#444466;font-family:JetBrains Mono'>
                                    CONFIANZA DEL ENSEMBLE
                                </div>
                                <div style='font-size:28px;font-weight:800;color:{conf_color}'>
                                    {conf_actual*100:.0f}%
                                </div>
                                <div style='font-size:11px;color:#666;font-family:JetBrains Mono'>
                                    acuerdo reciente: {acuerdo_reciente*100:.0f}%
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                        # Distribución
                        c1, c2, c3 = st.columns(3)
                        c1.metric("🐂 Alcista", f"{n_bull/total_e*100:.1f}%", f"{n_bull} días")
                        c2.metric("↔️ Lateral",  f"{n_lat/total_e*100:.1f}%",  f"{n_lat} días")
                        c3.metric("🐻 Bajista", f"{n_bear/total_e*100:.1f}%", f"{n_bear} días")

                        # Gráfica precio + regímenes + confianza
                        fig_ens = make_subplots(
                            rows=3, cols=1, shared_xaxes=True,
                            row_heights=[0.55, 0.25, 0.20],
                            vertical_spacing=0.04,
                            subplot_titles=[f"{ens_ticker} — Régimen Ensemble",
                                            "Confianza del Ensemble", "Estado"]
                        )
                        precio_ens = serie_ens.reindex(idx_comun).values
                        fig_ens.add_trace(go.Scatter(
                            x=idx_comun, y=precio_ens, name="Precio",
                            line=dict(color="#e8e8f0", width=1.5)
                        ), row=1, col=1)

                        # Sombreado por régimen
                        for e, fill_c, lbl in [(2,"rgba(0,255,157,0.15)","Alcista"),
                                               (1,"rgba(245,158,11,0.12)","Lateral"),
                                               (0,"rgba(255,68,102,0.15)","Bajista")]:
                            mask = estados_ensemble == e
                            in_b = False; x0 = None
                            for jj, mm in enumerate(mask):
                                if mm and not in_b:
                                    x0 = idx_comun[jj]; in_b = True
                                elif not mm and in_b:
                                    fig_ens.add_vrect(x0=x0, x1=idx_comun[jj-1],
                                                     fillcolor=fill_c, line_width=0, row=1, col=1)
                                    in_b = False
                            if in_b and x0 is not None:
                                fig_ens.add_vrect(x0=x0, x1=idx_comun[-1],
                                                 fillcolor=fill_c, line_width=0, row=1, col=1)
                            fig_ens.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                                marker=dict(size=10, symbol="square",
                                            color=fill_c.replace("0.15","1").replace("0.12","1")),
                                name=lbl, showlegend=True), row=1, col=1)

                        # Línea de confianza
                        conf_colors = [color_regimen(e) for e in estados_ensemble]
                        fig_ens.add_trace(go.Scatter(
                            x=idx_comun, y=confianza * 100,
                            name="Confianza", fill="tozeroy",
                            line=dict(color="#3b82f6", width=1.5),
                            fillcolor="rgba(59,130,246,0.1)",
                        ), row=2, col=1)
                        fig_ens.add_hline(y=70, line=dict(color="#00ff9d", dash="dash", width=1), row=2, col=1)
                        fig_ens.add_hline(y=50, line=dict(color="#f59e0b", dash="dash", width=1), row=2, col=1)

                        # Timeline estados
                        fig_ens.add_trace(go.Scatter(
                            x=idx_comun, y=estados_ensemble,
                            mode="markers",
                            marker=dict(color=conf_colors, size=3, symbol="square"),
                            showlegend=False,
                        ), row=3, col=1)
                        fig_ens.update_yaxes(tickvals=[0,1,2], ticktext=["Bajista","Lateral","Alcista"], row=3, col=1)

                        fig_ens.update_layout(
                            template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                            font=dict(family="Syne", color="#e8e8f0"), height=560,
                            margin=dict(l=16,r=16,t=40,b=16),
                            legend=dict(bgcolor="#0a0a16", font=dict(family="JetBrains Mono", size=11))
                        )
                        for rr in [1, 2, 3]:
                            fig_ens.update_xaxes(gridcolor="#1c1c30", color="#444466", showgrid=False, row=rr, col=1)
                            fig_ens.update_yaxes(gridcolor="#1c1c30", color="#444466", row=rr, col=1)
                        st.plotly_chart(fig_ens, use_container_width=True)

                        # Comparar HMMs individuales vs ensemble
                        st.markdown("<div class='label-tag'>Comparación HMM individual vs Ensemble</div>", unsafe_allow_html=True)
                        for nombre_v, estados_v, fechas_v, _ in resultados_ens:
                            idx_v = idx_comun.intersection(fechas_v)
                            if len(idx_v) == 0: continue
                            e_v   = estados_v[-1] if len(estados_v) > 0 else 1
                            color_v2 = color_regimen(int(e_v))
                            st.markdown(f"""
                            <div style='background:#0a0a16;border:1px solid #1c1c30;border-radius:8px;
                                        padding:10px 16px;margin-bottom:6px;
                                        display:flex;justify-content:space-between;
                                        font-family:JetBrains Mono;font-size:13px'>
                                <span style='color:#888'>{nombre_v}</span>
                                <span style='color:{color_v2};font-weight:700'>
                                    {nombre_regimen(int(e_v))}
                                </span>
                            </div>
                            """, unsafe_allow_html=True)

    # ─────────────────────────────────────────
    #  TAB 3 — PARTICLE FILTER
    # ─────────────────────────────────────────
    with tab3:
        st.markdown("""
        <div style='color:#888;font-size:13px;margin-bottom:16px'>
        El Particle Filter (filtro de partículas) es superior al Kalman para
        señales no lineales. Mantiene múltiples hipótesis simultáneas del estado
        real del mercado — cada "partícula" es un escenario posible.
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([2, 2])
        pf_ticker  = col1.text_input("Ticker", value=tickers_port[0] if tickers_port else "SPY", key="pf_t")
        pf_n_part  = col2.selectbox("Número de partículas", [200, 500, 1000, 2000], index=1, key="pf_n")
        pf_period  = st.select_slider("Periodo", options=["3mo","6mo","1y","2y"], value="1y", key="pf_p")

        if st.button("▶ Ejecutar Particle Filter", use_container_width=True, key="pf_run"):
            with st.spinner(f"Corriendo Particle Filter con {pf_n_part} partículas…"):
                serie_pf = get_historico(pf_ticker, pf_period)
                if serie_pf is None or len(serie_pf) < 30:
                    st.error("Datos insuficientes.")
                else:
                    precios_pf = serie_pf.astype(float).values
                    N = pf_n_part
                    np.random.seed(42)

                    # Estado: [precio_suavizado, velocidad, volatilidad_log]
                    # Partículas: distribución inicial alrededor del primer precio
                    particles = np.zeros((N, 3))
                    particles[:, 0] = precios_pf[0] * (1 + np.random.normal(0, 0.01, N))
                    particles[:, 1] = np.random.normal(0, 0.001, N)  # velocidad
                    particles[:, 2] = np.random.normal(0.01, 0.005, N).clip(0.001, 0.1)  # vol

                    weights    = np.ones(N) / N
                    estimados  = []
                    incertidumbre = []

                    # Ruido del proceso
                    Q_p = np.diag([0.001, 0.0001, 0.00001])
                    # Ruido de observación
                    R_obs = 0.005

                    for precio_obs in precios_pf:
                        # 1. Predicción: mover partículas según modelo
                        noise = np.random.multivariate_normal([0, 0, 0], Q_p, N)
                        particles[:, 1] += noise[:, 1]  # velocidad cambia
                        particles[:, 0] += particles[:, 1] + noise[:, 0]  # precio cambia
                        particles[:, 2] = np.abs(particles[:, 2] + noise[:, 2]).clip(0.001, 0.15)

                        # 2. Actualización: peso según verosimilitud de la observación
                        err = precio_obs - particles[:, 0]
                        sigma_obs = particles[:, 2] * precio_obs  # vol relativa
                        likelihood = np.exp(-0.5 * (err / sigma_obs) ** 2) / (sigma_obs * np.sqrt(2 * np.pi))
                        likelihood = np.clip(likelihood, 1e-300, None)
                        weights = weights * likelihood
                        weights /= weights.sum() + 1e-300

                        # 3. Estimación: media ponderada
                        est = np.average(particles[:, 0], weights=weights)
                        inc = np.sqrt(np.average((particles[:, 0] - est)**2, weights=weights))
                        estimados.append(float(est))
                        incertidumbre.append(float(inc))

                        # 4. Resampling efectivo si pocos pesos dominan
                        N_eff = 1.0 / (weights ** 2).sum()
                        if N_eff < N * 0.5:
                            indices = np.random.choice(N, size=N, p=weights)
                            particles = particles[indices]
                            weights = np.ones(N) / N

                    estimados     = np.array(estimados)
                    incertidumbre = np.array(incertidumbre)

                    # Comparar con Kalman clásico
                    kalman_est = []
                    xhat_k, P_k, Q_k, R_k = precios_pf[0], 1.0, 1e-5, 0.01**2
                    for pp in precios_pf:
                        Pm_k = P_k + Q_k; K_k = Pm_k / (Pm_k + R_k)
                        xhat_k = xhat_k + K_k * (pp - xhat_k); P_k = (1 - K_k) * Pm_k
                        kalman_est.append(xhat_k)

                    # Error cuadrático medio de cada filtro
                    mse_pf = np.mean((precios_pf - estimados) ** 2)
                    mse_k  = np.mean((precios_pf - np.array(kalman_est)) ** 2)
                    mejora = (mse_k - mse_pf) / mse_k * 100

                    # Señal actual
                    precio_actual_pf = float(precios_pf[-1])
                    est_actual       = float(estimados[-1])
                    inc_actual       = float(incertidumbre[-1])
                    diff_pct         = (precio_actual_pf - est_actual) / est_actual * 100

                    señal_pf = "🚨 SOBRECOMPRADO" if diff_pct > 3 else \
                               "🟢 OPORTUNIDAD"   if diff_pct < -3 else "⚪ NEUTRAL"
                    color_pf = "#ff4466" if diff_pct > 3 else "#00ff9d" if diff_pct < -3 else "#888"

                    # Cards de resultado
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("🎯 Precio estimado", f"${est_actual:,.2f}")
                    c2.metric("📊 Precio actual",   f"${precio_actual_pf:,.2f}", f"{diff_pct:+.2f}%")
                    c3.metric("📉 Incertidumbre",   f"±${inc_actual:,.2f}")
                    c4.metric("⚡ Mejora vs Kalman", f"{mejora:+.1f}%")

                    st.markdown(f"""
                    <div style='background:{color_pf}11;border:1px solid {color_pf}44;
                                border-left:4px solid {color_pf};border-radius:12px;
                                padding:14px 20px;margin:12px 0'>
                        <div style='font-size:18px;font-weight:800;color:{color_pf}'>{señal_pf}</div>
                        <div style='font-family:JetBrains Mono;font-size:12px;color:#666;margin-top:4px'>
                            Precio está {abs(diff_pct):.1f}% {"por encima" if diff_pct>0 else "por debajo"}
                            de la estimación del Particle Filter
                            &nbsp;|&nbsp; Banda de confianza: ${est_actual-inc_actual:,.2f} – ${est_actual+inc_actual:,.2f}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Gráfica
                    fig_pf = go.Figure()
                    banda_sup = estimados + incertidumbre * 2
                    banda_inf = estimados - incertidumbre * 2
                    fechas_pf = list(serie_pf.index)

                    fig_pf.add_trace(go.Scatter(
                        x=fechas_pf + fechas_pf[::-1],
                        y=list(banda_sup) + list(banda_inf[::-1]),
                        fill="toself", fillcolor="rgba(59,130,246,0.08)",
                        line=dict(width=0), name="Banda ±2σ", showlegend=True,
                    ))
                    fig_pf.add_trace(go.Scatter(
                        x=fechas_pf, y=precios_pf,
                        name="Precio real", line=dict(color="#e8e8f0", width=1.5)
                    ))
                    fig_pf.add_trace(go.Scatter(
                        x=fechas_pf, y=estimados,
                        name=f"Particle Filter (MSE={mse_pf:.4f})",
                        line=dict(color="#00ff9d", width=2)
                    ))
                    fig_pf.add_trace(go.Scatter(
                        x=fechas_pf, y=kalman_est,
                        name=f"Kalman clásico (MSE={mse_k:.4f})",
                        line=dict(color="#f59e0b", width=1.5, dash="dot")
                    ))
                    fig_pf.update_layout(
                        template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                        font=dict(family="Syne", color="#e8e8f0"),
                        title=f"{pf_ticker} — Particle Filter vs Kalman clásico ({pf_n_part} partículas)",
                        height=400, margin=dict(l=16,r=16,t=48,b=16), hovermode="x unified",
                        xaxis=dict(showgrid=False, color="#444466"),
                        yaxis=dict(gridcolor="#1c1c30", color="#444466"),
                        legend=dict(bgcolor="#0a0a16", font=dict(family="JetBrains Mono", size=11))
                    )
                    st.plotly_chart(fig_pf, use_container_width=True)

    # ─────────────────────────────────────────
    #  TAB 4 — KELLY CON CORRELACIONES
    # ─────────────────────────────────────────
    with tab4:
        st.markdown("""
        <div style='color:#888;font-size:13px;margin-bottom:16px'>
        El Kelly simple asume que cada posición es independiente.
        Pero AAPL y MSFT están correlacionadas — si una cae, la otra también.
        El Kelly con correlaciones ajusta el sizing para que el riesgo real del portafolio
        sea el que calculas, no el doble por tener activos correlacionados.
        </div>
        """, unsafe_allow_html=True)

        capital_kelly = st.number_input("Capital total $", value=10000.0, step=500.0, key="kc_cap")
        kelly_period  = st.select_slider("Periodo histórico", options=["6mo","1y","2y"], value="1y", key="kc_p")

        tickers_kelly = tickers_port.copy()
        extra_k = st.text_input("Agregar tickers extra (separados por coma)", placeholder="NVDA, META, GSPC", key="kc_e")
        if extra_k.strip():
            for tk in extra_k.split(","):
                tk = tk.strip().upper()
                if tk and tk not in tickers_kelly:
                    tickers_kelly.append(tk)

        if not tickers_kelly:
            st.info("Agrega acciones a tu portafolio o escribe tickers arriba.")
        elif st.button("▶ Calcular Kelly con Correlaciones", use_container_width=True, key="kc_run"):
            with st.spinner("Calculando matriz de correlaciones y sizing óptimo…"):
                series_dict = {}
                for tk in tickers_kelly:
                    s = get_historico(tk, kelly_period)
                    if s is not None and len(s) > 30:
                        series_dict[tk] = s

                if len(series_dict) < 2:
                    st.error("Necesitas al menos 2 activos con datos para calcular correlaciones.")
                else:
                    # Alinear series en índice común
                    df_all = pd.DataFrame(series_dict)
                    df_all = df_all.dropna()
                    ret_df = df_all.pct_change().dropna()

                    # Matriz de correlaciones
                    corr_mat = ret_df.corr()

                    # Kelly individual por activo
                    kelly_ind = {}
                    for tk in series_dict:
                        r = ret_df[tk]
                        wins = r[r>0]; losses = r[r<0]
                        if len(wins) > 0 and len(losses) > 0:
                            p = len(wins)/len(r)
                            b = wins.mean() / abs(losses.mean()) if losses.mean() != 0 else 1
                            k = max(0.0, min((b*p - (1-p)) / b, 0.5))
                        else:
                            k = 0.0
                        kelly_ind[tk] = k

                    # Ajuste por correlación: reducir Kelly según correlación promedio con los demás
                    tickers_k = list(series_dict.keys())
                    kelly_ajustado = {}
                    for tk in tickers_k:
                        corrs_otros = [abs(corr_mat.loc[tk, tk2])
                                       for tk2 in tickers_k if tk2 != tk]
                        corr_prom = np.mean(corrs_otros) if corrs_otros else 0
                        # Factor de penalización: a mayor correlación con los demás, menor Kelly
                        factor = 1 - (corr_prom * 0.5)
                        kelly_ajustado[tk] = kelly_ind[tk] * factor

                    # Normalizar para que la suma no supere 100%
                    suma_k = sum(kelly_ajustado.values())
                    if suma_k > 1.0:
                        kelly_ajustado = {tk: v/suma_k for tk, v in kelly_ajustado.items()}

                    # Heatmap de correlaciones
                    st.markdown("<div class='label-tag'>Matriz de correlaciones</div>", unsafe_allow_html=True)
                    fig_corr = go.Figure(go.Heatmap(
                        z=corr_mat.values,
                        x=corr_mat.columns.tolist(),
                        y=corr_mat.index.tolist(),
                        colorscale=[
                            [0.0,  "#ff4466"],
                            [0.5,  "#0e0e1e"],
                            [1.0,  "#00ff9d"],
                        ],
                        zmid=0, zmin=-1, zmax=1,
                        text=np.round(corr_mat.values, 2),
                        texttemplate="%{text}",
                        textfont=dict(size=11, family="JetBrains Mono"),
                        hoverongaps=False,
                    ))
                    fig_corr.update_layout(
                        template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                        font=dict(family="Syne", color="#e8e8f0"),
                        height=max(300, len(tickers_k) * 55 + 80),
                        margin=dict(l=16,r=16,t=16,b=16),
                    )
                    st.plotly_chart(fig_corr, use_container_width=True)

                    # Comparativa Kelly simple vs ajustado
                    st.markdown("<div class='label-tag'>Kelly simple vs Kelly ajustado por correlación</div>", unsafe_allow_html=True)
                    fig_kk = go.Figure()
                    fig_kk.add_trace(go.Bar(
                        x=tickers_k,
                        y=[kelly_ind[tk]*100 for tk in tickers_k],
                        name="Kelly simple", marker_color="#3b82f6", opacity=0.7,
                    ))
                    fig_kk.add_trace(go.Bar(
                        x=tickers_k,
                        y=[kelly_ajustado[tk]*100 for tk in tickers_k],
                        name="Kelly ajustado (correlaciones)", marker_color="#00ff9d", opacity=0.9,
                    ))
                    fig_kk.update_layout(
                        template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                        font=dict(family="Syne", color="#e8e8f0"),
                        barmode="group", height=300,
                        margin=dict(l=16,r=16,t=16,b=16),
                        xaxis=dict(showgrid=False, color="#444466"),
                        yaxis=dict(gridcolor="#1c1c30", color="#444466", ticksuffix="%"),
                        legend=dict(bgcolor="#0a0a16", font=dict(family="JetBrains Mono", size=11)),
                    )
                    st.plotly_chart(fig_kk, use_container_width=True)

                    # Cards de asignación recomendada
                    st.markdown("<div class='label-tag'>Asignación óptima recomendada</div>", unsafe_allow_html=True)
                    total_asig = sum(kelly_ajustado.values())
                    cols_k = st.columns(min(len(tickers_k), 4))
                    for ci, tk in enumerate(sorted(tickers_k, key=lambda x: kelly_ajustado[x], reverse=True)):
                        k_s = kelly_ind[tk]
                        k_a = kelly_ajustado[tk]
                        reduccion = (k_s - k_a) / k_s * 100 if k_s > 0 else 0
                        dolar_rec = k_a * capital_kelly
                        corrs_otros = [abs(corr_mat.loc[tk, tk2]) for tk2 in tickers_k if tk2 != tk]
                        corr_p = np.mean(corrs_otros) if corrs_otros else 0

                        color_k2 = "#00ff9d" if k_a > 0.15 else "#f59e0b" if k_a > 0.05 else "#666"
                        with cols_k[ci % 4]:
                            st.markdown(f"""
                            <div style='background:#0e0e1e;border:1px solid #1c1c30;
                                        border-left:3px solid {color_k2};border-radius:12px;
                                        padding:14px;margin-bottom:10px'>
                                <div style='font-weight:800;font-size:16px'>{tk}</div>
                                <div style='font-family:JetBrains Mono;font-size:22px;
                                            font-weight:700;color:{color_k2};margin:6px 0'>
                                    {k_a*100:.1f}%
                                </div>
                                <div style='font-family:JetBrains Mono;font-size:13px;color:#e8e8f0'>
                                    ${dolar_rec:,.0f}
                                </div>
                                <div style='margin-top:8px;padding-top:8px;border-top:1px solid #1c1c30;
                                            font-size:11px;color:#666;font-family:JetBrains Mono'>
                                    Simple: {k_s*100:.1f}% &nbsp;→&nbsp;
                                    <span style='color:#f59e0b'>-{reduccion:.0f}% por correlación</span><br>
                                    Corr. promedio: {corr_p:.2f}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                    st.markdown(f"""
                    <div style='background:#f59e0b0e;border:1px solid #f59e0b33;border-radius:10px;
                                padding:14px 18px;margin-top:8px;font-size:13px;color:#f59e0b'>
                        ⚠️ <strong>Capital asignado total: {total_asig*100:.1f}% de ${capital_kelly:,.0f}</strong>
                        = <strong>${total_asig*capital_kelly:,.0f}</strong> &nbsp;·&nbsp;
                        El {(1-total_asig)*100:.1f}% restante (${(1-total_asig)*capital_kelly:,.0f})
                        se mantiene en efectivo como colchón de riesgo.
                    </div>
                    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
#  🎯 MOTOR DE DECISIÓN UNIFICADO
#  Integra todas las señales → probabilidad + tamaño óptimo
# ═══════════════════════════════════════════════════════════
elif st.session_state.vista == "motor":

    st.markdown("""
    <div style='padding:28px 0 8px'>
        <div class='label-tag'>MOTOR DE DECISIÓN UNIFICADO</div>
        <div style='font-size:28px;font-weight:800;letter-spacing:-0.5px'>🎯 Sistema Cuantitativo Completo</div>
        <div style='color:#666;font-size:13px;margin-top:6px'>
            Kalman · HMM Ensemble · Particle Filter · Técnico · Fundamental · Kelly · VaR · Monte Carlo
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ─── Funciones del motor ───────────────────────────────

    def señal_kalman(serie):
        """Retorna score [-1,1] del filtro Kalman sobre tendencia"""
        precios = serie.astype(float).values
        xhat, P, Q, R = precios[0], 1.0, 1e-5, 0.01**2
        for p in precios:
            Pm = P+Q; K = Pm/(Pm+R); xhat = xhat+K*(p-xhat); P=(1-K)*Pm
        diff_pct = (precios[-1] - xhat) / xhat * 100
        # Score: positivo = precio por encima de tendencia (posible techo)
        # negativo = precio por debajo de tendencia (posible piso)
        score = np.clip(diff_pct / 5.0, -1.0, 1.0)
        return float(-score), float(xhat), float(precios[-1])  # invertido: techo = vender

    def señal_hmm_ensemble(serie):
        """Retorna score [-1,1] del HMM ensemble y confianza"""
        ventanas = [serie.iloc[-126:], serie.iloc[-252:] if len(serie)>=252 else serie, serie]
        pesos_v  = [0.25, 0.35, 0.40]
        votos_e  = None
        n_hmms   = 0
        for sv, peso in zip(ventanas, pesos_v):
            estados_v, fechas_v = hmm_regimen(sv)
            if estados_v is None: continue
            if votos_e is None:
                votos_e = np.zeros(3)
            votos_e[int(estados_v[-1])] += peso
            n_hmms += 1
        if votos_e is None: return 0.0, 0.0
        estado_f    = int(np.argmax(votos_e))
        confianza_f = float(votos_e[estado_f])
        # 0=bajista→-1, 1=lateral→0, 2=alcista→+1
        score_hmm = (estado_f - 1.0) * confianza_f
        return float(score_hmm), float(confianza_f)

    def señal_particle_filter(serie, N=300):
        """Score del Particle Filter: distancia normalizada precio vs estimado"""
        precios_v = serie.astype(float).values
        particles = np.zeros((N, 2))
        particles[:,0] = precios_v[0]*(1+np.random.normal(0,0.01,N))
        particles[:,1] = np.random.normal(0,0.001,N)
        weights = np.ones(N)/N
        Q_p = np.diag([0.002, 0.0001]); R_p = 0.005
        for pp in precios_v:
            noise = np.random.multivariate_normal([0,0], Q_p, N)
            particles[:,1] += noise[:,1]
            particles[:,0] += particles[:,1] + noise[:,0]
            err  = pp - particles[:,0]
            sigma_p = max(pp*0.01, 0.001)
            lk   = np.exp(-0.5*(err/sigma_p)**2)/(sigma_p*np.sqrt(2*np.pi))+1e-300
            weights = weights*lk; weights /= weights.sum()+1e-300
            if 1.0/(weights**2).sum() < N*0.5:
                idx = np.random.choice(N, N, p=weights)
                particles = particles[idx]; weights = np.ones(N)/N
        est = float(np.average(particles[:,0], weights=weights))
        diff_pct = (precios_v[-1] - est) / est * 100
        # Precio muy por encima del estimado = sobrecomprado = señal venta
        score_pf = float(np.clip(-diff_pct/3.0, -1.0, 1.0))
        return score_pf, est

    def señal_tecnica(serie):
        """Score técnico combinado RSI+MACD+BB normalizado a [-1,1]"""
        close = serie.astype(float)
        rsi = calcular_rsi(close)
        _, _, hist = calcular_macd(close)
        bb_up, _, bb_lo = calcular_bollinger(close)
        rsi_v  = float(rsi.iloc[-1])  if not np.isnan(rsi.iloc[-1])  else 50
        hist_v = float(hist.iloc[-1]) if not np.isnan(hist.iloc[-1]) else 0
        p      = float(close.iloc[-1])
        bb_u   = float(bb_up.iloc[-1]) if not np.isnan(bb_up.iloc[-1]) else p*1.02
        bb_l   = float(bb_lo.iloc[-1]) if not np.isnan(bb_lo.iloc[-1]) else p*0.98
        score = 0.0
        score += (50 - rsi_v) / 50.0 * 0.4        # RSI: <50 = alcista
        score += np.sign(hist_v) * 0.3             # MACD: positivo = alcista
        if p < bb_l:   score += 0.3                # BB: bajo banda = alcista
        elif p > bb_u: score -= 0.3                # BB: sobre banda = bajista
        return float(np.clip(score, -1.0, 1.0)), rsi_v, hist_v

    def señal_fundamental(ticker):
        """Score fundamental normalizado a [-1,1] basado en métricas clave"""
        fd = get_fundamentales(ticker)
        if not fd: return 0.0
        score = 0.0; n = 0
        # P/E: <15 bueno, >30 malo
        if fd["pe_ratio"]:
            score += np.clip((20-fd["pe_ratio"])/20.0, -1,1)*0.25; n+=1
        # ROE: >15% bueno
        if fd["roe"]:
            score += np.clip((fd["roe"]-0.05)/0.15, -1,1)*0.25; n+=1
        # Margen neto: >10% bueno
        if fd["margen_neto"]:
            score += np.clip((fd["margen_neto"]-0.03)/0.12, -1,1)*0.2; n+=1
        # Crecimiento revenue: >10% bueno
        if fd["rev_growth"]:
            score += np.clip(fd["rev_growth"]/0.2, -1,1)*0.15; n+=1
        # Deuda/equity: <80 bueno
        if fd["debt_equity"]:
            score += np.clip((80-fd["debt_equity"])/80.0, -1,1)*0.15; n+=1
        return float(np.clip(score/max(n,1)*5, -1.0, 1.0)) if n>0 else 0.0

    def calcular_var_es(serie, confianza=0.95, horizonte=1):
        """Value at Risk y Expected Shortfall"""
        ret = serie.pct_change().dropna().astype(float)
        var = float(np.percentile(ret, (1-confianza)*100))
        es  = float(ret[ret <= var].mean()) if len(ret[ret<=var])>0 else var
        return var*np.sqrt(horizonte), es*np.sqrt(horizonte)

    def montecarlo_portfolio(serie, capital, n_sim=1000, horizonte=30):
        """Monte Carlo: distribución de escenarios futuros"""
        ret = serie.pct_change().dropna().astype(float)
        mu  = float(ret.mean())
        sig = float(ret.std())
        precio_actual = float(serie.iloc[-1])
        sims = np.zeros((n_sim, horizonte))
        for i in range(n_sim):
            r = np.random.normal(mu, sig, horizonte)
            sims[i] = precio_actual * np.cumprod(1+r)
        valores_finales = sims[:,-1] * (capital / precio_actual)
        return sims, valores_finales, precio_actual

    def motor_decision_unificado(scores_dict, pesos_config, capital, kelly_k, var_1d, regimen):
        """
        Combina scores → probabilidad → tamaño de posición ajustado por riesgo
        scores_dict: {señal: score entre -1 y +1}
        pesos_config: {señal: peso}
        """
        # Score ponderado total
        score_total = sum(scores_dict[k]*pesos_config.get(k,0) for k in scores_dict
                          if k in pesos_config)
        suma_pesos  = sum(pesos_config.get(k,0) for k in scores_dict if k in pesos_config)
        score_norm  = score_total / suma_pesos if suma_pesos > 0 else 0.0

        # Convertir a probabilidad via sigmoide
        prob_compra = 1 / (1 + np.exp(-score_norm * 4))

        # Zona de decisión
        if prob_compra >= 0.70:   decision, color_d = "🟢 COMPRAR",  "#00ff9d"
        elif prob_compra >= 0.60: decision, color_d = "🟡 ACUMULAR", "#f59e0b"
        elif prob_compra <= 0.30: decision, color_d = "🔴 VENDER",   "#ff4466"
        elif prob_compra <= 0.40: decision, color_d = "🟠 REDUCIR",  "#f97316"
        else:                     decision, color_d = "⚪ NEUTRAL",   "#888"

        # Position sizing ajustado por régimen
        factor_regimen = {2: 1.0, 1: 0.6, 0: 0.3}.get(regimen, 0.6)
        kelly_regime   = kelly_k * factor_regimen

        # Ajuste por VaR: si el VaR diario > 3%, reducir posición
        var_factor = min(1.0, 0.03 / abs(var_1d)) if abs(var_1d) > 0.001 else 1.0
        kelly_final = min(kelly_regime * var_factor, 0.40)

        capital_rec = capital * kelly_final * max(0.0, (prob_compra - 0.5) * 2)

        return {
            "score":       float(score_norm),
            "prob":        float(prob_compra),
            "decision":    decision,
            "color":       color_d,
            "kelly_adj":   float(kelly_final),
            "capital_rec": float(capital_rec),
            "factor_reg":  float(factor_regimen),
            "var_factor":  float(var_factor),
        }

    # ─── UI del Motor ──────────────────────────────────────

    port = st.session_state.portfolio.reset_index(drop=True)
    tickers_port_m = port["Ticker"].tolist() if not port.empty else []

    col1, col2, col3 = st.columns([2, 2, 1])
    motor_ticker  = col1.text_input("Ticker a analizar", placeholder="AAPL, TSLA, GMEXICO.MX…", key="mot_t")
    motor_port_t  = col2.selectbox("O desde portafolio", [""] + tickers_port_m, key="mot_p")
    motor_capital = col3.number_input("Capital $", value=10000.0, step=500.0, key="mot_c")
    motor_ticker  = motor_ticker.upper().strip() or motor_port_t

    # ── Inicializar pesos en session_state ──
    if "pesos_optimizados" not in st.session_state:
        st.session_state.pesos_optimizados = None
    if "ticker_optimizado" not in st.session_state:
        st.session_state.ticker_optimizado = ""

    # ── Panel de pesos: auto o manual ──
    with st.expander("⚙️ Pesos del motor — Auto-optimización", expanded=True):
        modo_pesos = st.radio(
            "",
            ["🤖 Auto-optimizar (recomendado)", "🎛️ Manual (sliders)"],
            horizontal=True, label_visibility="collapsed", key="modo_pesos"
        )

        if modo_pesos == "🤖 Auto-optimizar (recomendado)":
            col_opt1, col_opt2, col_opt3 = st.columns([2, 2, 1])
            opt_periodo = col_opt1.selectbox(
                "Periodo histórico para optimizar",
                ["1y", "2y", "3y"], index=1, key="opt_periodo"
            )
            opt_metrica = col_opt2.selectbox(
                "Optimizar por",
                ["Sharpe", "Calmar", "Retorno - |Drawdown|"], key="opt_metrica"
            )
            opt_metodo = col_opt3.selectbox(
                "Método",
                ["Grid (27 combos)", "Bayesiano (60 trials)"], key="opt_metodo"
            )

            ticker_cambio = motor_ticker != st.session_state.ticker_optimizado

            if st.button("🔍 Optimizar pesos automáticamente", use_container_width=True, key="btn_auto_opt") or \
               (st.session_state.pesos_optimizados is None and motor_ticker):

                if motor_ticker:
                    with st.spinner(f"Buscando pesos óptimos para {motor_ticker}…"):

                        @st.cache_data(ttl=3600, show_spinner=False)
                        def optimizar_pesos_cached(ticker, periodo, metrica, metodo):
                            """Cache para no re-optimizar si el ticker y config no cambian"""
                            serie_op = get_historico(ticker, periodo)
                            if serie_op is None or len(serie_op) < 200:
                                return None, None

                            # Split 60/40 in-sample / out-of-sample
                            corte    = int(len(serie_op) * 0.60)
                            serie_is = serie_op.iloc[:corte]

                            def evaluar_pesos(w_k, w_t, w_h):
                                pesos_g = {"kalman": w_k, "tecnico": w_t, "hmm": w_h}
                                n_is    = len(serie_is)
                                tr_is   = serie_is.iloc[:n_is//2]
                                te_is   = serie_is.iloc[n_is//2:]
                                try:
                                    res = ejecutar_motor_en_ventana(tr_is, te_is, pesos_g, 10000.0)
                                    if metrica == "Sharpe":
                                        return res["sharpe"]
                                    elif metrica == "Calmar":
                                        return res["calmar"]
                                    else:
                                        return res["ret"] - abs(res["maxdd"])
                                except:
                                    return -999.0

                            mejor_score = -999.0
                            mejor_pesos = {"kalman": 1.0, "tecnico": 1.0, "hmm": 1.0}
                            historial   = []

                            if "Grid" in metodo:
                                # Grid search: 3×3×3 = 27 combinaciones
                                grid_vals = [0.3, 1.0, 1.8]
                                for w_k in grid_vals:
                                    for w_t in grid_vals:
                                        for w_h in grid_vals:
                                            sc = evaluar_pesos(w_k, w_t, w_h)
                                            historial.append({
                                                "kalman": w_k, "tecnico": w_t,
                                                "hmm": w_h, "score": sc
                                            })
                                            if sc > mejor_score:
                                                mejor_score = sc
                                                mejor_pesos = {"kalman":w_k,"tecnico":w_t,"hmm":w_h}
                            else:
                                # Bayesiano simplificado: Gaussian Process surrogate
                                # con acquisition function UCB
                                np.random.seed(42)
                                # Fase 1: exploración aleatoria (20 puntos)
                                puntos_x = []
                                puntos_y = []
                                for _ in range(20):
                                    w_k = np.random.uniform(0.1, 2.0)
                                    w_t = np.random.uniform(0.1, 2.0)
                                    w_h = np.random.uniform(0.1, 2.0)
                                    sc  = evaluar_pesos(w_k, w_t, w_h)
                                    puntos_x.append([w_k, w_t, w_h])
                                    puntos_y.append(sc)
                                    historial.append({"kalman":w_k,"tecnico":w_t,"hmm":w_h,"score":sc})
                                    if sc > mejor_score:
                                        mejor_score = sc
                                        mejor_pesos = {"kalman":w_k,"tecnico":w_t,"hmm":w_h}

                                # Fase 2: explotación guiada (40 puntos)
                                # Surrogate: promedio ponderado por distancia (Nadaraya-Watson)
                                for _ in range(40):
                                    # Generar candidatos y elegir el de mayor UCB
                                    candidatos = np.random.uniform(0.1, 2.0, (50, 3))
                                    X   = np.array(puntos_x)
                                    Y   = np.array(puntos_y)
                                    best_acq = -999; best_c = candidatos[0]

                                    for c in candidatos:
                                        # Distancias a puntos conocidos
                                        dists = np.sqrt(((X - c)**2).sum(axis=1)) + 1e-6
                                        bw    = np.median(dists)
                                        w_nw  = np.exp(-dists**2/(2*bw**2))
                                        w_nw /= w_nw.sum()
                                        mu_c  = float(w_nw @ Y)
                                        # Incertidumbre: dispersión ponderada
                                        sigma_c = float(np.sqrt(w_nw @ (Y - mu_c)**2)) + 0.01
                                        # UCB: balance explotación/exploración
                                        acq = mu_c + 1.5 * sigma_c
                                        if acq > best_acq:
                                            best_acq = acq; best_c = c

                                    w_k, w_t, w_h = best_c
                                    sc = evaluar_pesos(w_k, w_t, w_h)
                                    puntos_x.append([w_k, w_t, w_h])
                                    puntos_y.append(sc)
                                    historial.append({"kalman":w_k,"tecnico":w_t,"hmm":w_h,"score":sc})
                                    if sc > mejor_score:
                                        mejor_score = sc
                                        mejor_pesos = {"kalman":w_k,"tecnico":w_t,"hmm":w_h}

                            # Validar out-of-sample
                            serie_os = serie_op.iloc[corte:]
                            n_os     = len(serie_os)
                            tr_os    = serie_os.iloc[:n_os//2]
                            te_os    = serie_os.iloc[n_os//2:]
                            try:
                                res_os   = ejecutar_motor_en_ventana(tr_os, te_os, mejor_pesos, 10000.0)
                                res_uni  = ejecutar_motor_en_ventana(
                                    tr_os, te_os,
                                    {"kalman":1.0,"tecnico":1.0,"hmm":1.0}, 10000.0
                                )
                            except:
                                res_os = res_uni = None

                            return {
                                "pesos":       mejor_pesos,
                                "score_is":    mejor_score,
                                "res_os":      res_os,
                                "res_uni":     res_uni,
                                "historial":   historial,
                                "n_trials":    len(historial),
                                "metodo":      metodo,
                                "metrica":     metrica,
                            }, serie_op

                        resultado_opt, _ = optimizar_pesos_cached(
                            motor_ticker, opt_periodo, opt_metrica, opt_metodo
                        )

                        if resultado_opt is None:
                            st.error("No hay suficientes datos para optimizar.")
                        else:
                            st.session_state.pesos_optimizados  = resultado_opt["pesos"]
                            st.session_state.ticker_optimizado  = motor_ticker
                            st.session_state._res_opt_completo  = resultado_opt

            # Mostrar resultado de la optimización
            if st.session_state.pesos_optimizados and st.session_state.ticker_optimizado == motor_ticker:
                opt_r   = st.session_state.pesos_optimizados
                full_r  = getattr(st.session_state, "_res_opt_completo", None)
                res_os  = full_r["res_os"]  if full_r else None
                res_uni = full_r["res_uni"] if full_r else None
                hist_df = pd.DataFrame(full_r["historial"]) if full_r else None

                # Cards de pesos encontrados
                c1,c2,c3 = st.columns(3)
                señales_w = [
                    ("🌊 Kalman",    opt_r["kalman"],  c1),
                    ("🔬 Técnico",   opt_r["tecnico"], c2),
                    ("🧬 HMM",       opt_r["hmm"],     c3),
                ]
                for lbl_w, val_w, col_w in señales_w:
                    dominante = val_w == max(opt_r.values())
                    color_w   = "#00ff9d" if dominante else "#e8e8f0"
                    col_w.markdown(f"""
                    <div style='background:{"#00ff9d0a" if dominante else "#0a0a16"};
                                border:1px solid {"#00ff9d33" if dominante else "#1c1c30"};
                                border-radius:10px;padding:12px;text-align:center'>
                        <div style='font-size:11px;color:#444466;font-family:JetBrains Mono;
                                    letter-spacing:2px;margin-bottom:4px'>{lbl_w}</div>
                        <div style='font-size:26px;font-weight:800;color:{color_w};
                                    font-family:JetBrains Mono'>{val_w:.2f}</div>
                        {"<div style='font-size:10px;color:#00ff9d;margin-top:2px'>★ DOMINANTE</div>" if dominante else ""}
                    </div>
                    """, unsafe_allow_html=True)

                # Comparativa IS vs OOS vs Uniforme
                if res_os and res_uni:
                    mejora = res_os["sharpe"] - res_uni["sharpe"]
                    color_mj = "#00ff9d" if mejora > 0 else "#ff4466"
                    st.markdown(f"""
                    <div style='background:{color_mj}0a;border:1px solid {color_mj}22;
                                border-left:3px solid {color_mj};border-radius:10px;
                                padding:10px 16px;margin-top:10px;
                                display:flex;gap:24px;flex-wrap:wrap;
                                font-family:JetBrains Mono;font-size:12px'>
                        <div>
                            <div style='color:#444466;font-size:9px;letter-spacing:2px'>MÉTODO</div>
                            <div style='color:#e8e8f0'>{full_r["metodo"]} · {full_r["n_trials"]} pruebas</div>
                        </div>
                        <div>
                            <div style='color:#444466;font-size:9px;letter-spacing:2px'>SHARPE OOS (óptimo)</div>
                            <div style='color:{color_mj};font-weight:700'>{res_os["sharpe"]:.3f}</div>
                        </div>
                        <div>
                            <div style='color:#444466;font-size:9px;letter-spacing:2px'>SHARPE OOS (uniforme)</div>
                            <div style='color:#888'>{res_uni["sharpe"]:.3f}</div>
                        </div>
                        <div>
                            <div style='color:#444466;font-size:9px;letter-spacing:2px'>MEJORA</div>
                            <div style='color:{color_mj};font-weight:700'>{mejora:+.3f}</div>
                        </div>
                        <div>
                            <div style='color:#444466;font-size:9px;letter-spacing:2px'>RET OOS</div>
                            <div style='color:{"#00ff9d" if res_os["ret"]>0 else "#ff4466"}'>{res_os["ret"]:+.1f}%</div>
                        </div>
                        <div>
                            <div style='color:#444466;font-size:9px;letter-spacing:2px'>MAX DD OOS</div>
                            <div style='color:#f59e0b'>{res_os["maxdd"]:.1f}%</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                # Gráfica evolución de la optimización
                if hist_df is not None and len(hist_df) > 5:
                    hist_df["trial"] = range(1, len(hist_df)+1)
                    hist_df["best_so_far"] = hist_df["score"].cummax()
                    hist_df_clean = hist_df[hist_df["score"] > -900]

                    fig_opt = go.Figure()
                    fig_opt.add_trace(go.Scatter(
                        x=hist_df_clean["trial"], y=hist_df_clean["score"],
                        mode="markers", name="Score por trial",
                        marker=dict(
                            color=hist_df_clean["score"],
                            colorscale=[[0,"#ff4466"],[0.5,"#f59e0b"],[1,"#00ff9d"]],
                            size=7, opacity=0.7,
                            colorbar=dict(title=full_r["metrica"] if full_r else "Score",
                                         thickness=12, len=0.7)
                        ),
                    ))
                    fig_opt.add_trace(go.Scatter(
                        x=hist_df["trial"], y=hist_df["best_so_far"],
                        name="Mejor acumulado", mode="lines",
                        line=dict(color="#00ff9d", width=2),
                    ))
                    fig_opt.update_layout(
                        template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                        font=dict(family="Syne", color="#e8e8f0"),
                        title=f"Convergencia de la optimización — {full_r['metodo'] if full_r else ''}",
                        height=260, margin=dict(l=16,r=16,t=48,b=16),
                        xaxis=dict(title="Trial #", showgrid=False, color="#444466"),
                        yaxis=dict(title=full_r["metrica"] if full_r else "Score",
                                   gridcolor="#1c1c30", color="#444466"),
                        legend=dict(bgcolor="#0a0a16", font=dict(family="JetBrains Mono", size=11)),
                    )
                    st.plotly_chart(fig_opt, use_container_width=True)

                pesos_conf = st.session_state.pesos_optimizados
                # Agregar particle y fundamental con peso fijo (no optimizados por velocidad)
                pesos_conf["particle"]    = 0.8
                pesos_conf["fundamental"] = 0.6

            else:
                # Pesos por defecto mientras no se optimiza
                pesos_conf = {"kalman":1.0,"hmm":1.5,"particle":0.8,"tecnico":1.2,"fundamental":0.6}
                st.info("💡 Pulsa **Optimizar pesos automáticamente** para que el sistema aprenda "
                        "los mejores pesos para este ticker con datos históricos reales.")

        else:  # Manual
            cw1, cw2, cw3, cw4, cw5 = st.columns(5)
            w_kalman = cw1.slider("Kalman",      0.0, 2.0, 1.0, 0.1, key="w_k")
            w_hmm    = cw2.slider("HMM Ens.",    0.0, 2.0, 1.5, 0.1, key="w_h")
            w_pf     = cw3.slider("Part.Filter", 0.0, 2.0, 1.0, 0.1, key="w_pf")
            w_tec    = cw4.slider("Técnico",     0.0, 2.0, 1.2, 0.1, key="w_t")
            w_fund   = cw5.slider("Fundamental", 0.0, 2.0, 0.8, 0.1, key="w_f")
            pesos_conf = {
                "kalman": w_kalman, "hmm": w_hmm, "particle": w_pf,
                "tecnico": w_tec,   "fundamental": w_fund,
            }

    if not motor_ticker:
        st.markdown("""
        <div style='background:#0e0e1e;border:1px solid #1c1c30;border-radius:14px;
                    padding:48px;text-align:center;margin-top:20px'>
            <div style='font-size:36px'>🎯</div>
            <div style='font-size:16px;font-weight:700;margin-top:12px'>
                Escribe o selecciona un ticker para analizar
            </div>
            <div style='color:#444466;font-size:13px;margin-top:8px'>
                El motor ejecuta todos los modelos simultáneamente y produce<br>
                una probabilidad unificada + tamaño de posición óptimo
            </div>
        </div>
        """, unsafe_allow_html=True)

    else:
        with st.spinner(f"Ejecutando motor completo para {motor_ticker}…"):
            t_start = __import__('time').time()

            serie_m = get_historico(motor_ticker, "2y")
            if serie_m is None:
                serie_m = get_historico(motor_ticker+".MX", "2y")
                if serie_m: motor_ticker += ".MX"

            if serie_m is None or len(serie_m) < 60:
                st.error(f"No se pudo obtener datos para {motor_ticker}.")
            else:
                np.random.seed(42)
                errores = []

                # ── Ejecutar todas las señales ──
                try:    s_kal, kalman_est, precio_act = señal_kalman(serie_m)
                except: s_kal, kalman_est, precio_act = 0.0, 0.0, float(serie_m.iloc[-1]); errores.append("Kalman")

                try:    s_hmm, conf_hmm = señal_hmm_ensemble(serie_m)
                except: s_hmm, conf_hmm = 0.0, 0.0; errores.append("HMM")

                try:    s_pf, pf_est = señal_particle_filter(serie_m.iloc[-252:] if len(serie_m)>=252 else serie_m, N=300)
                except: s_pf, pf_est = 0.0, float(serie_m.iloc[-1]); errores.append("Particle Filter")

                try:    s_tec, rsi_v, macd_v = señal_tecnica(serie_m)
                except: s_tec, rsi_v, macd_v = 0.0, 50.0, 0.0; errores.append("Técnico")

                try:    s_fund = señal_fundamental(motor_ticker)
                except: s_fund = 0.0; errores.append("Fundamental")

                try:    var_1d, es_1d = calcular_var_es(serie_m)
                except: var_1d, es_1d = -0.02, -0.03; errores.append("VaR")

                # Régimen HMM para ajuste de posición
                try:
                    estados_m, _ = hmm_regimen(serie_m.iloc[-252:] if len(serie_m)>=252 else serie_m)
                    regimen_actual = int(estados_m[-1]) if estados_m is not None else 1
                except:
                    regimen_actual = 1

                # Kelly básico
                ret_m = serie_m.pct_change().dropna().astype(float)
                wins_m = ret_m[ret_m>0]; losses_m = ret_m[ret_m<0]
                if len(wins_m)>0 and len(losses_m)>0:
                    p_m = len(wins_m)/len(ret_m)
                    b_m = wins_m.mean()/abs(losses_m.mean()) if losses_m.mean()!=0 else 1
                    kelly_base = max(0.0, min((b_m*p_m-(1-p_m))/b_m, 0.5))
                else:
                    kelly_base = 0.1

                scores_input = {
                    "kalman": s_kal, "hmm": s_hmm, "particle": s_pf,
                    "tecnico": s_tec, "fundamental": s_fund,
                }

                resultado = motor_decision_unificado(
                    scores_input, pesos_conf, motor_capital,
                    kelly_base, var_1d, regimen_actual
                )
                t_elapsed = __import__('time').time() - t_start

                # ════════════════════════════════════
                #  PANEL PRINCIPAL — Decisión
                # ════════════════════════════════════
                prob_pct  = resultado["prob"] * 100
                color_dec = resultado["color"]
                barra_prob = int(prob_pct)

                st.markdown(f"""
                <div style='background:{color_dec}0d;border:2px solid {color_dec}44;
                            border-radius:18px;padding:28px 32px;margin:16px 0'>
                    <div style='display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:20px'>
                        <div>
                            <div style='font-size:11px;letter-spacing:3px;color:#444466;
                                        font-family:JetBrains Mono;text-transform:uppercase;
                                        margin-bottom:8px'>DECISIÓN — {motor_ticker}</div>
                            <div style='font-size:42px;font-weight:800;color:{color_dec};
                                        letter-spacing:-1px;line-height:1'>
                                {resultado["decision"]}
                            </div>
                            <div style='margin-top:16px;background:#ffffff0a;border-radius:8px;
                                        height:12px;overflow:hidden;width:300px'>
                                <div style='width:{barra_prob}%;height:100%;
                                            background:linear-gradient(90deg,#ff4466,#f59e0b,#00ff9d);
                                            border-radius:8px;transition:width 0.5s'></div>
                            </div>
                            <div style='font-family:JetBrains Mono;font-size:11px;
                                        color:#666;margin-top:4px;display:flex;justify-content:space-between;width:300px'>
                                <span>VENDER 0%</span><span>NEUTRAL 50%</span><span>COMPRAR 100%</span>
                            </div>
                        </div>
                        <div style='text-align:right'>
                            <div style='font-size:11px;color:#444466;font-family:JetBrains Mono;
                                        letter-spacing:2px;margin-bottom:4px'>PROBABILIDAD</div>
                            <div style='font-size:52px;font-weight:800;color:{color_dec};
                                        font-family:JetBrains Mono;line-height:1'>
                                {prob_pct:.1f}%
                            </div>
                            <div style='font-size:12px;color:#666;margin-top:4px;font-family:JetBrains Mono'>
                                Score unificado: {resultado["score"]:+.3f}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # ── Capital recomendado ──
                sim_color = "#00ff9d" if resultado["capital_rec"] > 0 else "#888"
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("💰 Capital recomendado", f"${resultado['capital_rec']:,.0f}",
                          f"{resultado['kelly_adj']*100:.1f}% del portafolio")
                c2.metric("📉 VaR diario (95%)",    f"{var_1d*100:.2f}%",
                          f"ES: {es_1d*100:.2f}%")
                c3.metric(f"🧬 Régimen {nombre_regimen(regimen_actual)}",
                          f"Factor {resultado['factor_reg']:.0%}")
                c4.metric("⚡ Tiempo análisis", f"{t_elapsed:.1f}s",
                          f"{'⚠️ errores' if errores else '✅ completo'}")

                # ════════════════════════════════════
                #  DESGLOSE DE SEÑALES
                # ════════════════════════════════════
                st.markdown("<div class='label-tag' style='margin-top:16px'>Desglose de señales</div>",
                            unsafe_allow_html=True)

                señales_info = [
                    ("🌊 Kalman Filter",    s_kal,  w_kalman, f"Tendencia: ${kalman_est:,.2f} | Precio: ${precio_act:,.2f}"),
                    ("🧬 HMM Ensemble",     s_hmm,  w_hmm,   f"Régimen: {nombre_regimen(regimen_actual)} | Confianza: {conf_hmm*100:.0f}%"),
                    ("🌀 Particle Filter",  s_pf,   w_pf,    f"Estimado: ${pf_est:,.2f} | Precio: ${precio_act:,.2f}"),
                    ("🔬 Análisis Técnico", s_tec,  w_tec,   f"RSI: {rsi_v:.1f} | MACD hist: {macd_v:.4f}"),
                    ("📋 Fundamental",      s_fund, w_fund,  f"Score fundamental: {s_fund:+.3f}"),
                ]

                for nombre_s, score_s, peso_s, detalle_s in señales_info:
                    barra_s    = int((score_s + 1) / 2 * 100)  # 0-100
                    color_s    = "#00ff9d" if score_s > 0.2 else "#ff4466" if score_s < -0.2 else "#f59e0b"
                    contrib    = score_s * peso_s
                    is_error_s = any(e.lower() in nombre_s.lower() for e in errores)

                    st.markdown(f"""
                    <div style='background:#0a0a16;border:1px solid #1c1c30;border-radius:10px;
                                padding:12px 16px;margin-bottom:8px'>
                        <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>
                            <div>
                                <span style='font-weight:700;font-size:14px'>{nombre_s}</span>
                                {"<span style='color:#ff4466;font-size:10px;margin-left:8px;font-family:JetBrains Mono'>ERROR</span>" if is_error_s else ""}
                                <div style='font-size:11px;color:#666;font-family:JetBrains Mono;margin-top:2px'>
                                    {detalle_s}
                                </div>
                            </div>
                            <div style='text-align:right'>
                                <div style='font-family:JetBrains Mono;font-size:18px;
                                            font-weight:700;color:{color_s}'>{score_s:+.3f}</div>
                                <div style='font-size:10px;color:#444466;font-family:JetBrains Mono'>
                                    peso: {peso_s:.1f} · contrib: {contrib:+.3f}
                                </div>
                            </div>
                        </div>
                        <div style='background:#ffffff0a;border-radius:4px;height:6px;overflow:hidden;position:relative'>
                            <div style='position:absolute;left:50%;top:0;width:1px;height:100%;background:#2a2a44'></div>
                            <div style='width:{barra_s}%;height:100%;background:{color_s};border-radius:4px'></div>
                        </div>
                        <div style='display:flex;justify-content:space-between;
                                    font-family:JetBrains Mono;font-size:9px;color:#333;margin-top:2px'>
                            <span>BAJISTA -1</span><span>NEUTRAL 0</span><span>ALCISTA +1</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                # ════════════════════════════════════
                #  MONTE CARLO
                # ════════════════════════════════════
                st.markdown("<div class='label-tag' style='margin-top:16px'>Monte Carlo — 1000 escenarios (30 días)</div>",
                            unsafe_allow_html=True)

                with st.spinner("Simulando 1000 escenarios…"):
                    sims_mc, vals_finales, p_act_mc = montecarlo_portfolio(
                        serie_m, motor_capital, n_sim=1000, horizonte=30
                    )

                p5   = float(np.percentile(vals_finales, 5))
                p25  = float(np.percentile(vals_finales, 25))
                p50  = float(np.percentile(vals_finales, 50))
                p75  = float(np.percentile(vals_finales, 75))
                p95  = float(np.percentile(vals_finales, 95))
                prob_ganancia = float((vals_finales > motor_capital).mean() * 100)

                c1,c2,c3,c4,c5 = st.columns(5)
                c1.metric("😱 Peor 5%",   f"${p5:,.0f}",  f"{(p5/motor_capital-1)*100:+.1f}%")
                c2.metric("📉 P25",        f"${p25:,.0f}", f"{(p25/motor_capital-1)*100:+.1f}%")
                c3.metric("📊 Mediana",    f"${p50:,.0f}", f"{(p50/motor_capital-1)*100:+.1f}%")
                c4.metric("📈 P75",        f"${p75:,.0f}", f"{(p75/motor_capital-1)*100:+.1f}%")
                c5.metric("🚀 Mejor 5%",   f"${p95:,.0f}", f"{(p95/motor_capital-1)*100:+.1f}%")

                # Gráfica Monte Carlo
                fig_mc = go.Figure()

                # Muestra 200 trayectorias individuales
                fechas_mc = pd.date_range(start=serie_m.index[-1], periods=31, freq='B')[1:]
                for i in range(0, min(200, len(sims_mc)), 1):
                    vals_i = sims_mc[i] * (motor_capital / p_act_mc)
                    color_tr = "rgba(0,255,157,0.04)" if vals_i[-1] > motor_capital \
                               else "rgba(255,68,102,0.04)"
                    fig_mc.add_trace(go.Scatter(
                        x=fechas_mc, y=vals_i,
                        line=dict(width=0.5, color=color_tr),
                        showlegend=False, hoverinfo="skip",
                    ))

                # Bandas de percentil
                p5_ts  = np.percentile(sims_mc, 5, axis=0)  * (motor_capital/p_act_mc)
                p95_ts = np.percentile(sims_mc, 95, axis=0) * (motor_capital/p_act_mc)
                p50_ts = np.percentile(sims_mc, 50, axis=0) * (motor_capital/p_act_mc)

                fig_mc.add_trace(go.Scatter(
                    x=list(fechas_mc)+list(fechas_mc[::-1]),
                    y=list(p95_ts)+list(p5_ts[::-1]),
                    fill="toself", fillcolor="rgba(59,130,246,0.12)",
                    line=dict(width=0), name="Banda 5%-95%",
                ))
                fig_mc.add_trace(go.Scatter(
                    x=fechas_mc, y=p50_ts,
                    name="Mediana", line=dict(color="#3b82f6", width=2.5)
                ))
                fig_mc.add_hline(
                    y=motor_capital,
                    line=dict(color="#f59e0b", dash="dash", width=1.5),
                    annotation_text=f"Capital inicial ${motor_capital:,.0f}",
                    annotation_font=dict(color="#f59e0b", size=11),
                )

                color_prob = "#00ff9d" if prob_ganancia>60 else "#f59e0b" if prob_ganancia>45 else "#ff4466"
                fig_mc.update_layout(
                    template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                    font=dict(family="Syne", color="#e8e8f0"),
                    title=f"Monte Carlo 1000 sims · {motor_ticker} · Probabilidad de ganancia: "
                          f"<span style='color:{color_prob}'>{prob_ganancia:.0f}%</span>",
                    height=400, margin=dict(l=16,r=16,t=56,b=16),
                    xaxis=dict(showgrid=False, color="#444466"),
                    yaxis=dict(gridcolor="#1c1c30", color="#444466", tickprefix="$"),
                    legend=dict(bgcolor="#0a0a16", font=dict(family="JetBrains Mono", size=11)),
                    hovermode="x unified",
                )
                st.plotly_chart(fig_mc, use_container_width=True)

                # ════════════════════════════════════
                #  GESTIÓN DE RIESGO PROFESIONAL
                # ════════════════════════════════════
                st.markdown("<div class='label-tag' style='margin-top:8px'>Gestión de riesgo — Stop Loss & Take Profit adaptativos</div>",
                            unsafe_allow_html=True)

                # Calcular stops según régimen y volatilidad
                vol_30d    = float(serie_m.pct_change().dropna().iloc[-30:].std()) if len(serie_m)>30 else 0.02
                stop_mult  = {2: 1.5, 1: 2.0, 0: 3.0}[regimen_actual]   # más amplio en bajista
                tp_mult    = {2: 3.0, 1: 2.0, 0: 1.5}[regimen_actual]   # más conservador en bajista

                stop_loss_pct  = vol_30d * stop_mult * np.sqrt(5)  # 1 semana
                take_profit_pct= vol_30d * tp_mult   * np.sqrt(5)

                stop_precio    = precio_act * (1 - stop_loss_pct)
                tp_precio      = precio_act * (1 + take_profit_pct)
                rr_ratio       = take_profit_pct / stop_loss_pct if stop_loss_pct > 0 else 0

                # Drawdown máximo del portafolio
                if not port.empty:
                    dd_warning = resultado["capital_rec"] / motor_capital > 0.15
                else:
                    dd_warning = False

                c1,c2,c3,c4 = st.columns(4)
                c1.metric("🛑 Stop Loss",      f"${stop_precio:,.2f}", f"-{stop_loss_pct*100:.1f}%")
                c2.metric("🎯 Take Profit",    f"${tp_precio:,.2f}",   f"+{take_profit_pct*100:.1f}%")
                c3.metric("⚖️ Ratio R/R",       f"{rr_ratio:.2f}x",
                          "✅ Favorable" if rr_ratio >= 2 else "⚠️ Revisar")
                c4.metric("🌊 Vol. 30d",        f"{vol_30d*100:.2f}%/día",
                          f"Régimen: {nombre_regimen(regimen_actual)}")

                # Límite de drawdown del portafolio
                st.markdown(f"""
                <div style='background:{"#ff446611" if dd_warning else "#0e0e1e"};
                            border:1px solid {"#ff444644" if dd_warning else "#1c1c30"};
                            border-left:4px solid {"#ff4466" if dd_warning else "#00ff9d"};
                            border-radius:10px;padding:14px 18px;margin-top:8px'>
                    <div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px'>
                        <div>
                            <div style='font-weight:700;font-size:14px'>
                                {"⚠️ Exposición alta — considera reducir posición" if dd_warning else "✅ Exposición dentro del límite de riesgo"}
                            </div>
                            <div style='font-size:12px;color:#888;font-family:JetBrains Mono;margin-top:4px'>
                                Capital recomendado: ${resultado["capital_rec"]:,.0f}
                                ({resultado["kelly_adj"]*100:.1f}% del total)
                                &nbsp;·&nbsp; VaR diario: {var_1d*100:.2f}%
                                &nbsp;·&nbsp; Expected Shortfall: {es_1d*100:.2f}%
                            </div>
                        </div>
                        <div style='font-family:JetBrains Mono;font-size:22px;
                                    font-weight:700;color:{resultado["color"]}'>
                            {resultado["prob"]*100:.1f}% prob.
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # ── Audio TTS del motor ──
                texto_motor = (
                    f"Motor de decisión para {motor_ticker}. "
                    f"Decisión: {resultado['decision'].split(' ',1)[1] if ' ' in resultado['decision'] else resultado['decision']}. "
                    f"Probabilidad de compra: {prob_pct:.0f} por ciento. "
                    f"Régimen de mercado actual: {nombre_regimen(regimen_actual)}. "
                    f"Capital recomendado: {resultado['kelly_adj']*100:.0f} por ciento del portafolio, "
                    f"equivalente a {resultado['capital_rec']:,.0f} dólares. "
                    f"Stop loss en {stop_loss_pct*100:.1f} por ciento. "
                    f"Take profit en {take_profit_pct*100:.1f} por ciento. "
                    f"Ratio riesgo-recompensa: {rr_ratio:.1f}. "
                    f"Probabilidad de ganancia según Monte Carlo: {prob_ganancia:.0f} por ciento en 30 días."
                )
                st.components.v1.html(audio_tts_html(texto_motor), height=60)

# ═══════════════════════════════════════════════════════════
#  🔬 VALIDACIÓN PRO
#  Walk-forward del motor completo · Optimización de pesos
#  Drawdown controls · Portfolio sizing con correlaciones
# ═══════════════════════════════════════════════════════════
elif st.session_state.vista == "validacion":

    st.markdown("""
    <div style='padding:28px 0 8px'>
        <div class='label-tag'>VALIDACIÓN RIGUROSA DEL SISTEMA</div>
        <div style='font-size:28px;font-weight:800;letter-spacing:-0.5px'>🔬 Validación Pro</div>
        <div style='color:#666;font-size:13px;margin-top:6px'>
            Walk-Forward del Motor Completo · Optimización Automática de Pesos ·
            Drawdown Controls · Portfolio Sizing con Correlaciones
        </div>
    </div>
    """, unsafe_allow_html=True)

    port_v = st.session_state.portfolio.reset_index(drop=True)
    tickers_v = port_v["Ticker"].tolist() if not port_v.empty else []

    tab_wf, tab_opt, tab_dd, tab_ps = st.tabs([
        "📊 Walk-Forward Motor",
        "🧬 Optimización de Pesos",
        "🛡️ Drawdown Controls",
        "📐 Portfolio Sizing",
    ])

    # ─────────────────────────────────────────────────────
    #  FUNCIONES COMPARTIDAS
    # ─────────────────────────────────────────────────────

    def score_motor_rapido(serie, pesos):
        """
        Versión vectorizada del motor: calcula score combinado para
        una ventana de datos. Omite Fundamental (lento) en backtesting.
        Retorna score ∈ [-1, 1]
        """
        try:
            # Kalman
            p = serie.astype(float).values
            xhat, P, Q, R = p[0], 1.0, 1e-5, 0.01**2
            for pp in p:
                Pm=P+Q; K=Pm/(Pm+R); xhat=xhat+K*(pp-xhat); P=(1-K)*Pm
            s_kal = float(np.clip(-((p[-1]-xhat)/xhat*100)/5, -1, 1))
        except: s_kal = 0.0

        try:
            # Técnico
            close = serie.astype(float)
            rsi_s = calcular_rsi(close)
            _, _, hist_s = calcular_macd(close)
            rsi_v  = float(rsi_s.iloc[-1])  if not np.isnan(rsi_s.iloc[-1])  else 50
            hist_v = float(hist_s.iloc[-1]) if not np.isnan(hist_s.iloc[-1]) else 0
            bb_u, _, bb_l = calcular_bollinger(close)
            pv = float(close.iloc[-1])
            bu = float(bb_u.iloc[-1]) if not np.isnan(bb_u.iloc[-1]) else pv*1.02
            bl = float(bb_l.iloc[-1]) if not np.isnan(bb_l.iloc[-1]) else pv*0.98
            sc = (50-rsi_v)/50*0.4 + np.sign(hist_v)*0.3
            if pv < bl: sc += 0.3
            elif pv > bu: sc -= 0.3
            s_tec = float(np.clip(sc, -1, 1))
        except: s_tec = 0.0

        try:
            # HMM ligero (solo 30 iteraciones para velocidad)
            estados_r, _ = hmm_regimen(serie, n_iter=30)
            if estados_r is not None:
                estado_r = int(estados_r[-1])
                s_hmm = float((estado_r - 1.0) * 0.7)
            else:
                s_hmm = 0.0
        except: s_hmm = 0.0

        # Score ponderado
        w_tot = pesos["kalman"] + pesos["tecnico"] + pesos["hmm"]
        if w_tot == 0: return 0.0
        score = (s_kal*pesos["kalman"] + s_tec*pesos["tecnico"] + s_hmm*pesos["hmm"]) / w_tot
        return float(np.clip(score, -1, 1))

    def ejecutar_motor_en_ventana(serie_tr, serie_te, pesos, capital,
                                   umbral_compra=0.60, umbral_venta=0.40,
                                   stop_pct=0.07, tp_pct=0.12):
        """
        Ejecuta el motor completo en una ventana test.
        Señales generadas mirando solo datos de train (sin lookahead).
        """
        pos = 0; cap = capital; acc = 0; precio_entrada = None
        vals = [capital]; trades_n = 0; wins = 0; max_val = capital

        for j in range(len(serie_te)):
            # Ventana expandida: train + lo visto hasta j
            serie_vista = pd.concat([serie_tr, serie_te.iloc[:j+1]])
            p = float(serie_te.iloc[j])

            if j % 5 == 0:  # recalcular señal cada 5 días (eficiencia)
                score = score_motor_rapido(serie_vista.iloc[-120:], pesos)
                prob  = 1/(1+np.exp(-score*4))
            else:
                prob = prob  # mantener la última

            val_actual = cap + acc*p
            max_val    = max(max_val, val_actual)

            # Stop loss / take profit dinámicos
            if pos == 1 and precio_entrada:
                ret_pos = (p - precio_entrada) / precio_entrada
                if ret_pos <= -stop_pct or ret_pos >= tp_pct:
                    ganancia = p - precio_entrada
                    if ganancia > 0: wins += 1
                    cap = acc*p; acc = 0; pos = 0; precio_entrada = None

            # Señal de compra
            if pos == 0 and prob >= umbral_compra and cap > 0:
                acc = cap/p; cap = 0; pos = 1
                precio_entrada = p; trades_n += 1

            # Señal de venta
            elif pos == 1 and prob <= umbral_venta:
                ganancia = p - (precio_entrada or p)
                if ganancia > 0: wins += 1
                cap = acc*p; acc = 0; pos = 0; precio_entrada = None
                trades_n += 1

            vals.append(cap + acc*p)

        if pos == 1: cap = acc*float(serie_te.iloc[-1])
        final = cap
        ret   = (final/capital - 1) * 100
        bnh   = (float(serie_te.iloc[-1])/float(serie_te.iloc[0]) - 1) * 100

        s = pd.Series(vals)
        dr = s.pct_change().dropna()
        sharpe  = float(dr.mean()/dr.std()*np.sqrt(252)) if dr.std()>0 else 0
        maxdd   = float(((s/s.cummax())-1).min()*100)
        calmar  = abs(ret/maxdd) if maxdd != 0 else 0
        wr      = (wins/trades_n*100) if trades_n > 0 else 0
        var_95  = float(np.percentile(dr, 5)) if len(dr)>0 else -0.02
        es_95   = float(dr[dr<=var_95].mean()) if len(dr[dr<=var_95])>0 else var_95

        return {
            "ret": round(ret,2), "bnh": round(bnh,2),
            "sharpe": round(sharpe,3), "calmar": round(calmar,3),
            "maxdd": round(maxdd,2), "wr": round(wr,1),
            "n_trades": trades_n, "var_95": round(var_95*100,2),
            "es_95": round(es_95*100,2), "vals": vals,
        }

    # ─────────────────────────────────────────
    #  TAB 1 — WALK-FORWARD DEL MOTOR COMPLETO
    # ─────────────────────────────────────────
    with tab_wf:
        st.markdown("""
        <div style='color:#888;font-size:13px;margin-bottom:16px'>
        Walk-forward sobre el <strong>motor completo</strong> (Kalman+HMM+Técnico),
        no solo RSI+MACD. Mide Sharpe, Calmar, VaR, ES y consistencia real
        a través de múltiples regímenes históricos.
        </div>
        """, unsafe_allow_html=True)

        c1,c2,c3,c4 = st.columns(4)
        wfp_ticker  = c1.text_input("Ticker", value=tickers_v[0] if tickers_v else "SPY", key="wfp_t")
        wfp_train   = c2.selectbox("Ventana train (días)", [60,90,120,180,252], index=2, key="wfp_tr")
        wfp_test    = c3.selectbox("Ventana test (días)",  [15,20,30,45], index=1, key="wfp_te")
        wfp_capital = c4.number_input("Capital $", value=10000.0, step=1000.0, key="wfp_c")

        c5,c6,c7 = st.columns(3)
        wfp_stop   = c5.slider("Stop Loss %", 2.0, 15.0, 7.0, 0.5, key="wfp_sl") / 100
        wfp_tp     = c6.slider("Take Profit %", 5.0, 25.0, 12.0, 0.5, key="wfp_tp") / 100
        wfp_umbral = c7.slider("Umbral compra prob.", 0.55, 0.80, 0.62, 0.01, key="wfp_ub")

        pesos_wfp = {"kalman": 1.0, "tecnico": 1.2, "hmm": 1.5}

        if st.button("▶ Ejecutar Walk-Forward Motor Completo", use_container_width=True, key="wfp_run"):
            with st.spinner("Ejecutando walk-forward del motor… (puede tardar 1-2 min)"):
                serie_wfp = get_historico(wfp_ticker, "5y")
                if serie_wfp is None or len(serie_wfp) < wfp_train + wfp_test + 10:
                    st.error("Datos insuficientes para walk-forward.")
                else:
                    resultados_wfp = []
                    n_wfp  = len(serie_wfp)
                    start  = wfp_train
                    prog   = st.progress(0)
                    total_v= max(1, (n_wfp - wfp_train) // wfp_test)
                    vi     = 0

                    while start + wfp_test <= n_wfp:
                        tr = serie_wfp.iloc[start-wfp_train:start]
                        te = serie_wfp.iloc[start:start+wfp_test]
                        r  = ejecutar_motor_en_ventana(
                            tr, te, pesos_wfp, wfp_capital,
                            umbral_compra=wfp_umbral,
                            umbral_venta=1-wfp_umbral,
                            stop_pct=wfp_stop, tp_pct=wfp_tp
                        )
                        r["fecha"] = str(te.index[0].date())
                        r["fecha_fin"] = str(te.index[-1].date())

                        # Detectar régimen de la ventana train
                        try:
                            est_r, _ = hmm_regimen(tr, n_iter=20)
                            r["regimen"] = nombre_regimen(int(est_r[-1])) if est_r is not None else "?"
                        except:
                            r["regimen"] = "?"

                        resultados_wfp.append(r)
                        start += wfp_test
                        vi += 1
                        prog.progress(min(vi/total_v, 1.0))

                    prog.empty()
                    df_wfp = pd.DataFrame(resultados_wfp)

                    # ── Métricas globales ──
                    n_tot   = len(df_wfp)
                    n_beat  = (df_wfp["ret"] > df_wfp["bnh"]).sum()
                    n_pos   = (df_wfp["ret"] > 0).sum()
                    sharpe_m= df_wfp["sharpe"].mean()
                    calmar_m= df_wfp["calmar"].mean()
                    wr_m    = df_wfp["wr"].mean()
                    dd_m    = df_wfp["maxdd"].mean()
                    var_m   = df_wfp["var_95"].mean()
                    es_m    = df_wfp["es_95"].mean()
                    ret_m   = df_wfp["ret"].mean()
                    ret_std = df_wfp["ret"].std()
                    consistencia = n_pos/n_tot*100 if n_tot>0 else 0

                    pct_beat = n_beat/n_tot*100 if n_tot>0 else 0
                    color_v  = "#00ff9d" if pct_beat>=60 else "#f59e0b" if pct_beat>=45 else "#ff4466"
                    veredicto= ("✅ MOTOR ROBUSTO" if pct_beat>=60 and sharpe_m>0.5
                                else "⚠️ MOTOR MIXTO" if pct_beat>=45
                                else "❌ MOTOR DÉBIL")

                    st.markdown(f"""
                    <div style='background:{color_v}11;border:2px solid {color_v}44;
                                border-radius:16px;padding:24px 28px;margin:16px 0'>
                        <div style='font-size:24px;font-weight:800;color:{color_v};margin-bottom:16px'>
                            {veredicto}
                        </div>
                        <div style='display:flex;gap:28px;flex-wrap:wrap;font-family:JetBrains Mono'>
                        {''.join([f"""
                        <div>
                            <div style='font-size:9px;color:#444466;letter-spacing:2px;text-transform:uppercase'>{lbl}</div>
                            <div style='font-size:19px;font-weight:700;color:{cl}'>{val}</div>
                        </div>""" for lbl,val,cl in [
                            ("Supera B&H", f"{n_beat}/{n_tot} ({pct_beat:.0f}%)", color_v),
                            ("Consistencia", f"{consistencia:.0f}%", "#00ff9d" if consistencia>60 else "#f59e0b"),
                            ("Sharpe medio", f"{sharpe_m:.3f}", "#00ff9d" if sharpe_m>0.8 else "#f59e0b" if sharpe_m>0 else "#ff4466"),
                            ("Calmar ratio", f"{calmar_m:.3f}", "#00ff9d" if calmar_m>0.5 else "#f59e0b"),
                            ("Win rate", f"{wr_m:.1f}%", "#00ff9d" if wr_m>55 else "#f59e0b" if wr_m>45 else "#ff4466"),
                            ("Max DD medio", f"{dd_m:.1f}%", "#00ff9d" if abs(dd_m)<10 else "#f59e0b" if abs(dd_m)<20 else "#ff4466"),
                            ("VaR 95% medio", f"{var_m:.2f}%", "#00ff9d" if abs(var_m)<2 else "#f59e0b"),
                            ("Ret ± std", f"{ret_m:.1f}±{ret_std:.1f}%", color_v),
                        ]])}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Gráfica retorno por ventana coloreada por régimen
                    reg_colors = {
                        "🐂 ALCISTA": "#00ff9d",
                        "↔️ LATERAL": "#f59e0b",
                        "🐻 BAJISTA": "#ff4466",
                        "?": "#888",
                    }
                    fig_wfp = go.Figure()
                    for reg, rc in reg_colors.items():
                        mask_r = df_wfp["regimen"] == reg
                        if mask_r.any():
                            fig_wfp.add_trace(go.Bar(
                                x=df_wfp[mask_r]["fecha"],
                                y=df_wfp[mask_r]["ret"],
                                name=f"Motor {reg}",
                                marker_color=rc, opacity=0.85,
                            ))
                    fig_wfp.add_trace(go.Scatter(
                        x=df_wfp["fecha"], y=df_wfp["bnh"],
                        name="Buy & Hold", mode="lines+markers",
                        line=dict(color="#ffffff55", width=1.5, dash="dot"),
                        marker=dict(size=4),
                    ))
                    fig_wfp.add_hline(y=0, line=dict(color="#2a2a44", width=1))
                    fig_wfp.update_layout(
                        template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                        font=dict(family="Syne", color="#e8e8f0"),
                        title=f"Retorno por ventana ({wfp_test}d) — coloreado por régimen HMM",
                        height=340, margin=dict(l=16,r=16,t=48,b=16), barmode="stack",
                        xaxis=dict(showgrid=False, color="#444466"),
                        yaxis=dict(gridcolor="#1c1c30", color="#444466", ticksuffix="%"),
                        legend=dict(bgcolor="#0a0a16", font=dict(family="JetBrains Mono", size=11)),
                    )
                    st.plotly_chart(fig_wfp, use_container_width=True)

                    # Sharpe acumulado rolling
                    sharpe_rolling = df_wfp["sharpe"].expanding().mean()
                    fig_sh = go.Figure()
                    fig_sh.add_trace(go.Scatter(
                        x=df_wfp["fecha"], y=sharpe_rolling,
                        name="Sharpe acumulado", fill="tozeroy",
                        line=dict(color="#00ff9d", width=2),
                        fillcolor="rgba(0,255,157,0.06)",
                    ))
                    fig_sh.add_hline(y=1.0, line=dict(color="#f59e0b", dash="dash", width=1),
                                     annotation_text="Sharpe=1 (bueno)")
                    fig_sh.add_hline(y=0.0, line=dict(color="#ff4466", dash="dash", width=1))
                    fig_sh.update_layout(
                        template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                        title="Sharpe ratio acumulado — estabilidad del motor",
                        height=240, margin=dict(l=16,r=16,t=48,b=16), font=dict(family="Syne"),
                        xaxis=dict(showgrid=False, color="#444466"),
                        yaxis=dict(gridcolor="#1c1c30", color="#444466"),
                    )
                    st.plotly_chart(fig_sh, use_container_width=True)

    # ─────────────────────────────────────────
    #  TAB 2 — OPTIMIZACIÓN AUTOMÁTICA DE PESOS
    # ─────────────────────────────────────────
    with tab_opt:
        st.markdown("""
        <div style='color:#888;font-size:13px;margin-bottom:16px'>
        En vez de ajustar pesos manualmente, el sistema busca automáticamente
        la combinación que maximiza el Sharpe ratio out-of-sample.
        Usa búsqueda en grid sobre el espacio de pesos.
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        opt_ticker  = c1.text_input("Ticker", value=tickers_v[0] if tickers_v else "SPY", key="opt_t")
        opt_capital = c2.number_input("Capital $", value=10000.0, step=1000.0, key="opt_c")
        opt_metric  = c3.selectbox("Optimizar por", ["Sharpe", "Calmar", "Retorno - Drawdown"], key="opt_m")

        if st.button("🔍 Buscar pesos óptimos automáticamente", use_container_width=True, key="opt_run"):
            with st.spinner("Explorando espacio de pesos… puede tardar 1-2 min…"):
                serie_opt = get_historico(opt_ticker, "3y")
                if serie_opt is None or len(serie_opt) < 200:
                    st.error("Datos insuficientes.")
                else:
                    # Dividir: 60% in-sample (optimización), 40% out-of-sample (validación)
                    corte    = int(len(serie_opt) * 0.60)
                    serie_is = serie_opt.iloc[:corte]
                    serie_os = serie_opt.iloc[corte:]

                    # Grid de pesos — 3 valores por señal = 27 combinaciones
                    grid = [0.5, 1.0, 1.5]
                    mejores_pesos = None
                    mejor_score_is= -999
                    resultados_grid = []

                    prog_opt = st.progress(0)
                    total_comb = len(grid)**3
                    ci_opt = 0

                    for w_k in grid:
                        for w_t in grid:
                            for w_h in grid:
                                pesos_g = {"kalman": w_k, "tecnico": w_t, "hmm": w_h}
                                # Evaluar in-sample con ventana simple
                                n_is = len(serie_is)
                                train_is = serie_is.iloc[:n_is//2]
                                test_is  = serie_is.iloc[n_is//2:]
                                try:
                                    res_is = ejecutar_motor_en_ventana(
                                        train_is, test_is, pesos_g, opt_capital
                                    )
                                    if opt_metric == "Sharpe":
                                        metric_val = res_is["sharpe"]
                                    elif opt_metric == "Calmar":
                                        metric_val = res_is["calmar"]
                                    else:
                                        metric_val = res_is["ret"] - abs(res_is["maxdd"])
                                except:
                                    metric_val = -999

                                resultados_grid.append({
                                    "w_kalman": w_k, "w_tecnico": w_t, "w_hmm": w_h,
                                    "metric_is": round(metric_val, 3),
                                })
                                if metric_val > mejor_score_is:
                                    mejor_score_is = metric_val
                                    mejores_pesos  = pesos_g.copy()

                                ci_opt += 1
                                prog_opt.progress(ci_opt / total_comb)

                    prog_opt.empty()

                    # Validar los mejores pesos out-of-sample
                    n_os = len(serie_os)
                    train_os = serie_os.iloc[:n_os//2]
                    test_os  = serie_os.iloc[n_os//2:]

                    try:
                        res_os_best = ejecutar_motor_en_ventana(
                            train_os, test_os, mejores_pesos, opt_capital
                        )
                    except:
                        res_os_best = None

                    # Comparar con pesos uniformes
                    pesos_uni = {"kalman": 1.0, "tecnico": 1.0, "hmm": 1.0}
                    try:
                        res_os_uni = ejecutar_motor_en_ventana(
                            train_os, test_os, pesos_uni, opt_capital
                        )
                    except:
                        res_os_uni = None

                    # Resultado principal
                    st.markdown(f"""
                    <div style='background:#00ff9d0a;border:1px solid #00ff9d33;
                                border-radius:14px;padding:22px 26px;margin:16px 0'>
                        <div style='font-size:11px;color:#444466;font-family:JetBrains Mono;
                                    letter-spacing:2px;margin-bottom:8px'>
                            PESOS ÓPTIMOS ENCONTRADOS — {opt_ticker}
                        </div>
                        <div style='display:flex;gap:24px;flex-wrap:wrap;margin-bottom:16px'>
                            {' '.join([f"""<div style='background:#0a0a16;border:1px solid #1c1c30;
                                border-radius:10px;padding:12px 18px;text-align:center'>
                                <div style='font-size:10px;color:#444466;font-family:JetBrains Mono;
                                            letter-spacing:2px'>{lbl}</div>
                                <div style='font-size:24px;font-weight:800;color:#00ff9d;
                                            font-family:JetBrains Mono'>{val:.1f}</div>
                            </div>""" for lbl,val in [
                                ("KALMAN", mejores_pesos["kalman"]),
                                ("TÉCNICO", mejores_pesos["tecnico"]),
                                ("HMM", mejores_pesos["hmm"]),
                            ]])}
                        </div>
                        <div style='font-size:12px;color:#666;font-family:JetBrains Mono'>
                            Optimizados sobre 60% de los datos · Validados en el 40% restante (out-of-sample estricto)
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    if res_os_best and res_os_uni:
                        mejora_sharpe = res_os_best["sharpe"] - res_os_uni["sharpe"]
                        mejora_ret    = res_os_best["ret"]    - res_os_uni["ret"]
                        color_mj = "#00ff9d" if mejora_sharpe > 0 else "#ff4466"

                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("📈 Retorno OOS (óptimo)", f"{res_os_best['ret']:+.2f}%",
                                  f"{mejora_ret:+.2f}% vs uniforme")
                        c2.metric("⚡ Sharpe OOS (óptimo)", f"{res_os_best['sharpe']:.3f}",
                                  f"{mejora_sharpe:+.3f} vs uniforme")
                        c3.metric("📊 Retorno OOS (uniforme)", f"{res_os_uni['ret']:+.2f}%")
                        c4.metric("📉 Max DD OOS", f"{res_os_best['maxdd']:.1f}%")

                        st.markdown(f"""
                        <div style='background:{color_mj}11;border:1px solid {color_mj}33;
                                    border-left:4px solid {color_mj};border-radius:10px;
                                    padding:12px 18px;margin-top:8px;font-size:13px;color:{color_mj}'>
                            {"✅ Los pesos óptimos mejoran al sistema uniforme out-of-sample." if mejora_sharpe>0
                             else "⚠️ Los pesos óptimos no mejoran significativamente. El motor es robusto con pesos iguales."}
                            &nbsp; Sharpe: {res_os_best['sharpe']:.3f} vs {res_os_uni['sharpe']:.3f}
                        </div>
                        """, unsafe_allow_html=True)

                    # Heatmap del grid (fijo w_hmm=mejor)
                    df_grid = pd.DataFrame(resultados_grid)
                    best_h  = mejores_pesos["hmm"]
                    df_grid_h = df_grid[df_grid["w_hmm"] == best_h]
                    pivot = df_grid_h.pivot(index="w_tecnico", columns="w_kalman", values="metric_is")

                    fig_heat = go.Figure(go.Heatmap(
                        z=pivot.values, x=[str(c) for c in pivot.columns],
                        y=[str(i) for i in pivot.index],
                        colorscale=[[0,"#ff4466"],[0.5,"#0e0e1e"],[1,"#00ff9d"]],
                        text=np.round(pivot.values,3), texttemplate="%{text}",
                        textfont=dict(size=12, family="JetBrains Mono"),
                    ))
                    fig_heat.update_layout(
                        template="plotly_dark", paper_bgcolor="#0e0e1e",
                        title=f"Grid de {opt_metric} (w_hmm={best_h}) — in-sample",
                        height=320, margin=dict(l=16,r=16,t=48,b=16),
                        font=dict(family="Syne", color="#e8e8f0"),
                        xaxis_title="w_kalman", yaxis_title="w_tecnico",
                    )
                    st.plotly_chart(fig_heat, use_container_width=True)

    # ─────────────────────────────────────────
    #  TAB 3 — DRAWDOWN CONTROLS
    # ─────────────────────────────────────────
    with tab_dd:
        st.markdown("""
        <div style='color:#888;font-size:13px;margin-bottom:16px'>
        Reglas automáticas de drawdown a nivel portafolio.
        Si el portafolio cae más de X% en un período, se activan
        acciones defensivas: reducir posiciones, mover a cash, alertar.
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        dd_semanal  = c1.slider("Alerta DD semanal %",   3.0, 20.0, 7.0,  0.5, key="dd_s") / 100
        dd_mensual  = c2.slider("Alerta DD mensual %",   5.0, 30.0, 15.0, 1.0, key="dd_m") / 100
        dd_max      = c3.slider("Stop total portafolio %",10.0,40.0, 20.0, 1.0, key="dd_mx") / 100

        st.markdown("<div class='label-tag' style='margin-top:8px'>Estado actual del portafolio</div>",
                    unsafe_allow_html=True)

        if port_v.empty:
            st.info("Agrega acciones a tu portafolio para ver los controles de drawdown.")
        else:
            alertas_dd = []
            total_actual_dd = 0.0
            total_costo_dd  = 0.0
            rows_dd = []

            for i in range(len(port_v)):
                row_dd = port_v.iloc[i]
                stats_dd = motor_avanzado(row_dd["Ticker"])
                compra_dd   = float(row_dd["Compra"])
                cantidad_dd = float(row_dd["Cantidad"])
                costo_dd    = float(row_dd.get("Costo", compra_dd*cantidad_dd))

                if stats_dd:
                    _, actual_dd, _ = stats_dd
                    val_dd  = actual_dd * cantidad_dd
                    rend_dd = (val_dd - costo_dd) / costo_dd * 100 if costo_dd > 0 else 0
                else:
                    actual_dd = compra_dd
                    val_dd    = costo_dd
                    rend_dd   = 0.0

                # Drawdown desde el costo base
                dd_pos = min(0.0, (actual_dd - compra_dd) / compra_dd) if compra_dd > 0 else 0.0
                total_actual_dd += val_dd
                total_costo_dd  += costo_dd

                nivel_alerta = "ok"
                if abs(dd_pos) >= dd_max:    nivel_alerta = "critico"
                elif abs(dd_pos) >= dd_mensual: nivel_alerta = "alto"
                elif abs(dd_pos) >= dd_semanal: nivel_alerta = "medio"

                if nivel_alerta != "ok":
                    alertas_dd.append(row_dd["Ticker"])

                rows_dd.append({
                    "ticker": row_dd["Ticker"],
                    "rend": rend_dd,
                    "dd_pos": dd_pos*100,
                    "val": val_dd,
                    "nivel": nivel_alerta,
                })

            # DD total del portafolio
            dd_total = (total_actual_dd - total_costo_dd) / total_costo_dd * 100 if total_costo_dd > 0 else 0
            dd_total_frac = dd_total / 100

            # Determinar acción del portafolio
            if abs(dd_total_frac) >= dd_max:
                accion_port = "🚨 STOP TOTAL — Reducir todo al mínimo"
                color_port  = "#ff0044"
                reduccion_rec = 0.80
            elif abs(dd_total_frac) >= dd_mensual:
                accion_port = "🔴 DRAWDOWN ALTO — Reducir posiciones 50%"
                color_port  = "#ff4466"
                reduccion_rec = 0.50
            elif abs(dd_total_frac) >= dd_semanal:
                accion_port = "🟡 ALERTA MODERADA — Reducir posiciones 25%"
                color_port  = "#f59e0b"
                reduccion_rec = 0.25
            else:
                accion_port = "✅ PORTAFOLIO DENTRO DE PARÁMETROS"
                color_port  = "#00ff9d"
                reduccion_rec = 0.0

            # Panel de estado
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📊 Valor actual", f"${total_actual_dd:,.2f}")
            c2.metric("💰 Costo base",   f"${total_costo_dd:,.2f}")
            c3.metric("📉 DD total",     f"{dd_total:.2f}%",
                      "⚠️ Por debajo del umbral" if dd_total < -dd_semanal*100 else "✅ Normal")
            c4.metric("🚨 Posiciones en alerta", len(alertas_dd))

            st.markdown(f"""
            <div style='background:{color_port}11;border:2px solid {color_port}44;
                        border-radius:14px;padding:20px 24px;margin:16px 0'>
                <div style='font-size:20px;font-weight:800;color:{color_port};margin-bottom:8px'>
                    {accion_port}
                </div>
                <div style='font-family:JetBrains Mono;font-size:12px;color:#888'>
                    DD portafolio: {dd_total:.2f}%
                    &nbsp;·&nbsp; Umbral semanal: -{dd_semanal*100:.0f}%
                    &nbsp;·&nbsp; Umbral mensual: -{dd_mensual*100:.0f}%
                    &nbsp;·&nbsp; Stop total: -{dd_max*100:.0f}%
                    {f"<br><br>⚡ Acción recomendada: reducir {reduccion_rec*100:.0f}% de cada posición" if reduccion_rec > 0 else ""}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Cards por posición
            st.markdown("<div class='label-tag'>Estado por posición</div>", unsafe_allow_html=True)
            color_nivel = {"ok":"#00ff9d","medio":"#f59e0b","alto":"#ff4466","critico":"#ff0044"}
            icono_nivel = {"ok":"✅","medio":"⚠️","alto":"🔴","critico":"🚨"}
            accion_nivel= {
                "ok":      "Mantener",
                "medio":   f"Reducir {dd_semanal*100:.0f}%",
                "alto":    f"Reducir {dd_mensual*100:.0f}%",
                "critico": "Cerrar posición",
            }

            cols_dd = st.columns(3)
            for ci, r_dd in enumerate(rows_dd):
                c_dd = color_nivel[r_dd["nivel"]]
                with cols_dd[ci % 3]:
                    st.markdown(f"""
                    <div style='background:{c_dd}0d;border:1px solid {c_dd}44;
                                border-radius:12px;padding:14px;margin-bottom:10px;text-align:center'>
                        <div style='font-weight:800;font-size:16px'>{r_dd["ticker"]}</div>
                        <div style='font-family:JetBrains Mono;font-size:18px;font-weight:700;
                                    color:{c_dd};margin:6px 0'>
                            {r_dd["rend"]:+.1f}%
                        </div>
                        <div style='font-size:11px;color:#666;font-family:JetBrains Mono'>
                            DD pos: {r_dd["dd_pos"]:.1f}%
                        </div>
                        <div style='margin-top:8px;font-size:12px;font-weight:700;color:{c_dd}'>
                            {icono_nivel[r_dd["nivel"]]} {accion_nivel[r_dd["nivel"]]}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            # Reglas de drawdown aplicadas históricamente
            st.markdown("<div class='label-tag' style='margin-top:16px'>Simulación: ¿cuánto hubiera protegido esta regla?</div>",
                        unsafe_allow_html=True)
            dd_sim_ticker = st.selectbox("Simular en:", ["SPY","QQQ"] + tickers_v, key="dd_sim_t")
            if st.button("▶ Simular reglas de drawdown", use_container_width=True, key="dd_sim_run"):
                with st.spinner("Simulando…"):
                    serie_dds = get_historico(dd_sim_ticker, "3y")
                    if serie_dds is None:
                        st.error("Sin datos.")
                    else:
                        # Estrategia con reglas vs Buy & Hold
                        cap_dd  = 10000.0; cap_bnh = 10000.0
                        precio0 = float(serie_dds.iloc[0])
                        acc_dd  = cap_dd / precio0; cap_libre = 0.0
                        modo    = "invertido"  # o "cash"
                        vals_dd = [cap_dd]; vals_bnh = [cap_bnh]
                        peak_dd = cap_dd

                        for j in range(1, len(serie_dds)):
                            p_j = float(serie_dds.iloc[j])
                            # BnH
                            cap_bnh = 10000.0 * p_j / precio0
                            # Con reglas
                            val_j = acc_dd*p_j + cap_libre
                            peak_dd = max(peak_dd, val_j)
                            dd_j = (val_j - peak_dd) / peak_dd

                            if dd_j <= -dd_max and modo == "invertido":
                                # Stop total: vender todo
                                cap_libre = acc_dd*p_j; acc_dd = 0; modo = "cash"
                            elif dd_j <= -dd_mensual and modo == "invertido":
                                # Reducir 50%
                                cap_libre += acc_dd*0.5*p_j; acc_dd *= 0.5
                            elif modo == "cash" and dd_j > -dd_semanal*0.5:
                                # Reentrar cuando mejore
                                acc_dd = (cap_libre + acc_dd*p_j) / p_j
                                cap_libre = 0; modo = "invertido"

                            vals_dd.append(acc_dd*p_j + cap_libre)
                            vals_bnh.append(cap_bnh)

                        ret_dd  = (vals_dd[-1]/10000-1)*100
                        ret_bnh = (vals_bnh[-1]/10000-1)*100
                        dd_max_sim_dd  = float(((pd.Series(vals_dd)/pd.Series(vals_dd).cummax())-1).min()*100)
                        dd_max_sim_bnh = float(((pd.Series(vals_bnh)/pd.Series(vals_bnh).cummax())-1).min()*100)

                        c1,c2,c3,c4 = st.columns(4)
                        c1.metric("Con reglas DD", f"{ret_dd:+.1f}%")
                        c2.metric("Buy & Hold",    f"{ret_bnh:+.1f}%")
                        c3.metric("Max DD (con reglas)", f"{dd_max_sim_dd:.1f}%")
                        c4.metric("Max DD (B&H)",        f"{dd_max_sim_bnh:.1f}%")

                        fig_dds = go.Figure()
                        fig_dds.add_trace(go.Scatter(
                            x=serie_dds.index, y=vals_dd,
                            name=f"Con reglas DD ({ret_dd:+.1f}%)",
                            line=dict(color="#00ff9d", width=2),
                            fill="tozeroy", fillcolor="rgba(0,255,157,0.05)"
                        ))
                        fig_dds.add_trace(go.Scatter(
                            x=serie_dds.index, y=vals_bnh,
                            name=f"Buy & Hold ({ret_bnh:+.1f}%)",
                            line=dict(color="#f59e0b", width=1.5, dash="dot")
                        ))
                        fig_dds.update_layout(
                            template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                            title=f"Reglas de drawdown en {dd_sim_ticker} — 3 años",
                            height=320, font=dict(family="Syne", color="#e8e8f0"),
                            margin=dict(l=16,r=16,t=48,b=16), hovermode="x unified",
                            xaxis=dict(showgrid=False, color="#444466"),
                            yaxis=dict(gridcolor="#1c1c30", color="#444466", tickprefix="$"),
                            legend=dict(bgcolor="#0a0a16", font=dict(family="JetBrains Mono", size=11)),
                        )
                        st.plotly_chart(fig_dds, use_container_width=True)

    # ─────────────────────────────────────────
    #  TAB 4 — PORTFOLIO SIZING CON CORRELACIONES
    # ─────────────────────────────────────────
    with tab_ps:
        st.markdown("""
        <div style='color:#888;font-size:13px;margin-bottom:16px'>
        Position sizing que considera la correlación total del portafolio.
        Calcula la contribución marginal al riesgo de cada posición (MCTR),
        el VaR y Expected Shortfall del portafolio completo, y recomienda
        pesos óptimos vía mínima varianza.
        </div>
        """, unsafe_allow_html=True)

        ps_capital = st.number_input("Capital total $", value=10000.0, step=500.0, key="ps_cap")
        ps_period  = st.select_slider("Periodo histórico", ["6mo","1y","2y"], value="1y", key="ps_per")

        tickers_ps = tickers_v.copy()
        extra_ps = st.text_input("Agregar tickers (separados por coma)", key="ps_extra")
        if extra_ps.strip():
            for tk in extra_ps.split(","):
                tk = tk.strip().upper()
                if tk and tk not in tickers_ps:
                    tickers_ps.append(tk)

        if len(tickers_ps) < 2:
            st.info("Necesitas al menos 2 activos. Agrega al portafolio o escribe tickers arriba.")
        elif st.button("▶ Calcular Portfolio Sizing Completo", use_container_width=True, key="ps_run"):
            with st.spinner("Calculando matriz de covarianza, VaR, ES y pesos óptimos…"):
                series_ps = {}
                for tk in tickers_ps:
                    s = get_historico(tk, ps_period)
                    if s is not None and len(s) > 30:
                        series_ps[tk] = s

                if len(series_ps) < 2:
                    st.error("No se pudo obtener datos de al menos 2 activos.")
                else:
                    df_ps   = pd.DataFrame(series_ps).dropna()
                    ret_ps  = df_ps.pct_change().dropna()
                    n_assets= len(series_ps)
                    tks     = list(series_ps.keys())

                    # Matriz de covarianza anualizada
                    cov_mat = ret_ps.cov() * 252
                    corr_mat_ps = ret_ps.corr()
                    mu_vec  = ret_ps.mean() * 252  # retornos anuales esperados

                    # ── Pesos actuales del portafolio ──
                    pesos_actuales = np.ones(n_assets) / n_assets  # default: igual peso
                    if not port_v.empty:
                        vals_port = {}
                        for tk in tks:
                            row_tk = port_v[port_v["Ticker"]==tk]
                            if not row_tk.empty:
                                stats_tk = motor_avanzado(tk)
                                p_tk = float(stats_tk[1]) if stats_tk else float(row_tk.iloc[0]["Compra"])
                                vals_port[tk] = p_tk * float(row_tk.iloc[0]["Cantidad"])
                            else:
                                vals_port[tk] = ps_capital / n_assets
                        total_vals = sum(vals_port.values())
                        if total_vals > 0:
                            pesos_actuales = np.array([vals_port.get(tk, 0)/total_vals for tk in tks])
                            pesos_actuales = pesos_actuales / pesos_actuales.sum()

                    cov_np = cov_mat.values

                    # ── Métricas del portafolio actual ──
                    sigma_port = float(np.sqrt(pesos_actuales @ cov_np @ pesos_actuales))
                    ret_port   = float(pesos_actuales @ mu_vec.values)
                    sharpe_port= ret_port / sigma_port if sigma_port > 0 else 0

                    # VaR y ES del portafolio (paramétrico)
                    var_port_95 = -1.645 * sigma_port / np.sqrt(252)
                    es_port_95  = -2.063 * sigma_port / np.sqrt(252)

                    # Contribución marginal al riesgo (MCTR)
                    mctr = cov_np @ pesos_actuales / sigma_port
                    ctc  = pesos_actuales * mctr  # contribución total al riesgo
                    pct_ctc = ctc / ctc.sum() * 100 if ctc.sum() > 0 else ctc

                    # ── Optimización: Mínima varianza ──
                    from scipy.optimize import minimize
                    def port_var(w):
                        return float(w @ cov_np @ w)
                    def port_sharpe_neg(w):
                        r = float(w @ mu_vec.values)
                        s = float(np.sqrt(w @ cov_np @ w))
                        return -r/s if s > 0 else 0

                    constraints = [{"type":"eq","fun":lambda w: w.sum()-1}]
                    bounds = [(0.02, 0.60)] * n_assets  # 2%-60% por activo
                    w0 = np.ones(n_assets)/n_assets

                    # Min varianza
                    res_mv = minimize(port_var, w0, method="SLSQP",
                                      bounds=bounds, constraints=constraints)
                    w_mv = res_mv.x if res_mv.success else w0

                    # Max Sharpe
                    res_ms = minimize(port_sharpe_neg, w0, method="SLSQP",
                                      bounds=bounds, constraints=constraints)
                    w_ms = res_ms.x if res_ms.success else w0

                    sigma_mv = float(np.sqrt(w_mv @ cov_np @ w_mv))
                    ret_mv   = float(w_mv @ mu_vec.values)
                    sigma_ms = float(np.sqrt(w_ms @ cov_np @ w_ms))
                    ret_ms   = float(w_ms @ mu_vec.values)

                    # ── Panel resumen portafolio actual ──
                    st.markdown("<div class='label-tag'>Portafolio actual</div>", unsafe_allow_html=True)
                    c1,c2,c3,c4 = st.columns(4)
                    c1.metric("📊 Volatilidad anual",   f"{sigma_port*100:.1f}%")
                    c2.metric("📈 Retorno esperado",    f"{ret_port*100:.1f}%")
                    c3.metric("⚡ Sharpe ratio",        f"{sharpe_port:.3f}")
                    c4.metric("📉 VaR diario 95%",      f"{var_port_95*100:.2f}%",
                              f"ES: {es_port_95*100:.2f}%")

                    # ── Contribución al riesgo ──
                    st.markdown("<div class='label-tag' style='margin-top:16px'>Contribución marginal al riesgo (MCTR)</div>",
                                unsafe_allow_html=True)
                    st.markdown("""
                    <div style='color:#666;font-size:12px;margin-bottom:10px;font-family:JetBrains Mono'>
                    Una posición que contribuye mucho más al riesgo que su peso sugiere que está
                    sobrediversificada o que el activo es muy volátil en relación al portafolio.
                    </div>""", unsafe_allow_html=True)

                    fig_mctr = go.Figure()
                    fig_mctr.add_trace(go.Bar(
                        x=tks, y=pesos_actuales*100,
                        name="Peso actual (%)",
                        marker_color="#3b82f6", opacity=0.8,
                    ))
                    fig_mctr.add_trace(go.Bar(
                        x=tks, y=pct_ctc,
                        name="Contribución al riesgo (%)",
                        marker_color=["#ff4466" if c > p+5 else "#00ff9d" if c < p-5 else "#f59e0b"
                                      for c, p in zip(pct_ctc, pesos_actuales*100)],
                        opacity=0.9,
                    ))
                    fig_mctr.update_layout(
                        template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                        font=dict(family="Syne", color="#e8e8f0"), barmode="group", height=300,
                        margin=dict(l=16,r=16,t=16,b=16), xaxis=dict(showgrid=False, color="#444466"),
                        yaxis=dict(gridcolor="#1c1c30", color="#444466", ticksuffix="%"),
                        legend=dict(bgcolor="#0a0a16", font=dict(family="JetBrains Mono", size=11)),
                        title="Verde = peso > riesgo (eficiente) · Rojo = riesgo > peso (revisar)",
                    )
                    st.plotly_chart(fig_mctr, use_container_width=True)

                    # ── Comparativa: actual vs min-var vs max-sharpe ──
                    st.markdown("<div class='label-tag' style='margin-top:8px'>Portafolios óptimos vs actual</div>",
                                unsafe_allow_html=True)

                    estrategias = [
                        ("Actual",      pesos_actuales, sigma_port,  ret_port,  sharpe_port, "#888"),
                        ("Min. Var.",   w_mv,           sigma_mv,    ret_mv,    ret_mv/sigma_mv if sigma_mv>0 else 0, "#3b82f6"),
                        ("Max Sharpe",  w_ms,           sigma_ms,    ret_ms,    ret_ms/sigma_ms if sigma_ms>0 else 0, "#00ff9d"),
                    ]

                    cols_est = st.columns(3)
                    for ci_e, (nombre_e, pesos_e, sig_e, ret_e, sharpe_e, color_e) in enumerate(estrategias):
                        var_e = -1.645 * sig_e / np.sqrt(252)
                        with cols_est[ci_e]:
                            st.markdown(f"""
                            <div style='background:{color_e}0d;border:1px solid {color_e}33;
                                        border-radius:12px;padding:16px;margin-bottom:12px'>
                                <div style='font-size:10px;letter-spacing:2px;color:#444466;
                                            font-family:JetBrains Mono;text-transform:uppercase;
                                            margin-bottom:8px'>{nombre_e}</div>
                                <div style='font-family:JetBrains Mono;font-size:18px;
                                            font-weight:700;color:{color_e};margin-bottom:4px'>
                                    Sharpe {sharpe_e:.3f}
                                </div>
                                <div style='font-size:12px;color:#888;font-family:JetBrains Mono'>
                                    Ret: {ret_e*100:.1f}% · Vol: {sig_e*100:.1f}%<br>
                                    VaR diario: {var_e*100:.2f}%
                                </div>
                                <div style='margin-top:10px;padding-top:8px;border-top:1px solid #1c1c30'>
                                    {''.join([f"<div style='display:flex;justify-content:space-between;font-family:JetBrains Mono;font-size:11px;margin-bottom:2px'><span style='color:#666'>{tks[j]}</span><span style='color:{color_e}'>{pesos_e[j]*100:.1f}%  ${pesos_e[j]*ps_capital:,.0f}</span></div>" for j in range(n_assets)])}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                    # Frontera eficiente simplificada
                    st.markdown("<div class='label-tag' style='margin-top:8px'>Frontera eficiente</div>",
                                unsafe_allow_html=True)
                    n_pts = 40
                    sigmas_fe = []; retornos_fe = []
                    for target_r in np.linspace(float(mu_vec.min()), float(mu_vec.max()), n_pts):
                        def min_var_target(w):
                            return float(w @ cov_np @ w)
                        cons_fe = [
                            {"type":"eq","fun":lambda w: w.sum()-1},
                            {"type":"eq","fun":lambda w: float(w @ mu_vec.values)-target_r},
                        ]
                        try:
                            r_fe = minimize(min_var_target, w0, method="SLSQP",
                                            bounds=bounds, constraints=cons_fe)
                            if r_fe.success:
                                sigmas_fe.append(float(np.sqrt(r_fe.fun))*100)
                                retornos_fe.append(target_r*100)
                        except: pass

                    if sigmas_fe:
                        fig_fe = go.Figure()
                        fig_fe.add_trace(go.Scatter(
                            x=sigmas_fe, y=retornos_fe,
                            mode="lines", name="Frontera eficiente",
                            line=dict(color="#00ff9d", width=2),
                        ))
                        # Puntos de los portafolios
                        for nombre_e, _, sig_e, ret_e, _, color_e in estrategias:
                            fig_fe.add_trace(go.Scatter(
                                x=[sig_e*100], y=[ret_e*100],
                                mode="markers+text",
                                marker=dict(size=12, color=color_e, symbol="star"),
                                text=[nombre_e], textposition="top center",
                                textfont=dict(family="JetBrains Mono", size=10),
                                name=nombre_e,
                            ))
                        fig_fe.update_layout(
                            template="plotly_dark", paper_bgcolor="#0e0e1e", plot_bgcolor="#0e0e1e",
                            font=dict(family="Syne", color="#e8e8f0"),
                            title="Frontera eficiente — riesgo vs retorno",
                            height=380, margin=dict(l=16,r=16,t=48,b=16),
                            xaxis=dict(title="Volatilidad anual (%)", gridcolor="#1c1c30", color="#444466"),
                            yaxis=dict(title="Retorno anual esperado (%)", gridcolor="#1c1c30", color="#444466"),
                            legend=dict(bgcolor="#0a0a16", font=dict(family="JetBrains Mono", size=11)),
                        )
                        st.plotly_chart(fig_fe, use_container_width=True)
