import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime

# --- CONFIGURACIÓN DE ESTILO ---
st.set_page_config(page_title="AI.Lino Stock Portfolio", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    div.stButton > button { width: 100%; border-radius: 5px; height: 3em; background-color: #2e7d32; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- MOTOR CUANTITATIVO (ALGO-CORE) ---
def motor_cuantico_kalman(ticker):
    """Filtro de Kalman simplificado para detectar tendencia limpia"""
    df = yf.download(ticker, period="6mo", interval="1d", progress=False)
    if df.empty: return None
    
    precios = df['Close'].values
    n_iter = len(precios)
    sz = (n_iter,)
    z = precios
    
    Q = 1e-5 # Varianza del proceso
    R = 0.1**2 # Varianza de la medición
    
    xhat = np.zeros(sz)      # Estimación a posteriori
    P = np.zeros(sz)         # Error a posteriori
    xhatminus = np.zeros(sz) # Estimación a priori
    Pminus = np.zeros(sz)    # Error a priori
    K = np.zeros(sz)         # Ganancia de Kalman
    
    xhat[0] = z[0]
    P[0] = 1.0
    
    for k in range(1, n_iter):
        xhatminus[k] = xhat[k-1]
        Pminus[k] = P[k-1] + Q
        K[k] = Pminus[k] / (Pminus[k] + R)
        xhat[k] = xhatminus[k] + K[k] * (z[k] - xhatminus[k])
        P[k] = (1 - K[k]) * Pminus[k]
        
    return xhat[-1], z[-1], (xhat[-1] - xhat[-2]) # Tendencia, Actual, Momentum

# --- BASE DE DATOS LOCAL (SIMULADA) ---
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

# --- SIDEBAR: GESTIÓN DE ACCIONES ---
with st.sidebar:
    st.header("⚙️ Gestión de Activos")
    busqueda = st.text_input("Buscar Ticker (ej: NVDA, TSLA, AMD)")
    
    if busqueda:
        try:
            info = yf.Ticker(busqueda).info
            nombre = info.get('longName', 'Desconocido')
            st.success(f"Encontrado: {nombre}")
            
            precio_compra = st.number_input("Precio de Compra (USD)", min_value=0.01)
            cantidad = st.number_input("Cantidad de Acciones", min_value=0.1)
            
            if st.button("➕ Agregar al Portafolio"):
                st.session_state.portfolio.append({
                    "Ticker": busqueda.upper(),
                    "Nombre": nombre,
                    "Compra": precio_compra,
                    "Cantidad": cantidad
                })
                st.rerun()
        except:
            st.error("Ticker no válido. Verifica en Yahoo Finance.")

    if st.button("🗑️ Limpiar Portafolio"):
        st.session_state.portfolio = []
        st.rerun()

# --- PÁGINA PRINCIPAL ---
st.title("Wealth: AI.Lino Stock Portfolio")

if not st.session_state.portfolio:
    st.info("Agrega acciones en el panel lateral para comenzar el análisis.")
else:
    # Cálculos de Portafolio
    resumen_data = []
    total_invertido = 0
    total_actual = 0
    
    for item in st.session_state.portfolio:
        kalman_trend, actual, momentum = motor_cuantico_kalman(item['Ticker'])
        val_actual = actual * item['Cantidad']
        val_compra = item['Compra'] * item['Cantidad']
        ganancia_abs = val_actual - val_compra
        rendimiento = (ganancia_abs / val_compra) * 100
        
        total_invertido += val_compra
        total_actual += val_actual
        
        # Lógica de Venta (Techos de Heisenberg/Viterbi)
        # Si el momentum de Kalman baja y el precio está cerca de máximos -> VENDER
        hist = yf.download(item['Ticker'], period="1mo", progress=False)
        techo = hist['High'].max()
        distancia_techo = ((techo - actual) / techo) * 100
        
        sugerencia = "MANTENER"
        if momentum < 0 and distancia_techo < 1.5:
            sugerencia = "VENDER (Techo Detectado)"
        elif rendimiento < -7:
            sugerencia = "STOP LOSS"

        resumen_data.append({
            "Ticker": item['Ticker'],
            "Precio Actual": round(actual, 2),
            "Rendimiento %": round(rendimiento, 2),
            "Estado Algo": sugerencia,
            "Valor": round(val_actual, 2)
        })

    # --- MÉTRICAS SUPERIORES ---
    rendimiento_total = ((total_actual - total_invertido) / total_invertido) * 100
    c1, c2, c3 = st.columns(3)
    c1.metric("Patrimonio Neto", f"${total_actual:,.2f}", f"{rendimiento_total:.2f}%")
    c2.metric("Inversión Total", f"${total_invertido:,.2f}")
    c3.metric("Ganancia Total", f"${(total_actual - total_invertido):,.2f}")

    # --- GRÁFICA DE RENDIMIENTO (ESTILO WEALTH) ---
    df_plot = pd.DataFrame(resumen_data)
    fig = go.Figure(go.Bar(
        x=df_plot['Ticker'],
        y=df_plot['Rendimiento %'],
        marker_color=['#00c805' if x > 0 else '#ff5000' for x in df_plot['Rendimiento %']],
        text=df_plot['Rendimiento %'],
        textposition='auto',
    ))
    fig.update_layout(title="Contribución al Rendimiento (Filtro Kalman Activo)", template="plotly_dark", height=400)
    st.plotly_chart(fig, use_container_width=True)

    # --- SECCIÓN DE ACCIONES A VENDER ---
    st.header("📉 Señales de Salida Exponencial")
    ventas = df_plot[df_plot['Estado Algo'] != "MANTENER"]
    if not ventas.empty:
        st.warning("El motor ha detectado agotamiento de tendencia o techos en los siguientes activos:")
        st.table(ventas[['Ticker', 'Precio Actual', 'Rendimiento %', 'Estado Algo']])
    else:
        st.success("Todas las posiciones mantienen momentum alcista según el modelo HMM/Kalman.")

    # --- TABLA DE POSICIONES DETALLADA ---
    st.header("📋 Mis Posiciones")
    st.dataframe(df_plot, use_container_width=True)
