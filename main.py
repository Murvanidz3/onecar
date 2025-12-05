import os
import uvicorn
import google.generativeai as genai
from curl_cffi import requests as cffi_requests
import re
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import json

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

class LinkRequest(BaseModel):
    url: str

class CarRequest(BaseModel):
    myauto_text: str
    vin_history_text: str
    price: int

# --- დამხმარე ფუნქციები ---

def clean_json_text(text):
    text = text.replace('```json', '').replace('```', '')
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end+1]
    return text.strip()

def extract_id(input_str):
    if input_str.isdigit(): return input_str
    match = re.search(r'/pr/(\d+)', input_str)
    if match: return match.group(1)
    match = re.search(r'(\d{8,})', input_str)
    if match: return match.group(1)
    return None

def get_myauto_data(car_id):
    try:
        api_url = f"https://api2.myauto.ge/ka/products/{car_id}"
        # ვიყენებთ Chrome-ის იმიტაციას
        response = cffi_requests.get(api_url, impersonate="chrome")
        if response.status_code != 200: return None
        data = response.json().get('data', {})
        if not data: return None
        
        return f"""
        მანქანა: {data.get('man_id')} {data.get('mod_id')}
        წელი: {data.get('prod_year')}
        ფასი: {data.get('price_usd', 0)}$
        გარბენი: {data.get('car_run_km')} კმ
        ძრავი: {data.get('engine_volume')}
        განბაჟება: {data.get('customs_passed')}
        აღწერა: {data.get('product_description')}
        """
    except: return None

# --- AI ფუნქცია (Smart Retry) ---
# ეს ფუნქცია ეცდება 1.5-flash-ს, თუ არ გამოვიდა - gemini-pro-ს
def ask_gemini(prompt):
    # აქ პირდაპირ სახელებს ვწერთ, პრეფიქსების გარეშე
    models_to_try = ["gemini-1.5-flash", "gemini-pro"]
    
    last_error = None
    
    for model_name in models_to_try:
        try:
            print(f"🤖 Trying model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return json.loads(clean_json_text(response.text))
        except Exception as e:
            print(f"⚠️ {model_name} failed: {e}")
            last_error = e
            continue
            
    # თუ ვერცერთმა ვერ იმუშავა
    return {"error": f"AI Error: {str(last_error)}"}

# --- Routes ---

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

@app.post("/scrape_and_analyze")
def scrape_analyze(data: LinkRequest):
    if not GOOGLE_API_KEY: return {"error": "API Key not configured"}

    car_id = extract_id(data.url)
    if not car_id: return {"error": "ID ვერ ვიპოვე"}

    car_info = get_myauto_data(car_id)
    if not car_info: return {"error": "ვერ მოხერხდა MyAuto-სთან დაკავშირება. გამოიყენეთ ხელით შემოწმება."}

    prompt = f"""
    Role: Strict Georgian Car Expert.
    Task: Analyze MyAuto data: {car_info}
    Output JSON format: {{ "score": 0-100, "verdict": "geo string", "analysis": "geo string" }}
    """
    
    return ask_gemini(prompt)

@app.post("/analyze")
def analyze_car(data: CarRequest):
    if not GOOGLE_API_KEY: return {"error": "API Key not configured"}
            
    prompt = f"""
    Role: Strict Georgian Car Expert.
    Listing: {data.myauto_text}, Price: {data.price}, History: {data.vin_history_text}
    Output JSON format: {{ "score": 0-100, "verdict": "geo string", "analysis": "geo string" }}
    """
    return ask_gemini(prompt)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)