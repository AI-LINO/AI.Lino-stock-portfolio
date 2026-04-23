import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os

# --- PERSISTENCIA DE DATOS ---
FILE_PATH = 'portfolio_ai_lino.csv'

def guardar_datos(df):
    df.to_csv(FILE_PATH, index=False)

def cargar_datos():
    if os.path.exists(FILE_PATH):
        return pd.read_csv(FILE_PATH)
    return pd.DataFrame(columns=["Ticker", "Nombre", "Compra", "Cantidad", "Mercado"])

# Inicializar el estado del portafolio
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = cargar_datos()

# --- MOTOR CUANTITATIVO (KALMAN / VITERBI) ---
def motor_cuantico(ticker):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty: return None
        precios = df['Close'].values
        
        # Filtro de Kalman para tendencia limpia
        xhat = precios[0]; P = 1.0; Q = 1e-5; R = 0.01**2
        for p in precios:
            xhatminus = xhat; Pminus = P + Q
            K = Pminus / (Pminus + R)
            xhat = xhatminus + K * (p - xhatminus)
            P = (1 - K) * Pminus
        
        # Lógica de "Techo" (Resistencia de 3 meses)
        techo_historico = df['High'].max()
        return xhat, precios[-1], techo_historico
    except: return None

# --- INTERFAZ ESTILO "WEALTH" ---
st.set_page_config(page_title="AI.Lino Stock Portfolio Pro", layout="wide")
st.title("🏛️ AI.Lino Stock Portfolio Pro")

# --- BUSCADOR GLOBAL ---
with st.expander("🔍 Buscar Acción (Global: .MX, USA, Europa)", expanded=True):
    query = st.text_input("Nombre de la empresa (ej: Bimbo, Tesla, Nvidia)")
    if query:
        search = yf.Search(query, max_results=10).quotes
        if search:
            # Crear lista de opciones clara
            opciones = {f"{s['symbol']} | {s.get('exchange', 'N/A')} | {s.get('longname', 'Desconocido')}": s['symbol'] for s in search}
            seleccion = st.selectbox("Selecciona el activo correcto:", list(opciones.keys()))
            
            c1, c2 = st.columns(2)
            p_compra = c1.number_input("Precio de Compra (USD/MXN)", min_value=0.0, format="%.2f")
            cant = c2.number_input("Cantidad de títulos", min_value=0.0, format="%.4f")
            
            if st.button("✅ Agregar al Portafolio"):
                ticker_id = opciones[seleccion]
                nueva_fila = pd.DataFrame([{
                    "Ticker": ticker_id,
                    "Nombre": seleccion.split('|')[-1].strip(),
                    "Compra": p_compra,
                    "Cantidad": cant,
                    "Mercado": seleccion.split('|')[1].strip()
                }])
                st.session_state.portfolio = pd.concat([st.session_state.portfolio, nueva_fila], ignore_index=True)
                guardar_datos(st.session_state.portfolio)
                st.success(f"Agregado: {ticker_id}")
                st.rerun()

# --- MONITOR DE RENDIMIENTO ---
if not st.session_state.portfolio.empty:
    st.divider()
    resumen_list = []
    
    for i, row in st.session_state.portfolio.iterrows():
        data = motor_cuantico(row['Ticker'])
        if data:
            trend, actual, techo = data
            rendimiento = ((actual - row['Compra']) / row['Compra']) * 100
            
            # Condición de administración de techos
            distancia_techo = ((techo - actual) / techo) * 100
            estado = "MANTENER"
            if distancia_techo < 1.5: estado = "VENDER (Techo)"
            elif rendimiento < -8: estado = "STOP LOSS"

            resumen_list.append({
                "Index": i,
                "Ticker": row['Ticker'],
                "Rendimiento %": round(rendimiento, 2),
                "Sugerencia": estado,
                "Valor Actual": round(actual * row['Cantidad'], 2)
            })

    df_resumen = pd.DataFrame(resumen_list)

    # Gráfico de Barras interactivo
    fig = go.Figure(go.Bar(
        x=df_resumen['Ticker'], y=df_resumen['Rendimiento %'],
        marker_color=['#00c805' if x > 0 else '#ff5000' for x in df_resumen['Rendimiento %']]
    ))
    fig.update_layout(title="Rendimiento del Portafolio (%)", template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    # --- LISTA DE ACCIONES Y ELIMINACIÓN INDIVIDUAL ---
    st.subheader("📋 Mis Posiciones Activas")
    for _, r in df_resumen.iterrows():
        col_t, col_r, col_s, col_d = st.columns([1, 1, 2, 1])
        col_t.write(f"**{r['Ticker']}**")
        col_r.write(f"{r['Rendimiento %']}%")
        
        if "VENDER" in r['Sugerencia']:
            col_s.error(f"🚨 {r['Sugerencia']}")
        else:
            col_s.success(f"💎 {r['Sugerencia']}")
            
        if col_d.button("🗑️ Eliminar", key=f"btn_{r['Index']}"):
            st.session_state.portfolio = st.session_state.portfolio.drop(r['Index'])
            guardar_datos(st.session_state.portfolio)
            st.rerun()
