import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os

# --- PERSISTENCIA ---
FILE_PATH = 'portfolio_ai_lino.csv'

def guardar_datos(df):
    df.to_csv(FILE_PATH, index=False)

def cargar_datos():
    if os.path.exists(FILE_PATH):
        try:
            return pd.read_csv(FILE_PATH)
        except:
            return pd.DataFrame(columns=["Ticker", "Nombre", "Compra", "Cantidad", "Mercado"])
    return pd.DataFrame(columns=["Ticker", "Nombre", "Compra", "Cantidad", "Mercado"])

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = cargar_datos()

# --- MOTOR CUÁNTICO DE ADMINISTRACIÓN ---
def motor_cuantico(ticker):
    try:
        # Descarga de datos con manejo de errores de múltiples columnas
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty: return None
        
        # Asegurar que tomamos solo una columna (evita el ValueError de la imagen)
        precios = df['Close'].iloc[:, 0].values if isinstance(df['Close'], pd.DataFrame) else df['Close'].values
        maximos = df['High'].iloc[:, 0].values if isinstance(df['High'], pd.DataFrame) else df['High'].values
        
        # Filtro de Kalman para tendencia limpia (Lógica Simons)
        xhat = precios[0]; P = 1.0; Q = 1e-5; R = 0.01**2
        for p in precios:
            xhatminus = xhat; Pminus = P + Q
            K = Pminus / (Pminus + R)
            xhat = xhatminus + K * (p - xhatminus)
            P = (1 - K) * Pminus
        
        return xhat, precios[-1], np.max(maximos)
    except Exception as e:
        return None

# --- INTERFAZ ---
st.set_page_config(page_title="AI.Lino Stock Portfolio Pro", layout="wide")
st.title("🏛️ AI.Lino Stock Portfolio Pro")

# --- BUSCADOR ---
with st.expander("🔍 Buscar y Agregar (México .MX, USA, Europa)", expanded=True):
    query = st.text_input("Empresa (ej: Bimbo, Tesla, Nvidia)")
    if query:
        search = yf.Search(query, max_results=10).quotes
        if search:
            opciones = {f"{s['symbol']} | {s.get('exchange', 'N/A')} | {s.get('longname', 'Desconocido')}": s['symbol'] for s in search}
            seleccion = st.selectbox("Selecciona el activo exacto:", list(opciones.keys()))
            
            c1, c2 = st.columns(2)
            p_compra = c1.number_input("Precio de Compra", min_value=0.0, format="%.2f")
            cant = c2.number_input("Cantidad", min_value=0.0, format="%.4f")
            
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
                st.rerun()

# --- MONITOR DE RENDIMIENTO ---
if not st.session_state.portfolio.empty:
    st.divider()
    resumen_list = []
    
    for i, row in st.session_state.portfolio.iterrows():
        data = motor_cuantico(row['Ticker'])
        if data:
            trend, actual, techo = data
            rend = ((actual - row['Compra']) / row['Compra']) * 100
            dist_techo = ((techo - actual) / techo) * 100
            
            # Algoritmo de decisión
            estado = "MANTENER"
            if dist_techo < 1.5: estado = "VENDER (Techo)"
            elif rend < -7: estado = "STOP LOSS"

            resumen_list.append({
                "Index": i, "Ticker": row['Ticker'], "Rend %": round(rend, 2),
                "Acción": estado, "Valor": round(actual * row['Cantidad'], 2)
            })

    if resumen_list:
        df_res = pd.DataFrame(resumen_list)
        
        # Gráfica interactiva
        fig = go.Figure(go.Bar(
            x=df_res['Ticker'], y=df_res['Rend %'],
            marker_color=['#00c805' if x > 0 else '#ff5000' for x in df_res['Rend %']]
        ))
        fig.update_layout(title="Rendimiento del Portafolio (%)", template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        # --- GESTIÓN INDIVIDUAL ---
        st.subheader("📋 Gestión de Posiciones")
        for _, r in df_res.iterrows():
            col_t, col_r, col_s, col_d = st.columns([1, 1, 2, 1])
            col_t.write(f"**{r['Ticker']}**")
            col_r.write(f"{r['Rend %']}%")
            
            if "VENDER" in r['Acción']:
                col_s.error(f"🚨 {r['Acción']}")
            else:
                col_s.success(f"💎 {r['Acción']}")
                
            if col_d.button("🗑️ Eliminar", key=f"del_{r['Index']}"):
                st.session_state.portfolio = st.session_state.portfolio.drop(r['Index'])
                guardar_datos(st.session_state.portfolio)
                st.rerun()
