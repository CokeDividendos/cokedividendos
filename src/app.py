import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px     
import requests, datetime, json 
from pathlib import Path
from datetime import date
# ----------------------------------------------------------------------
#   Cache global (SQLite) para todas las peticiones HTTP → 6 horas
# ----------------------------------------------------------------------
from datetime import timedelta
import requests_cache

requests_cache.install_cache(
    "yf_cache",          # nombre del archivo *.sqlite
    expire_after=timedelta(hours=24),
    allowable_codes=(200, 203, 300, 301, 404, 429),          # cachea también 404
    allowable_methods=("GET", "POST")    # por si acaso
)


# ── Import para sesión “browser-like” ────────────────────────────────
from curl_cffi import requests as curl_requests

# Creamos UNA sesión global que imita Chrome
YF_SESSION = curl_requests.Session(impersonate="chrome")


# --------------------------
# Configuración de la App
# --------------------------
st.set_page_config(
    page_title="Plataforma de Análisis", 
    page_icon="Coke Dividendos (8).png",  # Asegúrate de que esta imagen se encuentre en la carpeta del proyecto
    layout="wide"
)

# Crear las pestañas horizontales con st.tabs
# --------------------------
tabs = st.tabs(["Valoración y Análisis Financiero", "Seguimiento de Cartera", "Analizar ETF's", "Finanzas Personales", "Calculadora de Interés Compuesto"])

