import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# Configuración estética de la App
st.set_page_config(page_title="AI.Lino Stock Portfolio", layout="wide")

st.title("📊 AI.Lino Stock Portfolio")
st.subheader("Administración Cuantitativa y Detección de Techos")

# Lista de tus activos (basada en tus capturas)
tickers = ['HIMS', 'VIST', 'SNPS', 'GSIT', 'TSLA', 'FSLR', 'AAPL', 'AMD', 'TSM']

def analizar_rendimiento_y_techos(ticker):
    # Descargamos datos de los últimos 6 meses
    df = yf.download(ticker, period="6mo", interval="1d")
    if df.empty:
        return None
    
    precio_actual = df['Close'].iloc[-1]
    techo_6m = df['High'].max()
    rendimiento_semanal = ((precio_actual - df['Close'].iloc[-5]) / df['Close'].iloc[-5]) * 100
    
    # Lógica de Administración: Proximidad al techo
    distancia_al_techo = ((techo_6m - precio_actual) / techo_6m) * 100
    
    return {
        "Ticker": ticker,
        "Precio": precio_actual,
        "Rendimiento %": rendimiento_semanal,
        "Techo (6m)": techo_6m,
        "Distancia al Techo %": distancia_al_techo
    }

# Procesar datos
resultados = []
for t in tickers:
    res = analizar_rendimiento_y_techos(t)
    if res:
        resultados.append(res)

df_portfolio = pd.DataFrame(resultados)

# --- VISUALIZACIÓN ---
col1, col2 = st.columns([2, 1])

with col1:
    st.write("### Comparativa de Activos")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_portfolio['Ticker'],
        y=df_portfolio['Rendimiento %'],
        marker_color=['#00c805' if x > 0 else '#ff5000' for x in df_portfolio['Rendimiento %']]
    ))
    fig.update_layout(template="plotly_dark", title="Rendimiento Semanal")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.write("### 🛡️ Alertas de Administración")
    for _, row in df_portfolio.iterrows():
        # Si está a menos del 3% del techo, es zona de alerta
        if row['Distancia al Techo %'] < 3.0:
            st.error(f"**{row['Ticker']}**: Cerca de TECHO ({row['Distancia al Techo %']:.2f}%) - Evaluar Venta.")
        elif row['Rendimiento %'] < -5:
            st.warning(f"**{row['Ticker']}**: Caída fuerte. Revisar soportes.")
        else:
            st.success(f"**{row['Ticker']}**: En zona segura.")

# Tabla detallada
st.write("### Detalle del Portafolio")
st.dataframe(df_portfolio.style.format({
    "Precio": "${:.2f}",
    "Rendimiento %": "{:.2f}%",
    "Techo (6m)": "${:.2f}",
    "Distancia al Techo %": "{:.2f}%"
}))
