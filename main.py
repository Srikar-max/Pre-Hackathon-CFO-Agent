import uvicorn
import pandas as pd
import os
import json
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import JSONResponse

class Metrics(BaseModel):
    runway: int
    monthly_revenue: int
    monthly_cogs: int     
    monthly_opex: int      

class SimulatePayload(BaseModel):
    hires: int
    marketing_spend_increase: int
    price_increase_percentage: float
    baseline_metrics: Metrics

class FlexpricePayload(BaseModel):
    product_description: str

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FLEXPRICE_API_KEY = os.getenv("FLEXPRICE_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

FLEXPRICE_API_BASE_URL = "https://api.flexprice.dev/v1" 
FLEXPRICE_HEADERS = {
    "Authorization": f"Bearer {FLEXPRICE_API_KEY}" if FLEXPRICE_API_KEY else "",
    "Content-Type": "application/json"
}

app = FastAPI(title="CFO Helper API")
origins = ["http://localhost", "http://localhost:8501"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

USAGE_STATS = {"scenarios_simulated": 0, "reports_exported": 0, "ai_price_calculations": 0}

def get_usage_stats(customer_id: str = "default-customer"):
    if FLEXPRICE_API_KEY:
        try:
            response = requests.get(f"{FLEXPRICE_API_BASE_URL}/usage/{customer_id}", headers=FLEXPRICE_HEADERS, timeout=3)
            response.raise_for_status()
            data = response.json()
            USAGE_STATS.update(data)
            return data
        except requests.exceptions.RequestException:
            return USAGE_STATS.copy()
    else:
        return USAGE_STATS.copy()

def log_flexprice_event(event_name: str, customer_id: str = "default-customer"):
    if event_name == "scenario_simulated":
        USAGE_STATS["scenarios_simulated"] += 1
    elif event_name == "report_exported":
        USAGE_STATS["reports_exported"] += 1
    elif event_name == "ai_price_calculation":
        USAGE_STATS["ai_price_calculations"] += 1

    if FLEXPRICE_API_KEY:
        try:
            payload = {"eventName": event_name, "customerId": customer_id}
            requests.post(f"{FLEXPRICE_API_BASE_URL}/meter", headers=FLEXPRICE_HEADERS, json=payload, timeout=3)
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Could not log event to Flexprice: {e}")
    return get_usage_stats(customer_id)

# --- API Endpoints ---
@app.get("/initial-data")
async def get_initial_data():
    usage_stats = get_usage_stats()
    baseline_metrics = {
        "runway": 18, "monthly_revenue": 220000,
        "monthly_cogs": 40000, "monthly_opex": 150000
    }
    return {"baseline_metrics": baseline_metrics, "usage_stats": usage_stats}

@app.post("/simulate")
async def simulate_scenario(payload: SimulatePayload):
    base = payload.baseline_metrics
    new_monthly_revenue = int(base.monthly_revenue * (1 + payload.price_increase_percentage / 100.0))
    per_hire_monthly = 75000 / 12.0
    hiring_cost_monthly = payload.hires * per_hire_monthly
    new_monthly_opex = int(base.monthly_opex + hiring_cost_monthly + payload.marketing_spend_increase)
    new_gross_profit = new_monthly_revenue - base.monthly_cogs
    new_net_profit = new_gross_profit - new_monthly_opex
    
    baseline_net_profit = base.monthly_revenue - base.monthly_cogs - base.monthly_opex
    base_net_burn = -baseline_net_profit if baseline_net_profit < 0 else 0
    starting_cash = base.runway * base_net_burn if base_net_burn > 0 else base.monthly_revenue * 12

    net_cash_burn = -new_net_profit if new_net_profit < 0 else 0
    new_runway = int(max(0, starting_cash // net_cash_burn)) if net_cash_burn > 0 else 48

    updated_usage_stats = log_flexprice_event("scenario_simulated")
    
    simulated_metrics = {
        "runway": new_runway, "monthly_burn": new_monthly_opex, "monthly_opex": new_monthly_opex,
        "monthly_profit": int(new_net_profit), "monthly_revenue": int(new_monthly_revenue),
        "monthly_cogs": int(base.monthly_cogs)
    }
    return {"simulated_metrics": simulated_metrics, "usage_stats": updated_usage_stats}

@app.post("/log-report-export")
async def log_report_export():
    return log_flexprice_event("report_exported")

@app.post("/data-refresh")
async def refresh_data():
    refreshed_metrics = {
        "runway": 15, "monthly_revenue": 210000,
        "monthly_cogs": 45000, "monthly_opex": 160000
    }
    return {"baseline_metrics": refreshed_metrics}

@app.post("/flexprice/calculate")
async def calculate_price(payload: FlexpricePayload):
    updated_usage_stats = log_flexprice_event("ai_price_calculation")
    if GEMINI_API_KEY:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f'Respond ONLY with a valid JSON object with keys "optimal_price" (number) and "reasoning" (string). Product: "{payload.product_description}"'
        try:
            response = model.generate_content(prompt)
            cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()
            result_json = json.loads(cleaned_response)
            result_json["usage_stats"] = updated_usage_stats
            return JSONResponse(content=result_json)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error with Gemini API: {e}")
    else:
        result = {"optimal_price": 999, "reasoning": "GEMINI_API_KEY not configured.", "usage_stats": updated_usage_stats}
        return JSONResponse(content=result)