# Pestaña 1: Valoración y Análisis Financiero (aquí se coloca todo tu código actual)
with tabs[0]:

    # Mostrar el título junto con el ícono en la cabecera
    col1, col2 = st.columns([1, 5])

    with col1:
            # --- Logo -----------------------------------------------------------------
        from pathlib import Path
        ASSETS_DIR = Path(__file__).parent.parent / "assets"
        logo_path  = ASSETS_DIR / "Coke Dividendos (8).png"

    if logo_path.exists():
        st.image(str(logo_path), width=150)
    else:
        st.write("🧩 (logo no encontrado)")

    with col2:
            st.title("📊 Plataforma de Análisis de Coke Dividendos")

        # Colores base
    primary_orange = "darkorange"
    primary_blue = "deepskyblue"
    primary_pink = "hotpink"
    text_white = "white"

    # --------------------------
    # Entrada del Usuario
    # --------------------------
    ticker_input = st.text_input("🔎 Ingresa el Ticker (Ej: AAPL, MSFT, KO)", value="AAPL")

    period_options = {
        "5 años": "5y",
        "10 años": "10y",
        "15 años": "15y",
        "20 años": "20y"
    }
    period_selection = st.selectbox("⏳ Selecciona el período de análisis:", list(period_options.keys()))
    selected_period = period_options[period_selection]

    interval_options = {
        "Diario": "1d",
        "Mensual": "1mo"
    }
    interval_selection = st.selectbox("📆 Frecuencia de datos:", list(interval_options.keys()))
    selected_interval = interval_options[interval_selection]

    # --------------------------
    # Descargar Datos desde Yahoo Finance
    # --------------------------
    try:
        ticker_data = yf.Ticker(ticker_input, session=YF_SESSION)
        price_data = ticker_data.history(period=selected_period, interval=selected_interval)
        
        if price_data.empty:
            st.warning("No se encontraron datos para ese ticker. Revisa el símbolo.")
        else:
            # ==========================
            # BLOQUE 1: Información General y Datos Clave (Cálculos Básicos)
            # ==========================
            info = ticker_data.info

            # ─── Datos de negocio ─────────────────────────────────────────
            company_name = info.get("longName", "Nombre no disponible")
            sector       = info.get("sector",   "N/A")
            industry     = info.get("industry", "N/A")

            # ─── Métricas básicas de cotización ───────────────────────────

            # ─── valores por defecto para evitar NameError si hay rate‑limit ───
            price = dividend = yield_actual = payout_ratio = pe_ratio = roe_actual = None
            eps_actual = pb = cagr_dividend = avg_yield = total_return = annual_return = None
            sector = industry = company_name = "N/A"

            price        = info.get('currentPrice', None)
            dividend     = info.get('dividendRate', None)
            yield_actual = (dividend / price * 100) if dividend and price else None
            payout_ratio = info.get('payoutRatio', None)
            pe_ratio     = info.get('trailingPE', None)
            roe_actual   = info.get('returnOnEquity', None)      # decimal
            eps_actual   = info.get('trailingEps', None)
            pb           = info.get('priceToBook', None)
                        
            # Book/Share: (Capital Contable Total - Acciones preferentes) / Acciones totales en circulación.
            try:
                bs = ticker_data.balance_sheet.transpose()
                capital_total = bs.get("Total Equity Gross Minority Interest", None)
                if capital_total is not None:
                    capital_total = capital_total.iloc[0]
            except Exception as e:
                capital_total = None
            preferred_shares = 0  # Se asume 0 si no se tienen datos
            try:
                ordinary_shares
            except NameError:
                ordinary_shares = info.get('sharesOutstanding', None)
            book_per_share = (capital_total - preferred_shares) / ordinary_shares if (capital_total is not None and ordinary_shares is not None and ordinary_shares != 0) else None
            
            # G: Tasa de crecimiento = ROE actual * (1 - PauOut)
            G = roe_actual * (1 - payout_ratio) if (roe_actual is not None and payout_ratio is not None) else None
            G_percent = G * 100 if G is not None else None
            
            # Múltiplo de Crecimiento:
            if G_percent is not None:
                if G_percent <= 10:
                    multiplier = 10
                elif 10 < G_percent <= 20:
                    multiplier = 15
                else:
                    multiplier = 20
            else:
                multiplier = None
            
            # EPS a 5 años: EPS actual * (1 + G)^5 (G expresado en porcentaje)
            eps_5y = eps_actual * ((1 + (G_percent/100))**5) if (eps_actual is not None and G_percent is not None) else None
            
            # Precio PER a 5 años: se calcula como EPS a 5 años * Múltiplo de Crecimiento
            per_5y = eps_5y * multiplier if (eps_5y is not None and multiplier is not None) else None
            
            # G Esperado: ((Precio PER a 5 años / Precio Actual)^(1/5)) - 1
            g_esperado = ((per_5y / price)**(1/5) - 1) if (per_5y is not None and price is not None and price != 0) else None
            g_esperado_percent = g_esperado * 100 if g_esperado is not None else None
            
            # Valor de Precio Justo: P/B * Book/Share
            fair_price = pb * book_per_share if (pb is not None and book_per_share is not None) else None
            
            # --- Cálculo del CAGR del Dividendo (usando dividendos históricos) ---
            dividends = ticker_data.dividends
            if not dividends.empty:
                annual_dividends = dividends.resample('Y').sum()
                annual_dividends.index = annual_dividends.index.year
                start_year = pd.to_datetime(price_data.index[0]).year
                end_year = pd.to_datetime(price_data.index[-1]).year
                annual_dividends = annual_dividends[(annual_dividends.index >= start_year) & (annual_dividends.index <= end_year)]
                if len(annual_dividends) >= 3:
                    first_value = annual_dividends.iloc[0]
                    penultimate_value = annual_dividends.iloc[-2]
                    n_years = annual_dividends.index[-2] - annual_dividends.index[0]
                    cagr_dividend = ((penultimate_value / first_value) ** (1 / n_years) - 1) * 100
                else:
                    cagr_dividend = None
                # Yield Promedio:
                df_yield = price_data[['Close']].copy()
                df_yield['Año'] = df_yield.index.year
                dividend_map = annual_dividends.to_dict()
                df_yield['Dividendo Anual'] = df_yield['Año'].map(dividend_map)
                df_yield['Yield (%)'] = (df_yield['Dividendo Anual'] / df_yield['Close']) * 100
                if len(annual_dividends) > 1:
                    max_full_year = sorted(annual_dividends.index)[-2]
                    df_yield = df_yield[df_yield['Año'] <= max_full_year]
                avg_yield = df_yield['Yield (%)'].mean()
            else:
                cagr_dividend = None
                avg_yield = None

            # ─── Retornos históricos según rango elegido ───────────────────
            first_close   = price_data['Close'].iloc[0]
            last_close    = price_data['Close'].iloc[-1]
            total_return  = (last_close / first_close - 1) * 100            # %
            years_span    = (price_data.index[-1] - price_data.index[0]).days / 365.25
            annual_return = ((last_close / first_close) ** (1 / years_span) - 1) * 100 if years_span > 0 else None

            # --------------------------
            # Presentación: Nombre de la compañía y Gráfico de Precio Histórico
            # --------------------------
            company_name = info.get("longName", "Nombre no disponible")
            st.markdown(f"# {company_name}")

            st.markdown(f"**🏷️ Sector:** {sector}   |   **🏭 Industria:** {industry}")

            
            st.markdown(f"### 🚨 Datos Principales de {ticker_input}")
            # Mostrar una fila de métricas con los datos clave
            col1, col2, col3, col4, col5, col6, col7= st.columns(7)
            col1.metric("💰 Precio actual", f"${price:.2f}" if price is not None else "N/A")
            col2.metric("🏦 Dividendo Actual", f"${dividend:.2f}" if dividend is not None else "N/A")
            col3.metric("📈 Yield actual", f"{yield_actual:.2f}%" if yield_actual is not None else "N/A")
            col4.metric("📊 PER actual", f"{pe_ratio:.2f}x" if pe_ratio is not None else "N/A")
            col5.metric("🔁 PayOut actual", f"{payout_ratio*100:.2f}%" if payout_ratio is not None else "N/A")
            col6.metric("🧾 EPS actual", f"${eps_actual:.2f}" if eps_actual is not None else "N/A")
            col7.metric("⏳ CAGR del dividendo", f"{cagr_dividend:.2f}%" if cagr_dividend is not None else "N/A")
            # ────────────────────────────────────────────────────────────────
            

            st.subheader("##")
            
            #Gráfico de precio histórico

            st.subheader(f"📈 Precio Histórico de la Acción")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=price_data.index,
                y=price_data['Close'],
                mode='lines+text',
                name='Precio de Cierre',
                line=dict(color=primary_blue),
                text=[f"${y:.2f}" if i == len(price_data['Close']) - 1 else "" for i, y in enumerate(price_data['Close'])],
                textposition="top right",
                showlegend=True
            ))
            fig.update_layout(
                title=f'Precio de la acción ({selected_period}, {interval_selection.lower()})',
                xaxis_title='Fecha',
                yaxis_title='Precio (USD)',
                height=500
            )
            st.plotly_chart(fig, use_container_width=True, key="plotly_chart_price")
            
            st.subheader(f"⚠️ Drawdown Histórico")
            try:
                closing_prices = price_data['Close']
                running_max = closing_prices.cummax()
                drawdown = (closing_prices / running_max - 1) * 100

                fig_dd = go.Figure()
                fig_dd.add_trace(go.Scatter(
                    x=drawdown.index,
                    y=drawdown.values,
                    mode='lines+text',
                    name='Drawdown (%)',
                    line=dict(color='crimson'),
                    text=[f"{val:.1f}%" if i == len(drawdown.values) - 1 else "" for i, val in enumerate(drawdown.values)],
                    textposition="bottom right"
                ))

                fig_dd.update_layout(
                    title="Drawdown del Precio de la Acción",
                    xaxis_title='Fecha',
                    yaxis_title='Drawdown (%)',
                    yaxis=dict(range=[drawdown.min() - 5, 5]),
                    height=450,
                    margin=dict(l=30, r=30, t=60, b=30)
                )
                st.plotly_chart(fig_dd, use_container_width=True)
            except Exception as e:
                st.warning(f"No se pudo calcular el drawdown: {e}")
            # ==========================
            # BLOQUE 2: Valoración por Dividendo
            # ==========================
            st.subheader(f"🧐 Análisis y Valoración para {ticker_input}")

            with st.expander(f"💸 Análisis y Valoración por Dividendo de {ticker_input}"):
                dividends = ticker_data.dividends
                if not dividends.empty:
                    annual_dividends = dividends.resample('Y').sum()
                    annual_dividends.index = annual_dividends.index.year
                    start_year = pd.to_datetime(price_data.index[0]).year
                    end_year = pd.to_datetime(price_data.index[-1]).year
                    annual_dividends = annual_dividends[(annual_dividends.index >= start_year) & (annual_dividends.index <= end_year)]
                    if len(annual_dividends) >= 3:
                        first_value = annual_dividends.iloc[0]
                        penultimate_value = annual_dividends.iloc[-2]
                        n_years = annual_dividends.index[-2] - annual_dividends.index[0]
                        cagr = ((penultimate_value / first_value) ** (1 / n_years) - 1) * 100
                        cagr_text = f"📌 CAGR del dividendo: {cagr:.2f}% anual ({annual_dividends.index[0]}–{annual_dividends.index[-2]})"
                    else:
                        cagr_text = "📌 CAGR del dividendo: No disponible (datos insuficientes)"
                    fig_div = go.Figure()
                    fig_div.add_trace(go.Bar(
                        x=annual_dividends.index,
                        y=annual_dividends.values,
                        name='Dividendo Anual ($)',
                        marker_color=primary_orange,
                        text=[f"${val:.2f}" for val in annual_dividends.values],
                        textposition='outside'
                    ))
                    fig_div.update_layout(
                        title=cagr_text,
                        xaxis_title='Año',
                        yaxis_title='Dividendo ($)',
                        height=450,
                        margin=dict(l=30, r=30, t=60, b=30)
                    )
                    st.plotly_chart(fig_div, use_container_width=True, key="plotly_chart_div")
                    st.markdown("#### Resumen de Dividendos por Año")
                    table_df = pd.DataFrame({ year: f"${annual_dividends.loc[year]:.2f}" for year in annual_dividends.index },
                                            index=["Dividendo ($)"])
                    st.table(table_df)

                st.subheader("#")
                st.subheader(f"♻️ Sostenibilidad del Dividendo")
                try:
                    cashflow = ticker_data.cashflow.transpose()
                    cashflow.index = cashflow.index.year
                    fcf_col = "Free Cash Flow"
                    dividends_col = "Cash Dividends Paid"
                    if fcf_col in cashflow.columns and dividends_col in cashflow.columns:
                        fcf = cashflow[fcf_col]
                        dividends_paid = cashflow[dividends_col]
                        df_fcf = pd.DataFrame({
                            'FCF': fcf,
                            'Dividendos Pagados': dividends_paid.abs()
                        }).dropna()
                        df_fcf['FCF Payout (%)'] = (df_fcf['Dividendos Pagados'] / df_fcf['FCF']) * 100
                        fig_sost = go.Figure()
                        fig_sost.add_trace(go.Bar(
                            x=df_fcf.index,
                            y=df_fcf['FCF'],
                            name='FCF',
                            marker_color=primary_orange,
                            text=df_fcf['FCF'].round(0),
                            textposition='outside'
                        ))
                        fig_sost.add_trace(go.Bar(
                            x=df_fcf.index,
                            y=df_fcf['Dividendos Pagados'],
                            name='Dividendos Pagados',
                            marker_color=primary_blue,
                            text=df_fcf['Dividendos Pagados'].round(0),
                            textposition='outside'
                        ))
                        fig_sost.add_trace(go.Scatter(
                            x=df_fcf.index,
                            y=df_fcf['FCF Payout (%)'],
                            name='FCF Payout (%)',
                            mode='lines+markers+text',
                            yaxis='y2',
                            line=dict(color=primary_pink),
                            text=[f"{val:.0f}%" for val in df_fcf['FCF Payout (%)']],
                            textposition='top right'
                        ))
                        fig_sost.update_layout(
                            title="FCF vs Dividendos Pagados y FCF Payout Ratio",
                            xaxis_title="Año",
                            yaxis_title="Millones USD",
                            yaxis2=dict(
                                title='FCF Payout (%)',
                                overlaying='y',
                                side='right'
                            ),
                            barmode='group',
                            height=500,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )
                        st.plotly_chart(fig_sost, use_container_width=True, key="plotly_chart_sost")
                    else:
                        st.warning("No se encontraron las columnas necesarias para calcular el FCF o los Dividendos.")
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de sostenibilidad: {e}")

                st.subheader(f"📉 Rentabilidad por Dividendo Histórica")
                try:
                    df_yield = price_data[['Close']].copy()
                    df_yield['Año'] = df_yield.index.year
                    dividend_map = annual_dividends.to_dict()
                    df_yield['Dividendo Anual'] = df_yield['Año'].map(dividend_map)
                    df_yield['Yield (%)'] = (df_yield['Dividendo Anual'] / df_yield['Close']) * 100
                    if len(annual_dividends) > 1:
                        max_full_year = annual_dividends.index[-2]
                        df_yield = df_yield[df_yield['Año'] <= max_full_year]
                    avg_yield_div = df_yield['Yield (%)'].mean()
                    max_yield_div = df_yield['Yield (%)'].max()
                    min_yield_div = df_yield['Yield (%)'].min()
                    fig_yield = go.Figure()
                    fig_yield.add_trace(go.Scatter(
                        x=df_yield.index,
                        y=df_yield['Yield (%)'],
                        mode='lines',
                        name='Yield Diario',
                        line=dict(color=primary_pink)
                    ))
                    fig_yield.add_hline(y=avg_yield_div, line=dict(dash='dash', color='gray'),
                                        annotation_text='Promedio', annotation_position='top left')
                    fig_yield.add_hline(y=max_yield_div, line=dict(dash='dot', color='green'),
                                        annotation_text='Máximo', annotation_position='top left')
                    fig_yield.add_hline(y=min_yield_div, line=dict(dash='dot', color='red'),
                                        annotation_text='Mínimo', annotation_position='bottom left')
                    fig_yield.update_layout(
                        title="Rentabilidad por Dividendo (Diaria, filtrada)",
                        xaxis_title='Fecha',
                        yaxis_title='Yield (%)',
                        height=450,
                        margin=dict(l=30, r=30, t=60, b=30)
                    )
                    st.plotly_chart(fig_yield, use_container_width=True, key="plotly_chart_yield")
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de yield diario: {e}")
                
                st.subheader(f"💎 Método Geraldine Weiss: Datos, Resumen y Gráfico")
                try:
                    dividends = ticker_data.dividends
                    price_data_diario = ticker_data.history(period=selected_period, interval="1d")
                    if dividends.empty or price_data_diario.empty:
                        st.warning("No hay datos suficientes para calcular el Método Geraldine Weiss.")
                    else:
                        annual_dividends_raw = dividends.resample("Y").sum()
                        annual_dividends_raw.index = annual_dividends_raw.index.year
                        start_year = pd.to_datetime(price_data.index[0]).year
                        end_year = pd.to_datetime(price_data.index[-1]).year
                        annual_dividends = annual_dividends_raw[(annual_dividends_raw.index >= start_year) & (annual_dividends_raw.index <= end_year)]
                        if len(annual_dividends) >= 3:
                            first_value = annual_dividends.iloc[0]
                            penultimate_value = annual_dividends.iloc[-2]
                            n_years = annual_dividends.index[-2] - annual_dividends.index[0]
                            cagr_gw = ((penultimate_value / first_value) ** (1 / n_years) - 1) * 100
                        else:
                            cagr_gw = None
                        current_year = pd.Timestamp.today().year
                        def ajustar_dividendo(year):
                            if (year == current_year) and (cagr_gw is not None) and ((year - 1) in annual_dividends.index):
                                return annual_dividends[year - 1] * (1 + cagr_gw/100)
                            else:
                                return annual_dividends.get(year, None)
                        
                        monthly_data = price_data_diario.resample("M").last().reset_index()
                        monthly_data['Año'] = monthly_data['Date'].dt.year
                        monthly_data['Mes'] = monthly_data['Date'].dt.strftime("%B")
                        monthly_data.rename(columns={'Close': 'Precio'}, inplace=True)
                        monthly_data['Dividendo Anual'] = monthly_data['Año'].apply(ajustar_dividendo)
                        monthly_data['Yield'] = monthly_data['Dividendo Anual'] / monthly_data['Precio']
                        overall_yield_min = monthly_data['Yield'].min()
                        overall_yield_max = monthly_data['Yield'].max()
                        monthly_data['Precio Sobrevalorado'] = monthly_data['Dividendo Anual'] / overall_yield_min
                        monthly_data['Precio Infravalorado'] = monthly_data['Dividendo Anual'] / overall_yield_max
                        monthly_data = monthly_data.sort_values(by='Date')
                        valor_infravalorado = monthly_data.iloc[-1]['Precio Infravalorado']
                        df_tabla = monthly_data[['Año', 'Mes', 'Precio', 'Dividendo Anual', 'Yield', 'Precio Sobrevalorado', 'Precio Infravalorado']]
                        ultimo_año = df_tabla['Año'].max()
                        last_dividend = df_tabla[df_tabla['Año'] == ultimo_año]['Dividendo Anual'].iloc[-1]
                        current_price_gw = ticker_data.info.get('currentPrice', price_data_diario['Close'].iloc[-1])
                        st.markdown("### 🚨 Datos Clave")
                        gw_cols = st.columns(7)
                        gw_cols[0].metric("💰 Precio Actual", f"${current_price_gw:.2f}")
                        gw_cols[1].metric("🏦 Dividendo Anual", f"${last_dividend:.2f}")
                        gw_cols[2].metric("📊 CAGR Dividendo", f"{cagr_gw:.2f}%" if cagr_gw is not None else "N/A")
                        gw_cols[3].metric("📈 Yield Máximo", f"{overall_yield_max:.2%}")
                        gw_cols[4].metric("📉 Yield Mínimo", f"{overall_yield_min:.2%}")
                        gw_cols[5].metric("🚫 Sobrevalorado", f"${last_dividend/overall_yield_min:.2f}")
                        gw_cols[6].metric("✅ Infravalorado", f"${last_dividend/overall_yield_max:.2f}")
                        annual_years = sorted(monthly_data['Año'].unique())
                        annual_bands = []
                        for year in annual_years:
                            div_anual = ajustar_dividendo(year)
                            if div_anual is not None:
                                sobre = div_anual / overall_yield_min
                                infraval = div_anual / overall_yield_max
                                annual_bands.append({
                                    "Año": year,
                                    "Dividendo Anual": div_anual,
                                    "Precio Sobrevalorado": sobre,
                                    "Precio Infravalorado": infraval
                                })
                        df_annual = pd.DataFrame(annual_bands)
                        x_sobre = []
                        y_sobre = []
                        x_infra = []
                        y_infra = []
                        for i, row in df_annual.iterrows():
                            year = int(row["Año"])
                            start = pd.to_datetime(f"{year}-01-01")
                            if year != df_annual["Año"].max():
                                end = pd.to_datetime(f"{year+1}-01-01")
                            else:
                                end = price_data_diario.index[-1]
                            x_sobre.extend([start, end])
                            y_sobre.extend([row["Precio Sobrevalorado"], row["Precio Sobrevalorado"]])
                            x_infra.extend([start, end])
                            y_infra.extend([row["Precio Infravalorado"], row["Precio Infravalorado"]])
                        fig_gw = go.Figure()
                        fig_gw.add_trace(go.Scatter(
                            x=price_data_diario.index,
                            y=price_data_diario['Close'],
                            mode='lines',
                            name='Precio Histórico Diario',
                            line=dict(color="hotpink")
                        ))
                        fig_gw.add_trace(go.Scatter(
                            x=x_sobre,
                            y=y_sobre,
                            mode='lines',
                            name='Precio Sobrevalorado',
                            line=dict(color="darkorange", dash="dot")
                        ))
                        fig_gw.add_trace(go.Scatter(
                            x=x_infra,
                            y=y_infra,
                            mode='lines',
                            name='Precio Infravalorado',
                            line=dict(color="deepskyblue", dash="dot")
                        ))
                        fig_gw.add_trace(go.Scatter(
                            x=[price_data_diario.index[-1]],
                            y=[current_price_gw],
                            mode='markers+text',
                            name='Precio Actual',
                            marker=dict(color="hotpink", size=10),
                            text=[f"${current_price_gw:.2f}"],
                            textposition="top center"
                        ))
                        fig_gw.update_layout(
                            title=f"Precio Histórico Diario, Bandas y Precio Actual - {ticker_input}",
                            xaxis_title="Fecha",
                            yaxis_title="Precio ($)",
                            height=500,
                            margin=dict(l=20, r=20, t=60, b=40)
                        )
                        st.plotly_chart(fig_gw, use_container_width=True)
                        st.subheader(f"Datos para el Gráfico de Geraldine Weiss")
                        st.dataframe(df_tabla)
                except Exception as e:
                    st.error(f"No se pudo generar el gráfico del Método Geraldine Weiss: {e}")

            # ==========================
            # BLOQUE 3: Valoración por Múltiplos
            # ==========================
            with st.expander(f"💱 Análisis y Valoración por Múltiplos de {ticker_input}"):
                st.subheader(f"💵 Evolución de la Deuda")
                try:
                    bs = ticker_data.balance_sheet.transpose()
                    bs.index = bs.index.year

                    if "Total Debt" in bs.columns:
                        total_debt = bs["Total Debt"]
                    elif "Long Term Debt" in bs.columns:
                        total_debt = bs["Long Term Debt"]
                    else:
                        total_debt = None

                    if "Cash And Cash Equivalents" in bs.columns:
                        cash = bs["Cash And Cash Equivalents"]
                    elif "Cash" in bs.columns:
                        cash = bs["Cash"]
                    else:
                        cash = None

                    if total_debt is not None and cash is not None:
                        net_debt = total_debt - cash
                    else:
                        net_debt = None

                    cf = ticker_data.cashflow.transpose()
                    cf.index = cf.index.year
                    if "Free Cash Flow" in cf.columns:
                        fcf = cf["Free Cash Flow"]
                    else:
                        fcf = None

                    if net_debt is not None and fcf is not None:
                        debt_to_fcf = net_debt / fcf
                    else:
                        debt_to_fcf = None

                    df_deuda = pd.DataFrame()
                    if fcf is not None:
                        df_deuda['FCF'] = fcf
                    if net_debt is not None:
                        df_deuda['Deuda Neta'] = net_debt
                    if debt_to_fcf is not None:
                        df_deuda['Deuda Neta/FCF'] = debt_to_fcf

                    fig_deuda = go.Figure()
                    if 'FCF' in df_deuda.columns:
                        fig_deuda.add_trace(go.Bar(
                            x=df_deuda.index,
                            y=df_deuda['FCF'],
                            name='FCF',
                            marker_color=primary_orange,
                            text=df_deuda['FCF'].round(0),
                            textposition='outside'
                        ))
                    if 'Deuda Neta' in df_deuda.columns:
                        fig_deuda.add_trace(go.Bar(
                            x=df_deuda.index,
                            y=df_deuda['Deuda Neta'],
                            name='Deuda Neta',
                            marker_color=primary_blue,
                            text=df_deuda['Deuda Neta'].round(0),
                            textposition='outside'
                        ))
                    if 'Deuda Neta/FCF' in df_deuda.columns:
                        fig_deuda.add_trace(go.Scatter(
                            x=df_deuda.index,
                            y=df_deuda['Deuda Neta/FCF'],
                            name='Deuda Neta/FCF',
                            mode='lines+markers+text',
                            yaxis='y2',
                            line=dict(color=primary_pink),
                            text=[f"{val:.2f}" for val in df_deuda['Deuda Neta/FCF']],
                            textposition='top right'
                        ))

                    fig_deuda.update_layout(
                        title="Evolución de Deuda, FCF y Deuda Neta/FCF",
                        xaxis_title="Año",
                        yaxis_title="Valor (Millones USD)",
                        yaxis2=dict(
                            title='Deuda Neta/FCF',
                            overlaying='y',
                            side='right'
                        ),
                        barmode='group',
                        height=500,
                        margin=dict(l=30, r=30, t=60, b=30)
                    )

                    st.plotly_chart(fig_deuda, use_container_width=True, key="plotly_chart_deuda")
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de deuda: {e}")

                st.subheader(f"📈 Histórico del PER, EPS y Precio")
                try:
                    st.subheader(f"📌 El PER actual es de {pe_ratio:.2f}x")
                    income_statement = ticker_data.financials
                    if "Basic EPS" not in income_statement.index:
                        st.warning("No se encontró 'Basic EPS' en el Income Statement para calcular el PER.")
                    else:
                        eps_series = income_statement.loc["Basic EPS"]
                        eps_series.index = pd.to_datetime(eps_series.index).year
                        eps_series = eps_series.sort_index()
                        price_yearly = price_data.resample('Y').last()['Close']
                        price_yearly.index = price_yearly.index.year
                        price_yearly = price_yearly.sort_index()
                        common_years = eps_series.index.intersection(price_yearly.index)
                        eps_series = eps_series.loc[common_years]
                        price_yearly = price_yearly.loc[common_years]
                        per_series = price_yearly / eps_series
                        per_series = per_series.replace([float('inf'), -float('inf')], None).dropna()
                        df_per = pd.DataFrame({
                            "EPS": eps_series,
                            "Precio": price_yearly,
                            "PER": per_series
                        })
                        fig_combined = go.Figure()
                        fig_combined.add_trace(go.Bar(
                            x=df_per.index,
                            y=df_per["EPS"],
                            name="EPS",
                            marker_color=primary_orange,
                            text=df_per["EPS"].round(2),
                            textposition='outside'
                        ))
                        fig_combined.add_trace(go.Bar(
                            x=df_per.index,
                            y=df_per["Precio"],
                            name="Precio",
                            marker_color=primary_blue,
                            text=df_per["Precio"].round(2),
                            textposition='outside'
                        ))
                        fig_combined.add_trace(go.Scatter(
                            x=df_per.index,
                            y=df_per["PER"],
                            name="PER",
                            mode="lines+markers+text",
                            yaxis="y2",
                            line=dict(color=primary_pink),
                            text=[f"{val:.2f}" for val in df_per["PER"]],
                            textposition='top right'
                        ))
                        fig_combined.update_layout(
                            title="Histórico del EPS, Precio y PER",
                            xaxis_title="Año",
                            yaxis=dict(title="EPS / Precio"),
                            yaxis2=dict(title="PER", overlaying="y", side="right"),
                            barmode="group",
                            height=450,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )
                        st.plotly_chart(fig_combined, use_container_width=True, key="plotly_chart_per")
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico combinado del PER: {e}")
                
                st.subheader(f"📐 Evolución de EV, EBITDA y EV/EBITDA")
                try:
                    # Obtener EBITDA a partir del Income Statement
                    income = ticker_data.financials.transpose()
                    income.index = income.index.year
                    if "EBITDA" in income.columns:
                        ebitda = income["EBITDA"]
                    else:
                        ebitda = None

                    # Obtener deuda total y caja a partir del Balance
                    bs = ticker_data.balance_sheet.transpose()
                    bs.index = bs.index.year
                    if "Total Debt" in bs.columns:
                        total_debt = bs["Total Debt"]
                    elif "Long Term Debt" in bs.columns:
                        total_debt = bs["Long Term Debt"]
                    else:
                        total_debt = None

                    if "Cash And Cash Equivalents" in bs.columns:
                        cash = bs["Cash And Cash Equivalents"]
                    elif "Cash" in bs.columns:
                        cash = bs["Cash"]
                    else:
                        cash = None

                    # Calcular la deuda neta (serie completa)
                    if total_debt is not None and cash is not None:
                        net_debt_series = total_debt - cash
                    else:
                        net_debt_series = None

                    market_cap = ticker_data.info.get("marketCap", None)

                    # Calcular el EV/EBITDA "actual" usando el último año disponible
                    if ebitda is not None and net_debt_series is not None and market_cap is not None:
                        last_year = bs.index.max()
                        try:
                            last_debt = total_debt.loc[last_year]
                            last_cash = cash.loc[last_year]
                            net_debt_current = last_debt - last_cash
                            ev_current = market_cap + net_debt_current
                            last_ebitda = ebitda.loc[last_year]
                            current_ev_ebitda = ev_current / last_ebitda if last_ebitda != 0 else None
                        except Exception as ex:
                            current_ev_ebitda = None
                    else:
                        current_ev_ebitda = None

                    # Mostrar el EV/EBITDA actual (similar a lo que haces con el PER)
                    st.subheader(f"📌 El EV/EBITDA actual es de {current_ev_ebitda:.2f}" if current_ev_ebitda is not None else "EV/EBITDA actual no disponible")
                    
                    # Calcular el ratio EV/EBITDA a partir de la serie completa
                    if total_debt is not None and cash is not None:
                        net_debt = total_debt - cash
                    else:
                        net_debt = None

                    if market_cap is not None and net_debt is not None:
                        ev = market_cap + net_debt
                    else:
                        ev = None

                    if ev is not None and ebitda is not None:
                        ev_ebitda = ev / ebitda
                    else:
                        ev_ebitda = None

                    df_ev = pd.DataFrame()
                    if ebitda is not None:
                        df_ev["EBITDA"] = ebitda
                    if ev is not None:
                        df_ev["EV"] = ev
                    if ev_ebitda is not None:
                        df_ev["EV/EBITDA"] = ev_ebitda

                    fig_ev = go.Figure()
                    if "EBITDA" in df_ev.columns:
                        fig_ev.add_trace(go.Bar(
                            x=df_ev.index,
                            y=df_ev["EBITDA"],
                            name="EBITDA",
                            marker_color=primary_orange,
                            text=df_ev["EBITDA"].round(0),
                            textposition='outside'
                        ))
                    if "EV" in df_ev.columns:
                        fig_ev.add_trace(go.Bar(
                            x=df_ev.index,
                            y=df_ev["EV"],
                            name="EV",
                            marker_color=primary_blue,
                            text=df_ev["EV"].round(0),
                            textposition='outside'
                        ))
                    if "EV/EBITDA" in df_ev.columns:
                        fig_ev.add_trace(go.Scatter(
                            x=df_ev.index,
                            y=df_ev["EV/EBITDA"],
                            name="EV/EBITDA",
                            mode="lines+markers+text",
                            yaxis="y2",
                            line=dict(color=primary_pink),
                            text=[f"{val:.2f}" for val in df_ev["EV/EBITDA"]],
                            textposition='top right'
                        ))
                    fig_ev.update_layout(
                        title="Evolución de EV, EBITDA y EV/EBITDA",
                        xaxis_title="Año",
                        yaxis_title="Valor (USD)",
                        yaxis2=dict(title="EV/EBITDA", overlaying="y", side="right"),
                        barmode="group",
                        height=500,
                        margin=dict(l=30, r=30, t=60, b=30)
                    )
                    st.plotly_chart(fig_ev, use_container_width=True, key="plotly_chart_ev")
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de EV y EBITDA: {e}")


            # ==========================
            # BLOQUE 4: Análisis Fundamental - Balance
            # ==========================
            with st.expander(f"⚖️ Análisis Fundamental - Balance de {ticker_input}"):
                st.subheader("🏢 Evolución de Activos Totales y Activos Corrientes")
                try:
                    bs_t = ticker_data.balance_sheet.transpose()
                    bs_t.index = bs_t.index.year
                    if "Total Assets" not in bs_t.columns:
                        st.warning("No se encontró 'Total Assets' en el Balance Sheet.")
                    else:
                        total_assets = bs_t["Total Assets"]
                        possible_current_assets = ["Current Assets", "Total Current Assets"]
                        found_current_assets = None
                        for key in possible_current_assets:
                            if key in bs_t.columns:
                                found_current_assets = key
                                break
                        if found_current_assets is None:
                            st.warning("No se encontró información sobre Activos Corrientes.")
                        else:
                            current_assets = bs_t[found_current_assets]
                            df_activos = pd.DataFrame({
                                "Total Assets": total_assets,
                                found_current_assets: current_assets
                            })
                            fig_activos = go.Figure()
                            fig_activos.add_trace(go.Bar(
                                x=bs_t.index,
                                y=total_assets,
                                name="Total Assets",
                                marker_color=primary_blue,
                                text=[f"${val:,.0f}" for val in total_assets],
                                textposition='outside'
                            ))
                            fig_activos.add_trace(go.Bar(
                                x=bs_t.index,
                                y=current_assets,
                                name=found_current_assets,
                                marker_color=primary_orange,
                                text=[f"${val:,.0f}" for val in current_assets],
                                textposition='outside'
                            ))
                            fig_activos.update_layout(
                                title="Evolución de Activos Totales y Activos Corrientes",
                                xaxis_title="Año",
                                yaxis_title="Valor (USD)",
                                barmode="group",
                                height=450,
                                margin=dict(l=30, r=30, t=60, b=30)
                            )
                            st.plotly_chart(fig_activos, use_container_width=True, key="plotly_chart_activos")
                            st.markdown("#### Datos de Activos")
                            st.dataframe(df_activos)
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de activos: {e}")
                
                #-------------------------------------------
                #Pasivos
                #-------------------------------------------

                # ──────────────────────────────────────────────────────────────
                # 💳  Evolución de Pasivos Totales y Pasivos Corrientes
                #     +  Deuda Total vs Deuda Neta
                # ──────────────────────────────────────────────────────────────
                st.subheader("💳 Evolución de Pasivos Totales y Pasivos Corrientes Totales")
                try:
                    bs_t = ticker_data.balance_sheet.transpose()
                    bs_t.index = bs_t.index.year

                    # ---------- Pasivos totales / corrientes -------------------
                    if "Total Liabilities Net Minority Interest" not in bs_t.columns:
                        st.warning("No se encontró 'Total Liabilities Net Minority Interest' en el Balance Sheet.")
                    else:
                        total_liabilities = bs_t["Total Liabilities Net Minority Interest"]

                        # intento de 2 posibles nombres para pasivo corriente
                        possible_current = ["Current Liabilities", "Total Current Liabilities"]
                        found_current = next((c for c in possible_current if c in bs_t.columns), None)

                        if found_current is None:
                            st.warning("No se encontró información sobre Pasivos Corrientes Totales.")
                        else:
                            current_liabilities = bs_t[found_current]

                            df_pasivos = pd.DataFrame({
                                "Total Liabilities": total_liabilities,
                                found_current: current_liabilities
                            })

                            fig_pasivos = go.Figure()
                            fig_pasivos.add_trace(go.Bar(
                                x=df_pasivos.index, y=df_pasivos["Total Liabilities"],
                                name="Total Liabilities", marker_color=primary_blue,
                                text=[f"${v:,.0f}" for v in df_pasivos["Total Liabilities"]],
                                textposition="outside"
                            ))
                            fig_pasivos.add_trace(go.Bar(
                                x=df_pasivos.index, y=df_pasivos[found_current],
                                name=found_current, marker_color=primary_orange,
                                text=[f"${v:,.0f}" for v in df_pasivos[found_current]],
                                textposition="outside"
                            ))

                            fig_pasivos.update_layout(
                                title="Evolución de Pasivos Totales y Pasivos Corrientes Totales",
                                xaxis_title="Año", yaxis_title="Valor (USD)",
                                barmode="group", height=450,
                                margin=dict(l=30, r=30, t=60, b=30)
                            )
                            st.plotly_chart(fig_pasivos, use_container_width=True, key="plotly_pasivos")
                            st.markdown("#### Datos de Pasivos")
                            st.dataframe(df_pasivos)

                    # ---------- Deuda Total vs Deuda Neta -----------------------
                    st.subheader("💰 Evolución de Deuda Total vs Deuda Neta")
                    debt_cols = [c for c in ["Total Debt", "Net Debt"] if c in bs_t.columns]
                    if len(debt_cols) < 2:
                        st.warning("No se encontraron ambos campos 'Total Debt' y 'Net Debt' en el Balance.")
                    else:
                        total_debt = bs_t["Total Debt"]
                        net_debt   = bs_t["Net Debt"]

                        df_debt = pd.DataFrame({
                            "Total Debt": total_debt,
                            "Net Debt":   net_debt
                        })

                        fig_debt = go.Figure()
                        fig_debt.add_trace(go.Bar(
                            x=df_debt.index, y=df_debt["Total Debt"],
                            name="Total Debt", marker_color=primary_blue,
                            text=[f"${v:,.0f}" for v in df_debt["Total Debt"]],
                            textposition="outside"
                        ))
                        fig_debt.add_trace(go.Bar(
                            x=df_debt.index, y=df_debt["Net Debt"],
                            name="Net Debt", marker_color=primary_pink,
                            text=[f"${v:,.0f}" for v in df_debt["Net Debt"]],
                            textposition="outside"
                        ))

                        fig_debt.update_layout(
                            title="Evolución de Deuda Total y Deuda Neta",
                            xaxis_title="Año", yaxis_title="Valor (USD)",
                            barmode="group", height=450,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )
                        st.plotly_chart(fig_debt, use_container_width=True, key="plotly_debt")
                        st.markdown("#### Datos de Deuda")
                        st.dataframe(df_debt)

                except Exception as e:
                    st.warning(f"No se pudo generar los gráficos de pasivos/deuda: {e}")

                #-------------------------------------------
                #Patrimonio
                #-------------------------------------------

                st.subheader("💼 Evolución del Patrimonio")
                try:
                    bs_t = ticker_data.balance_sheet.transpose()
                    bs_t.index = bs_t.index.year
                    if "Total Equity Gross Minority Interest" not in bs_t.columns:
                        st.warning("No se encontró 'Total Equity Gross Minority Interest' en el Balance Sheet.")
                    else:
                        total_equity = bs_t["Total Equity Gross Minority Interest"]
                        df_capital = pd.DataFrame({"Total Equity": total_equity})
                        fig_capital = go.Figure()
                        fig_capital.add_trace(go.Bar(
                            x=total_equity.index,
                            y=total_equity.values,
                            name="Total Equity Gross Minority Interest",
                            marker_color=primary_orange,
                            text=[f"${val:,.0f}" for val in total_equity.values],
                            textposition='outside'
                        ))
                        fig_capital.update_layout(
                            title="Evolución del Patrimonio",
                            xaxis_title="Año",
                            yaxis_title="Valor (USD)",
                            height=450,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )
                        st.plotly_chart(fig_capital, use_container_width=True, key="plotly_chart_capital")
                        st.markdown("#### Datos del Patrimonio")
                        st.dataframe(df_capital)
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de evolución del Capital: {e}")
                
                st.subheader("⏳ Evolución del Balance")
                try:
                    bs_t = ticker_data.balance_sheet.transpose()
                    bs_t.index = bs_t.index.year
                    required_cols = ["Total Assets", "Total Liabilities Net Minority Interest", "Total Equity Gross Minority Interest"]
                    missing = [col for col in required_cols if col not in bs_t.columns]
                    if missing:
                        st.warning(f"No se encontraron los siguientes datos en el Balance Sheet: {', '.join(missing)}")
                    else:
                        total_assets = bs_t["Total Assets"]
                        total_liabilities = bs_t["Total Liabilities Net Minority Interest"]
                        total_equity = bs_t["Total Equity Gross Minority Interest"]
                        df_balance = pd.DataFrame({
                            "Total Assets": total_assets,
                            "Total Liabilities": total_liabilities,
                            "Total Equity": total_equity
                        })
                        fig_balance = go.Figure()
                        fig_balance.add_trace(go.Scatter(
                            x=bs_t.index,
                            y=total_assets,
                            mode="lines+markers",
                            name="Total Assets",
                            line=dict(color=primary_blue)
                        ))
                        fig_balance.add_trace(go.Scatter(
                            x=bs_t.index,
                            y=total_liabilities,
                            mode="lines+markers",
                            name="Total Liabilities",
                            line=dict(color=primary_orange)
                        ))
                        fig_balance.add_trace(go.Scatter(
                            x=bs_t.index,
                            y=total_equity,
                            mode="lines+markers",
                            name="Total Equity",
                            line=dict(color=primary_pink)
                        ))
                        fig_balance.update_layout(
                            title="Evolución del Balance: Activos, Pasivos y Capital",
                            xaxis_title="Año",
                            yaxis_title="Valor (USD)",
                            height=450,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )
                        st.plotly_chart(fig_balance, use_container_width=True, key="plotly_chart_balance")
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico del Balance: {e}")
                
                st.markdown("#### Balance en detalle")
                st.dataframe(ticker_data.balance_sheet.iloc[::-1], height=300)


             # BLOQUE 5: Análisis Fundamental - Estado de Resultados
            # ==========================
            with st.expander(f"📝 Análisis Fundamental - Estado de Resultados de {ticker_input}"):
                st.subheader(f"📝 Evolución de los Ingresos")
                try:
                    income = ticker_data.financials.transpose()
                    income.index = income.index.year

                    if "Total Revenue" not in income.columns or "Gross Profit" not in income.columns or "Operating Income" not in income.columns:
                        st.warning("No se encontraron suficientes datos en el Estado de Resultados para generar el gráfico de ingresos.")
                    else:
                        total_revenue = income["Total Revenue"]
                        gross_profit = income["Gross Profit"]
                        operating_income = income["Operating Income"]

                        if "Net Income" in income.columns:
                            net_income = income["Net Income"]
                        elif "Net Income from Continuing Operation Net Minority Interest" in income.columns:
                            net_income = income["Net Income from Continuing Operation Net Minority Interest"]
                        else:
                            net_income = None

                        df_income = pd.DataFrame({
                            "Total Revenue": total_revenue,
                            "Gross Profit": gross_profit,
                            "Operating Income": operating_income
                        })
                        if net_income is not None:
                            df_income["Net Income"] = net_income

                        primary_gold = "gold"

                        fig_income = go.Figure()
                        fig_income.add_trace(go.Bar(
                            x=df_income.index,
                            y=df_income["Total Revenue"],
                            name="Total Revenue",
                            marker_color=primary_blue,
                            text=[f"${val:,.0f}" for val in df_income["Total Revenue"]],
                            textposition='outside'
                        ))
                        fig_income.add_trace(go.Bar(
                            x=df_income.index,
                            y=df_income["Gross Profit"],
                            name="Gross Profit",
                            marker_color=primary_orange,
                            text=[f"${val:,.0f}" for val in df_income["Gross Profit"]],
                            textposition='outside'
                        ))
                        fig_income.add_trace(go.Bar(
                            x=df_income.index,
                            y=df_income["Operating Income"],
                            name="Operating Income",
                            marker_color=primary_pink,
                            text=[f"${val:,.0f}" for val in df_income["Operating Income"]],
                            textposition='outside'
                        ))
                        if "Net Income" in df_income.columns:
                            fig_income.add_trace(go.Bar(
                                x=df_income.index,
                                y=df_income["Net Income"],
                                name="Net Income",
                                marker_color=primary_gold,
                                text=[f"${val:,.0f}" for val in df_income["Net Income"]],
                                textposition='outside'
                            ))

                        fig_income.update_layout(
                            title="Evolución de los Ingresos",
                            xaxis_title="Año",
                            yaxis_title="Valor (USD)",
                            barmode="group",
                            height=450,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )

                        st.plotly_chart(fig_income, use_container_width=True)
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de Evolución de los Ingresos: {e}")

                st.subheader(f"📝 Evolución de Márgenes")

                try:
                    income = ticker_data.financials.transpose()
                    income.index = income.index.year

                    if 'Total Revenue' in income.columns and 'Gross Profit' in income.columns:
                        ingresos = income['Total Revenue']
                        bruto = income['Gross Profit']
                        margen_bruto = (bruto / ingresos * 100).round(1)
                    else:
                        margen_bruto = None

                    if 'Operating Income' in income.columns:
                        operativo = income['Operating Income']
                        margen_operativo = (operativo / ingresos * 100).round(1)
                    else:
                        margen_operativo = None

                    if 'Net Income' in income.columns:
                        neto = income['Net Income']
                        margen_neto = (neto / ingresos * 100).round(1)
                    else:
                        margen_neto = None

                    fig = go.Figure()
                    if margen_bruto is not None:
                        fig.add_trace(go.Scatter(x=margen_bruto.index, y=margen_bruto.values,
                                                name="Margen Bruto (%)", mode="lines+markers",
                                                line=dict(color=primary_blue)))
                    if margen_operativo is not None:
                        fig.add_trace(go.Scatter(x=margen_operativo.index, y=margen_operativo.values,
                                                name="Margen Operativo (%)", mode="lines+markers",
                                                line=dict(color=primary_orange)))
                    if margen_neto is not None:
                        fig.add_trace(go.Scatter(x=margen_neto.index, y=margen_neto.values,
                                                name="Margen Neto (%)", mode="lines+markers",
                                                line=dict(color=primary_pink)))

                    fig.update_layout(
                        title="Evolución de Márgenes (% sobre ventas)",
                        xaxis_title="Año",
                        yaxis_title="% Margen",
                        height=450,
                        margin=dict(l=30, r=30, t=60, b=30)
                    )

                    st.plotly_chart(fig, use_container_width=True)

                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de márgenes: {e}")
                
                st.subheader(f"⏳ Evolución del EPS")
                try:
                    # Usamos el EPS Actual obtenido anteriormente
                    if eps_actual is not None:
                        st.subheader(f"📌 El EPS actual es del {eps_actual:.2f}")
                    else:
                        st.warning("EPS actual no disponible.")

                    # Continuamos con la generación del gráfico de evolución del EPS (usando "Diluted EPS" si existe)
                    income = ticker_data.financials.transpose()
                    income.index = income.index.year

                    if "Diluted EPS" not in income.columns:
                        st.warning("No se encontró 'Diluted EPS' en el Estado de Resultados para este ticker.")
                    else:
                        diluted_eps = income["Diluted EPS"].sort_index()

                        fig_eps = go.Figure()
                        fig_eps.add_trace(go.Bar(
                            x=diluted_eps.index,
                            y=diluted_eps.values,
                            name="Diluted EPS",
                            marker_color=primary_orange,
                            text=[f"${val:.2f}" for val in diluted_eps.values],
                            textposition='outside'
                        ))

                        fig_eps.update_layout(
                            title="Evolución del Diluted EPS",
                            xaxis_title="Año",
                            yaxis_title="Diluted EPS (USD)",
                            height=450,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )

                        st.plotly_chart(fig_eps, use_container_width=True, key="plotly_chart_eps")
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de Diluted EPS: {e}")

                
                st.subheader(f"🔄 Evolución de Acciones en Circulación")

                try:
                    bs = ticker_data.balance_sheet
                    if "Ordinary Shares Number" not in bs.index:
                        st.warning("No se encontró 'Ordinary Shares Number' en el Balance Sheet para este ticker.")
                    else:
                        ordinary_shares = bs.loc["Ordinary Shares Number"]
                        ordinary_shares = ordinary_shares.dropna()
                        ordinary_shares.index = pd.to_datetime(ordinary_shares.index)
                        ordinary_shares = ordinary_shares.sort_index()
                        ordinary_shares_yearly = ordinary_shares.resample("Y").last()
                        ordinary_shares_yearly = ordinary_shares_yearly.dropna()
                        ordinary_shares_yearly.index = ordinary_shares_yearly.index.year

                        if ordinary_shares_yearly.empty:
                            st.warning("No hay datos de acciones en circulación disponibles después de filtrar los valores faltantes.")
                        else:
                            fig_shares = go.Figure()
                            fig_shares.add_trace(go.Bar(
                                x=ordinary_shares_yearly.index,
                                y=ordinary_shares_yearly.values,
                                name="Acciones en Circulación",
                                marker_color=primary_blue,
                                text=[f"{int(val):,}" for val in ordinary_shares_yearly.values],
                                textposition='outside'
                            ))

                            fig_shares.update_layout(
                                title="Evolución de Acciones en Circulación",
                                xaxis_title="Año",
                                yaxis_title="Acciones en Circulación",
                                height=450,
                                margin=dict(l=30, r=30, t=60, b=30)
                            )

                            st.plotly_chart(fig_shares, use_container_width=True)

                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de Acciones en Circulación: {e}")

                st.markdown("#### Estado de Resultados en detalle")
                # Se muestra la tabla tal como viene de YahooFinance (filas = cuentas, columnas = fechas)
                st.dataframe(ticker_data.financials.iloc[::-1], height=300)

            # ==========================
            # BLOQUE 6: Estado de Flujo de Efectivo
            # ==========================
            with st.expander(f"💵 Análisis Fundamental - Estado de Flujo de Efectivo de {ticker_input}"):
                cf = ticker_data.cashflow
                cf_t = cf.transpose()
                cf_t.index = pd.to_datetime(cf_t.index, format="%m/%d/%Y", errors="coerce")
                cf_t = cf_t.dropna(subset=[cf_t.columns[0]])
                cf_t.index = cf_t.index.year

                st.subheader("🛒 Flujo de Caja: Operating CF, CaPex y FCF (%)")
                try:
                    cf = ticker_data.cashflow.transpose()
                    cf.index = pd.to_datetime(cf.index, format="%m/%d/%Y", errors="coerce")
                    cf = cf.dropna(subset=[cf.columns[0]])
                    cf.index = cf.index.year
                    if "Operating Cash Flow" not in cf.columns or "Capital Expenditure" not in cf.columns:
                        st.warning("No se encontraron 'Operating Cash Flow' y/o 'Capital Expenditure' en el Flujo de Efectivo.")
                    else:
                        op_cf = cf["Operating Cash Flow"]
                        capex = cf["Capital Expenditure"]
                        adj_capex = -1 * capex
                        fcf = op_cf - adj_capex
                        fcf_pct = (fcf / op_cf) * 100
                        df_cf = cf.copy()
                        df_cf["FCF"] = fcf
                        df_cf["FCF (%)"] = fcf_pct
                        fig_cf = go.Figure()
                        fig_cf.add_trace(go.Bar(
                            x=cf.index,
                            y=op_cf,
                            name="Operating Cash Flow",
                            marker_color=primary_blue,
                            text=[f"${val:,.0f}" for val in op_cf],
                            textposition='outside'
                        ))
                        fig_cf.add_trace(go.Bar(
                            x=cf.index,
                            y=adj_capex,
                            name="Capital Expenditure (abs)",
                            marker_color=primary_orange,
                            text=[f"${val:,.0f}" for val in adj_capex],
                            textposition='outside'
                        ))
                        fig_cf.add_trace(go.Scatter(
                            x=cf.index,
                            y=fcf_pct,
                            name="FCF (%)",
                            mode="lines+markers+text",
                            yaxis="y2",
                            line=dict(color=primary_pink),
                            text=[f"{val:.2f}%" for val in fcf_pct],
                            textposition="top right"
                        ))
                        fig_cf.update_layout(
                            title="Flujo de Caja: Operating CF, CaPex y FCF (%)",
                            xaxis_title="Año",
                            yaxis=dict(title="Valores (USD)"),
                            yaxis2=dict(title="FCF (%)", overlaying="y", side="right"),
                            barmode="group",
                            height=450,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )
                        st.plotly_chart(fig_cf, use_container_width=True, key="plotly_chart_cf")
                        
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico combinado: {e}")

                st.subheader("💳 Emisión de Deuda")
                try:
                    key_issuance = "Issuance Of Debt"
                    if key_issuance not in cf_t.columns:
                        st.warning(f"No se encontró '{key_issuance}' en el Flujo de Efectivo.")
                    else:
                        issuance = cf_t[key_issuance]
                        issuance = pd.to_numeric(issuance, errors='coerce')
                        fig_issuance = go.Figure()
                        fig_issuance.add_trace(go.Bar(
                            x=cf_t.index,
                            y=issuance,
                            name=key_issuance,
                            marker_color=primary_blue,
                            text=[f"${val:,.0f}" for val in issuance],
                            textposition='outside'
                        ))
                        x_vals = np.array(cf_t.index, dtype=float)
                        y_vals = np.array(issuance, dtype=float)
                        slope, intercept = np.polyfit(x_vals, y_vals, 1)
                        trend = slope * x_vals + intercept
                        fig_issuance.add_trace(go.Scatter(
                            x=cf_t.index,
                            y=trend,
                            mode="lines",
                            name="Tendencia",
                            line=dict(color="hotpink", dash="dash")
                        ))
                        fig_issuance.update_layout(
                            title="Emisión de Deuda",
                            xaxis_title="Año",
                            yaxis_title="Valor (USD)",
                            height=450,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )
                        st.plotly_chart(fig_issuance, use_container_width=True, key="plotly_chart_issuance")
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de Emisión de Deuda: {e}")

                st.subheader("🏛️ Pago de Deuda")
                try:
                    key_repayment = "Repayment Of Debt"
                    if key_repayment not in cf_t.columns:
                        st.warning(f"No se encontró '{key_repayment}' en el Flujo de Efectivo.")
                    else:
                        repayment = cf_t[key_repayment]
                        fig_repayment = go.Figure()
                        fig_repayment.add_trace(go.Bar(
                            x=cf_t.index,
                            y=repayment,
                            name=key_repayment,
                            marker_color=primary_orange,
                            text=[f"${val:,.0f}" for val in repayment],
                            textposition='outside'
                        ))
                        fig_repayment.update_layout(
                            title="Pago de Deuda",
                            xaxis_title="Año",
                            yaxis_title="Valor (USD)",
                            height=450,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )
                        st.plotly_chart(fig_repayment, use_container_width=True, key="plotly_chart_repayment")
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de Pago de Deuda: {e}")

                st.subheader("♻️ Recompra de Acciones")
                try:
                    key_repurchase = "Repurchase Of Capital Stock"
                    if key_repurchase not in cf_t.columns:
                        st.warning(f"No se encontró '{key_repurchase}' en el Flujo de Efectivo.")
                    else:
                        repurchase = cf_t[key_repurchase]
                        fig_repurchase = go.Figure()
                        fig_repurchase.add_trace(go.Bar(
                            x=cf_t.index,
                            y=repurchase,
                            name=key_repurchase,
                            marker_color=primary_pink,
                            text=[f"${val:,.0f}" for val in repurchase],
                            textposition='outside'
                        ))
                        fig_repurchase.update_layout(
                            title="Recompra de Acciones",
                            xaxis_title="Año",
                            yaxis_title="Valor (USD)",
                            height=450,
                            margin=dict(l=30, r=30, t=60, b=30)
                        )
                        st.plotly_chart(fig_repurchase, use_container_width=True, key="plotly_chart_repurchase")
                except Exception as e:
                    st.warning(f"No se pudo generar el gráfico de Recompra de Acciones: {e}")

                st.markdown("#### Estado de Flujo de Efectivo en detalle")
                st.dataframe(ticker_data.cashflow.iloc[::-1], height=300)
        # --------------------------
                # Sección: Precios Objetivo (con entrada de Yield Deseado aquí)
                # --------------------------
        
        st.markdown("## 🎯 Valoración Proyectada")
        key_cols = st.columns(4)
        key_cols[0].metric("💰 Precio Actual", f"${price:.2f}" if price is not None else "N/A")
        # Para calcular el Valor Infravalorado de Geraldine Weiss se utiliza la metodología a partir de datos diarios:
        price_data_diario = ticker_data.history(period=selected_period, interval="1d")
        dividends_daily = ticker_data.dividends
        if not dividends_daily.empty:
                annual_dividends_raw = dividends_daily.resample("Y").sum()
                annual_dividends_raw.index = annual_dividends_raw.index.year
                start_year = pd.to_datetime(price_data.index[0]).year
                end_year = pd.to_datetime(price_data.index[-1]).year
                annual_dividends_gw = annual_dividends_raw[(annual_dividends_raw.index >= start_year) & (annual_dividends_raw.index <= end_year)]
                if len(annual_dividends_gw) >= 3:
                    first_val_gw = annual_dividends_gw.iloc[0]
                    penultimate_val_gw = annual_dividends_gw.iloc[-2]
                    n_years_gw = annual_dividends_gw.index[-2] - annual_dividends_gw.index[0]
                    cagr_gw = ((penultimate_val_gw / first_val_gw) ** (1 / n_years_gw) - 1) * 100
                else:
                    cagr_gw = None
                current_year = pd.Timestamp.today().year
                def ajustar_dividendo(year):
                    if (year == current_year) and (cagr_gw is not None) and ((year - 1) in annual_dividends_gw.index):
                        return annual_dividends_gw[year - 1] * (1 + cagr_gw/100)
                    else:
                        return annual_dividends_gw.get(year, None)
                    monthly_data = price_data_diario.resample("M").last().reset_index()
                    monthly_data['Año'] = monthly_data['Date'].dt.year
                    monthly_data['Mes'] = monthly_data['Date'].dt.strftime("%B")
                    monthly_data.rename(columns={'Close': 'Precio'}, inplace=True)
                    monthly_data['Dividendo Anual'] = monthly_data['Año'].apply(ajustar_dividendo)
                    monthly_data['Yield'] = monthly_data['Dividendo Anual'] / monthly_data['Precio']
                    overall_yield_max = monthly_data['Yield'].max()
                    monthly_data['Precio Infravalorado'] = monthly_data['Dividendo Anual'] / overall_yield_max
                    monthly_data = monthly_data.sort_values(by='Date')
                    valor_infravalorado = monthly_data.iloc[-1]['Precio Infravalorado']
        else:
                    valor_infravalorado = None
                
        key_cols[1].metric("💎 Precio Infrav. G. Weiss", f"${valor_infravalorado:.2f}" if valor_infravalorado is not None else "N/A")
        key_cols[2].metric("📊 Valor Libro Precio Justo", f"${fair_price:.2f}" if fair_price is not None else "N/A")
        key_cols[3].metric("🚀 Precio a PER 5 años", f"${per_5y:.2f}" if per_5y is not None else "N/A")
                
                # Ahora, en esta misma sección se solicita el Yield Deseado
        yield_deseado_obj = st.number_input("Ingrese Aquí el Yield Deseado (%)", min_value=0.1, value=3.0, step=0.1, key="yield_deseado_objetivo")
                
                # Recalcular el Precio por Dividendo Esperado:
                # (Dividendo Actual * (1 + (CAGR del Dividendo)/100)) / (Yield Deseado/100)
        fair_div_price = (dividend * (1 + (cagr_dividend/100))) / (yield_deseado_obj/100) if (dividend is not None and cagr_dividend is not None and yield_deseado_obj != 0) else None
                
        st.metric("⌛ Precio por Dividendo Esperado", f"${fair_div_price:.2f}" if fair_div_price is not None else "N/A")
                
                # --------------------------
                # Datos Relevantes (tabla)
                # --------------------------
        otros_datos = {
                    "ROE Actual": f"{roe_actual*100:.2f}%" if roe_actual is not None else "N/A",
                    "PauOut": f"{payout_ratio*100:.2f}%" if payout_ratio is not None else "N/A",
                    "EPS Actual": f"${eps_actual:.2f}" if eps_actual is not None else "N/A",
                    "PER": f"{pe_ratio:.2f}" if pe_ratio is not None else "N/A",
                    "P/B": f"{pb:.2f}" if pb is not None else "N/A",
                    "Book/Share": f"${book_per_share:.2f}" if book_per_share is not None else "N/A",
                    "G": f"{G_percent:.2f}%" if G_percent is not None else "N/A",
                    "Múltiplo Crecimiento": f"{multiplier}" if multiplier is not None else "N/A",
                    "EPS a 5 años": f"${eps_5y:.2f}" if eps_5y is not None else "N/A",
                    "G esperado": f"{g_esperado_percent:.2f}%" if g_esperado_percent is not None else "N/A",
                    "Dividendo Anual": f"${dividend:.2f}" if dividend is not None else "N/A",
                    "Yield Actual": f"{yield_actual:.2f}%" if yield_actual is not None else "N/A",
                    "CAGR del Dividendo": f"{cagr_dividend:.2f}%" if cagr_dividend is not None else "N/A",
                    "Yield Promedio": f"{avg_yield:.2f}%" if avg_yield is not None else "N/A"
                }
        df_otros = pd.DataFrame.from_dict(otros_datos, orient='index', columns=["Valor"])
        st.markdown("### 👨‍💻 Datos Relevantes")
        st.dataframe(df_otros)
        st.subheader("")


    except Exception as e:
        st.error(f"Ocurrió un error al obtener los datos: {e}")

            
    st.subheader("")  # Espacio extra

            