import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import io

API_URL = "http://127.0.0.1:8000"

def get_initial_data():
    try:
        response = requests.get(f"{API_URL}/initial-data", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        st.error("🔴 Could not connect to the backend. Is the `main.py` server running?")
        return None

def run_simulation(payload: dict):
    try:
        with st.spinner('Running financial models...'):
            response = requests.post(f"{API_URL}/simulate", json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Simulation failed: {e}")
        return None

def refresh_data():
    try:
        with st.spinner("Fetching live data..."):
            response = requests.post(f"{API_URL}/data-refresh", timeout=5)
            response.raise_for_status()
            return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Data refresh failed: {e}")
        return None

def log_report_export():
    try:
        response = requests.post(f"{API_URL}/log-report-export", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None

def calculate_dynamic_price(payload: dict):
    try:
        with st.spinner("Querying Gemini for optimal price..."):
            response = requests.post(f"{API_URL}/flexprice/calculate", json=payload, timeout=12)
            response.raise_for_status()
            return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Dynamic pricing failed: {e}")
        return None

def build_forecast_df(metrics: dict):
    net_profit = metrics["monthly_revenue"] - metrics["monthly_cogs"] - metrics["monthly_opex"]
    base_net_burn = -net_profit if net_profit < 0 else 0
    starting_cash = metrics["runway"] * base_net_burn if base_net_burn > 0 else (metrics["monthly_revenue"] * 12)
    runway_duration = metrics.get("runway", 36)
    if runway_duration <= 0: runway_duration = 1
    cash_balance = [max(0, starting_cash + (net_profit * i)) for i in range(runway_duration)]
    return pd.DataFrame({"Month": range(1, runway_duration + 1), "Cash Balance": cash_balance})

st.set_page_config(page_title="CFO Helper", page_icon="📈", layout="wide")
st.markdown("""<style>...</style>""", unsafe_allow_html=True) 

if 'initialized' not in st.session_state:
    initial_data = get_initial_data()
    if initial_data:
        st.session_state.baseline_metrics = initial_data["baseline_metrics"]
        st.session_state.baseline_forecast = build_forecast_df(initial_data["baseline_metrics"])
        st.session_state.usage_stats = initial_data.get("usage_stats", {"scenarios_simulated": 0, "reports_exported": 0})
        st.session_state.simulation_result = None
        st.session_state.dynamic_price_result = None
        st.session_state.initialized = True
    else:
        st.stop()

main_tab1, main_tab2 = st.tabs(["📊 Financial Scenario Simulator", "💡 Dynamic Pricing Assistant"])
with main_tab1:
    with st.sidebar:
        st.markdown("<h1><span style='color: #1E88E5;'>CFO</span> Helper</h1>", unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("📝 Scenario Inputs")
        num_engineers = st.number_input("🧑‍💻 Hire Additional Engineers", 0, 10, 2, 1)
        marketing_spend = st.slider("📢 Addtl. Monthly Marketing (₹)", 0, 200000, 10000, 5000)
        price_increase_perc = st.slider("💲 Product Price Increase (%)", 0, 50, 10, 5)
        st.markdown("---")

        if st.button("Simulate Scenario", use_container_width=True, type="primary"):
            payload = {
                "hires": int(num_engineers),
                "marketing_spend_increase": int(marketing_spend),
                "price_increase_percentage": float(price_increase_perc),
                "baseline_metrics": st.session_state.baseline_metrics
            }
            result = run_simulation(payload)
            if result:
                full_sim_metrics = st.session_state.baseline_metrics.copy()
                full_sim_metrics.update(result['simulated_metrics'])
                result['simulated_forecast'] = build_forecast_df(full_sim_metrics)
                st.session_state.simulation_result = result
                if "usage_stats" in result:
                    st.session_state.usage_stats = result["usage_stats"]
                st.rerun()

        if st.button("🔄 Refresh Live Data", use_container_width=True):
            refreshed_data = refresh_data()
            if refreshed_data:
                st.session_state.baseline_metrics = refreshed_data['baseline_metrics']
                st.session_state.baseline_forecast = build_forecast_df(refreshed_data['baseline_metrics'])
                st.session_state.simulation_result = None
                st.rerun()

        st.markdown("---")
        st.subheader("📊 Usage Dashboard")
        st.metric("Scenarios Simulated", st.session_state.usage_stats.get('scenarios_simulated', 0))
        st.metric("Reports Exported", st.session_state.usage_stats.get('reports_exported', 0))

    st.header("Financial Scenario Dashboard")
    if not st.session_state.simulation_result:
        st.info("Adjust inputs in the sidebar and click 'Simulate Scenario' to forecast your financials.")
        base = st.session_state.baseline_metrics
        base_profit = base['monthly_revenue'] - base['monthly_cogs'] - base['monthly_opex']
        col1, col2, col3 = st.columns(3)
        col1.metric("🏦 Runway (Months)", f"{base['runway']}")
        col2.metric("🔥 Monthly OpEx (Burn)", f"₹{base['monthly_opex']:,.0f}")
        col3.metric("💰 Net Profit/Loss (₹)", f"₹{base_profit:,.0f}")
    else:
        base_metrics = st.session_state.baseline_metrics
        base_profit = base_metrics['monthly_revenue'] - base_metrics['monthly_cogs'] - base_metrics['monthly_opex']
        base_burn = base_metrics['monthly_opex']
        simulated = st.session_state.simulation_result['simulated_metrics']
        col1, col2, col3 = st.columns(3)
        col1.metric("🏦 Runway (Months)", f"{simulated['runway']}", f"{simulated['runway'] - base_metrics.get('runway', 0)} Months")
        col2.metric("🔥 Monthly OpEx (Burn)", f"₹{simulated['monthly_burn']:,.0f}", f"₹{simulated['monthly_burn'] - base_burn:,.0f}", delta_color="inverse")
        col3.metric("💰 Net Profit/Loss (₹)", f"₹{simulated['monthly_profit']:,.0f}", f"₹{simulated['monthly_profit'] - base_profit:,.0f}")

        chart_tab, report_tab = st.tabs(["📈 Forecast Chart", "📄 Generate Report"])
        with chart_tab:
            baseline_df = st.session_state.baseline_forecast.copy()
            baseline_df['Scenario'] = 'Baseline'
            simulated_df = st.session_state.simulation_result['simulated_forecast'].copy()
            simulated_df['Scenario'] = 'Simulated'
            combined_df = pd.concat([baseline_df, simulated_df], ignore_index=True)
            fig = px.line(combined_df, x='Month', y='Cash Balance', color='Scenario', markers=True, template='plotly_white')
            st.plotly_chart(fig, use_container_width=True)

        with report_tab:
            st.subheader("Export Simulation Summary")
            def on_download_click():
                new_stats = log_report_export()
                if new_stats:
                    st.session_state.usage_stats = new_stats
                st.rerun()
            
            report_text = "..." 
            st.download_button(label="📥 Download Report", data=report_text.encode("utf-8"), file_name="financial_report.txt", mime="text/plain", on_click=on_download_click, use_container_width=True, type="primary")

with main_tab2:
    st.header("💡 AI Dynamic Pricing Assistant")
    st.markdown("Leverage Gemini to find the optimal price point for your product.")
    product_desc = st.text_area("**Enter Product Description**", "e.g., A subscription-based SaaS platform...", height=150)
    if st.button("Calculate Optimal Price", use_container_width=True, type="primary"):
        if product_desc and product_desc.strip():
            price_result = calculate_dynamic_price({"product_description": product_desc})
            if price_result:
                st.session_state.dynamic_price_result = price_result
                if "usage_stats" in price_result:
                    st.session_state.usage_stats = price_result["usage_stats"]
                st.rerun()
        else:
            st.warning("Please enter a product description.")

    if st.session_state.dynamic_price_result:
        st.markdown("---")
        st.subheader("Recommended Pricing")
        price = st.session_state.dynamic_price_result.get('optimal_price', 'N/A')
        reasoning = st.session_state.dynamic_price_result.get('reasoning', 'No reasoning provided.')
        col1, col2 = st.columns([1, 2])
        try:
            col1.metric("Optimal Price (₹)", f"₹{float(price):,.0f}")
        except (ValueError, TypeError):
            col1.metric("Optimal Price (₹)", f"{price}")
        col2.info(f"**AI Reasoning:**\n\n{reasoning}")