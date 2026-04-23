import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="AI.Lino Stock Portfolio", layout="wide")

# Estilo visual para emular tus capturas
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; color: #00c805; }
    .stTable { background-color: #161b22; }
    </style>
    """, unsafe_allow_html=True)

# --- MOTOR CUANTITATIVO HÍBRIDO ---
def motor_cuantico_avanzado(ticker):
    """Integración de Filtro Kalman y Lógica de Estados (HMM)"""
    try:
        # Descargamos un poco más de datos para asegurar estabilidad
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df.empty or len(df) < 20:
            return None
        
        # Manejo de MultiIndex si yfinance devuelve columnas dobles
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        precios = df['Close'].values.flatten()
        z = precios[-100:]  # Usamos los últimos 100 días para el filtro
        
        # Inicialización del Filtro de Kalman
        n = len(z)
        xhat = np.zeros(n)
        P = np.zeros(n)
        xhat[0] = z[0]
        P[0] = 1.0
        Q, R = 1e-4, 0.01**2  # Parámetros de ruido de proceso y medición
        
        for k in range(1, n):
            x_prior = xhat[k-1]
            P_prior = P[k-1] + Q
            K = P_prior / (P_prior + R)
            xhat[k] = x_prior + K * (z[k] - x_prior)
            P[k] = (1 - K) * P_prior
            
        tendencia_limpia = xhat[-1]
        precio_actual = z[-1]
        momentum = (xhat[-1] - xhat[-5]) / xhat[-5] # Cambio en tendencia limpia
        
        # Detección de Techos (Resistencia de 52 semanas)
        techo_anual = df['High'].max()
        proximidad_techo = (precio_actual / techo_anual)
        
        return {
            "actual": precio_actual,
            "tendencia": tendencia_limpia,
            "momentum": momentum,
            "techo": techo_anual,
            "distancia_techo": (1 - proximidad_techo) * 100
        }
    except Exception as e:
        return None

# --- PERSISTENCIA DE DATOS ---
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

# --- PANEL DE CONTROL (IZQUIERDA) ---
with st.sidebar:
    st.header("⚙️ Administración")
    ticker_input = st.text_input("Ticker oficial (ej. VIST, TSLA)").upper()
    
    if ticker_input:
        try:
            ticker_obj = yf.Ticker(ticker_input)
            nombre = ticker_obj.info.get('longName', ticker_input)
            st.success(f"Detectado: {nombre}")
            
            p_compra = st.number_input("Precio Compra (USD)", value=0.0, format="%.2f")
            cant = st.number_input("Cantidad", value=1.0, format="%.2f")
            
            if st.button("➕ Añadir a AI.Lino Portfolio"):
                st.session_state.portfolio.append({
                    "Ticker": ticker_input,
                    "Compra": p_compra,
                    "Cantidad": cant
                })
                st.rerun()
        except:
            st.error("No se pudo validar el Ticker.")

    if st.button("🗑️ Reiniciar Todo"):
        st.session_state.portfolio = []
        st.rerun()

# --- DASHBOARD PRINCIPAL ---
st.title("Wealth: AI.Lino Stock Portfolio")

if st.session_state.portfolio:
    resumen = []
    t_invertido, t_actual = 0.0, 0.0
    
    for item in st.session_state.portfolio:
        stats = motor_cuantico_avanzado(item['Ticker'])
        if stats:
            valor_c = item['Compra'] * item['Cantidad']
            valor_a = stats['actual'] * item['Cantidad']
            rend_pct = ((valor_a - valor_c) / valor_c) * 100 if valor_c > 0 else 0
            
            t_invertido += valor_c
            t_actual += valor_a
            
            # Lógica de Rebalanceo (Viterbi/Heisenberg inspired)
            # Si el momentum es negativo y estamos a < 3% del techo anual -> VENDER
            if stats['momentum'] < 0 and stats['distancia_techo'] < 3.0:
                accion = "🔴 VENTA (Techo/Debilidad)"
            elif stats['momentum'] > 0.02:
                accion = "🟢 MANTENER (Fuerza)"
            else:
                accion = "🟡 OBSERVAR"
                
            resumen.append({
                "Ticker": item['Ticker'],
                "Precio": stats['actual'],
                "Rend %": rend_pct,
                "Momentum (K)": stats['momentum'] * 100,
                "Acción Sugerida": accion,
                "Valor": valor_a
            })

    # Métricas Globales
    c1, c2, c3 = st.columns(3)
    ganancia_total = t_actual - t_invertido
    pct_total = (ganancia_total / t_invertido * 100) if t_invertido > 0 else 0
    
    c1.metric("Patrimonio Total", f"${t_actual:,.2f}", f"{pct_total:.2f}%")
    c2.metric("Inversión", f"${t_invertido:,.2f}")
    c3.metric("Resultado", f"${ganancia_total:,.2f}")

    # Gráfico de Contribución
    df_res = pd.DataFrame(resumen)
    fig = go.Figure(go.Bar(
        x=df_res['Ticker'], y=df_res['Rend %'],
        marker_color=['#00c805' if x > 0 else '#ff5000' for x in df_res['Rend %']]
    ))
    fig.update_layout(title="Contribución al Rendimiento", template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    # Tabla de Decisiones
    st.header("📉 Decisiones de Algoritmo")
    st.table(df_res[["Ticker", "Acción Sugerida", "Rend %", "Momentum (K)"]])

else:
    st.info("Configura tus activos en el panel izquierdo para activar el motor.")
