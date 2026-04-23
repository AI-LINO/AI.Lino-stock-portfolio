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
        if df.empty:
            return None
        
        # FIX: Extraer serie de forma segura (compatible con yfinance v1.x)
        close = df['Close']
        if isinstance(close.columns if hasattr(close, 'columns') else None, pd.MultiIndex):
            close = close.iloc[:, 0]
        precios = close.dropna().values.flatten().astype(float)
        
        if len(precios) < 2:
            return None

        # Filtro de Kalman simplificado
        xhat = precios[0]; P = 1.0; Q = 1e-5; R = 0.01**2
        for p in precios:
            xhatminus = xhat; Pminus = P + Q
            K = Pminus / (Pminus + R)
            xhat = xhatminus + K * (float(p) - xhatminus)
            P = (1 - K) * Pminus
        
        return float(xhat), float(precios[-1])
    except:
        return None

# --- INTERFAZ ---
st.set_page_config(page_title="AI.Lino Stock Portfolio", layout="wide")
st.title("🏛️ AI.Lino Stock Portfolio Pro")

# --- PANEL DE BÚSQUEDA Y AGREGADO ---
with st.expander("🔍 Buscar y Agregar Acciones (México, USA, Europa)", expanded=True):
    query = st.text_input("Escribe el nombre de la empresa (ej: Tesla, Bimbo, Apple)")
    
    if query:
        search_results = yf.Search(query, max_results=8).quotes
        if search_results:
            options = {
                f"{s['symbol']} - {s.get('exchange', 'N/A')} ({s.get('longname', s.get('shortname', ''))})": s['symbol']
                for s in search_results
            }
            seleccion = st.selectbox("Selecciona el Ticker correcto:", list(options.keys()))
            
            col_a, col_b = st.columns(2)
            p_compra = col_a.number_input("Precio de Compra (Tu moneda local)", min_value=0.0, key="p_compra")
            cant = col_b.number_input("Cantidad", min_value=0.0, key="cant")
            
            if st.button("Confirmar y Agregar al Portafolio"):
                ticker_final = options[seleccion]
                
                # FIX: verificar duplicado antes de agregar
                ya_existe = ticker_final in st.session_state.portfolio['Ticker'].values
                if ya_existe:
                    st.warning(f"{ticker_final} ya está en el portafolio.")
                else:
                    # FIX: extracción segura del nombre y mercado
                    partes = seleccion.split(' - ')
                    mercado = partes[1].split('(')[0].strip() if len(partes) > 1 else "N/A"
                    nombre = seleccion.split('(')[-1].replace(')', '').strip() if '(' in seleccion else seleccion

                    nuevo_item = pd.DataFrame([{
                        "Ticker": ticker_final,
                        "Nombre": nombre,
                        "Compra": p_compra,
                        "Cantidad": cant,
                        "Mercado": mercado,
                    }])
                    st.session_state.portfolio = pd.concat(
                        [st.session_state.portfolio, nuevo_item], ignore_index=True  # FIX: ignore_index=True siempre
                    )
                    guardar_datos(st.session_state.portfolio)
                    st.success(f"✅ Agregado {ticker_final}")
                    st.rerun()

# --- VISUALIZACIÓN EN TIEMPO REAL ---
if not st.session_state.portfolio.empty:
    st.header("📊 Monitor de Rendimiento Exponencial")
    
    resumen = []
    total_v = 0
    
    # FIX: usar .reset_index(drop=True) para índices limpios y consistentes
    portfolio_limpio = st.session_state.portfolio.reset_index(drop=True)

    for idx in range(len(portfolio_limpio)):
        row = portfolio_limpio.iloc[idx]
        stats = motor_avanzado(row['Ticker'])
        
        if stats:
            trend, actual = stats
            compra = float(row['Compra'])
            cantidad = float(row['Cantidad'])
            rendimiento = ((actual - compra) / compra) * 100 if compra > 0 else 0.0
            valor_act = actual * cantidad
            total_v += valor_act
            estado = "VENDER (Techo)" if actual > trend * 1.05 else "MANTENER"
        else:
            # FIX: Si falla la descarga, mostrar igual con datos parciales
            rendimiento = 0.0
            valor_act = 0.0
            estado = "SIN DATOS"

        resumen.append({
            "idx_original": idx,   # FIX: guardar índice real para eliminar correctamente
            "Ticker": row['Ticker'],
            "Mercado": row['Mercado'],
            "Rendimiento": round(rendimiento, 2),
            "Acción": estado,
            "Valor Actual": round(valor_act, 2)
        })

    df_res = pd.DataFrame(resumen)
    
    # Gráfica interactiva
    colores = []
    for x in df_res['Rendimiento']:
        if x > 0:
            colores.append('#00c805')
        elif x < 0:
            colores.append('#ff5000')
        else:
            colores.append('#888888')

    fig = go.Figure(go.Bar(
        x=df_res['Ticker'],
        y=df_res['Rendimiento'],
        marker_color=colores
    ))
    fig.update_layout(template="plotly_dark", title="Rendimiento por Activo (%)")
    st.plotly_chart(fig, use_container_width=True)

    # Valor total del portafolio
    st.metric("💰 Valor Total del Portafolio", f"${total_v:,.2f}")

    # --- LISTADO DE VENTAS Y GESTIÓN ---
    st.subheader("📋 Gestión de Posiciones")
    
    for _, r in df_res.iterrows():
        c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
        c1.write(f"**{r['Ticker']}**")
        c2.write(f"Rend: {r['Rendimiento']}% | {r['Mercado']}")
        
        if r['Acción'] == "VENDER (Techo)":
            c3.error("🚨 SUGERENCIA: VENDER (Techo)")
        elif r['Acción'] == "SIN DATOS":
            c3.warning("⚠️ Sin datos de mercado")
        else:
            c3.success("💎 MANTENER")
        
        # FIX: key único usando ticker para evitar conflictos entre reruns
        if c4.button("Eliminar", key=f"del_{r['Ticker']}"):
            idx_real = int(r['idx_original'])
            st.session_state.portfolio = (
                st.session_state.portfolio
                .reset_index(drop=True)       # FIX: limpiar índice antes de drop
                .drop(index=idx_real)
                .reset_index(drop=True)       # FIX: limpiar índice después de drop
            )
            guardar_datos(st.session_state.portfolio)
            st.rerun()
