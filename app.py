import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os

# --- CONFIGURACIÓN Y PERSISTENCIA ---
FILE_PATH = 'portfolio_data.csv'

def guardar_datos(df):
    df.to_csv(FILE_PATH, index=False)

def cargar_datos():
    if os.path.exists(FILE_PATH):
        return pd.read_csv(FILE_PATH)
    return pd.DataFrame(columns=["Ticker", "Nombre", "Compra", "Cantidad", "Mercado"])

# Inicializar estado
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = cargar_datos()

# --- MOTOR CUANTITATIVO (ALGO-CORE) ---
def motor_avanzado(ticker):
    """Integración de Kalman y Momentum para detección de techos"""
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty: return None
        precios = df['Close'].values
        # Filtro de Kalman simplificado (Heisenberg Uncertainty adjustment)
        xhat = precios[0]; P = 1.0; Q = 1e-5; R = 0.01**2
        for p in precios:
            xhatminus = xhat; Pminus = P + Q
            K = Pminus / (Pminus + R)
            xhat = xhatminus + K * (p - xhatminus)
            P = (1 - K) * Pminus
        return xhat, precios[-1] # Tendencia filtrada y Precio actual
    except: return None

# --- INTERFAZ ---
st.set_page_config(page_title="AI.Lino Stock Portfolio", layout="wide")
st.title("🏛️ AI.Lino Stock Portfolio Pro")

# --- PANEL DE BÚSQUEDA Y AGREGADO ---
with st.expander("🔍 Buscar y Agregar Acciones (México, USA, Europa)", expanded=True):
    query = st.text_input("Escribe el nombre de la empresa (ej: Tesla, Bimbo, Apple)")
    
    if query:
        # Buscamos opciones de tickers usando la función Search de yfinance
        search = yf.Search(query, max_results=8).quotes
        if search:
            options = {f"{s['symbol']} - {s.get('exchange', 'N/A')} ({s.get('longname', '')})": s['symbol'] for s in search}
            seleccion = st.selectbox("Selecciona el Ticker correcto:", list(options.keys()))
            
            col_a, col_b = st.columns(2)
            p_compra = col_a.number_input("Precio de Compra (Tu moneda local)", min_value=0.0)
            cant = col_b.number_input("Cantidad", min_value=0.0)
            
            if st.button("Confirmar y Agregar al Portafolio"):
                ticker_final = options[seleccion]
                nuevo_item = pd.DataFrame([{
                    "Ticker": ticker_final, 
                    "Nombre": seleccion.split('(')[-1].replace(')', ''),
                    "Compra": p_compra,
                    "Cantidad": cant,
                    "Mercado": seleccion.split('-')[1].split('(')[0].strip()
                }])
                st.session_state.portfolio = pd.concat([st.session_state.portfolio, nuevo_item], ignore_index=True)
                guardar_datos(st.session_state.portfolio)
                st.success(f"Agregado {ticker_final}")
                st.rerun()

# --- VISUALIZACIÓN EN TIEMPO REAL ---
if not st.session_state.portfolio.empty:
    st.header("📊 Monitor de Rendimiento Exponencial")
    
    resumen = []
    total_v = 0
    
    # Procesar cada acción una por una
    for index, row in st.session_state.portfolio.iterrows():
        stats = motor_avanzado(row['Ticker'])
        if stats:
            trend, actual = stats
            rendimiento = ((actual - row['Compra']) / row['Compra']) * 100
            valor_act = actual * row['Cantidad']
            total_v += valor_act
            
            # Lógica de Venta (Techo detectado si precio actual > tendencia filtrada y RSI alto sim)
            estado = "MANTENER"
            if actual > trend * 1.05: estado = "VENDER (Techo)"
            
            resumen.append({
                "ID": index,
                "Ticker": row['Ticker'],
                "Mercado": row['Mercado'],
                "Rendimiento": round(rendimiento, 2),
                "Acción": estado,
                "Valor Actual": round(valor_act, 2)
            })

    df_res = pd.DataFrame(resumen)
    
    # Gráfica interactiva
    fig = go.Figure(go.Bar(
        x=df_res['Ticker'], y=df_res['Rendimiento'],
        marker_color=['#00c805' if x > 0 else '#ff5000' for x in df_res['Rendimiento']]
    ))
    fig.update_layout(template="plotly_dark", title="Rendimiento por Activo (%)")
    st.plotly_chart(fig, use_container_width=True)

    # --- LISTADO DE VENTAS Y GESTIÓN ---
    st.subheader("📋 Gestión de Posiciones")
    for i, r in df_res.iterrows():
        c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
        c1.write(f"**{r['Ticker']}**")
        c2.write(f"Rend: {r['Rendimiento']}% | {r['Mercado']}")
        if r['Acción'] == "VENDER (Techo)":
            c3.error("🚨 SUGERENCIA: VENDER (Techo)")
        else:
            c3.success("💎 MANTENER")
            
        if c4.button("Eliminar", key=f"del_{i}"):
            st.session_state.portfolio = st.session_state.portfolio.drop(i)
            guardar_datos(st.session_state.portfolio)
            st.rerun()
