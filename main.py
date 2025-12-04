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
    
    # ⚠️ ცვლილება: ვიყენებთ სტანდარტულ "gemini-1.5-flash" სახელს
    try:
        model = genai.GenerativeModel('gemini-1.5-flash',
                                      generation_config={"response_mime_type": "application/json"})
    except Exception as e:
        print(f"Model Init Error: {e}")

class LinkRequest(BaseModel):
    url: str

def extract_id(input_str):
    if input_str.isdigit():
        return input_str
    match = re.search(r'/pr/(\d+)', input_str)
    if match:
        return match.group(1)
    match = re.search(r'(\d{8,})', input_str)
    if match:
        return match.group(1)
    return None

def get_myauto_data(car_id):
    try:
        api_url = f"https://api2.myauto.ge/ka/products/{car_id}"
        # Cloudflare Bypass
        response = cffi_requests.get(api_url, impersonate="chrome")
        
        if response.status_code != 200:
            print(f"Status blocked: {response.status_code}")
            return None
            
        data = response.json().get('data', {})
        if not data:
            return None

        info = f"""
        მანქანა: {data.get('man_id')} {data.get('mod_id')}
        წელი: {data.get('prod_year')}
        ფასი: {data.get('price_usd', 0)}$
        გარბენი: {data.get('car_run_km')} კმ
        ძრავი: {data.get('engine_volume')}
        განბაჟება: {data.get('customs_passed')}
        აღწერა: {data.get('product_description')}
        """
        return info
    except Exception as e:
        print(f"CFFI Error: {e}")
        return None

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

@app.post("/scrape_and_analyze")
def scrape_analyze(data: LinkRequest):
    if not GOOGLE_API_KEY:
        return {"error": "API Key not configured"}

    car_id = extract_id(data.url)
    if not car_id:
        return {"error": "ვერ ვიპოვე ID."}

    # აქ უკვე ვიცით რომ ეს მუშაობს!
    car_info = get_myauto_data(car_id)
    if not car_info:
        return {"error": "ვერ მოხერხდა დაკავშირება. გთხოვთ სცადოთ ხელით შევსება."}

    prompt = f"""
    Role: Strict Georgian Car Expert.
    Task: Analyze this car data fetched from MyAuto.
    Data: {car_info}
    Output JSON format: {{ "score": 0-100, "verdict": "string", "analysis": "string" }}
    """
    
    try:
        # ვცადოთ სტანდარტული გამოძახება
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        # თუ 1.5-flash არ მუშაობს, ვცადოთ fallback
        return {"error": f"AI Error: {str(e)}"}

class CarRequest(BaseModel):
    myauto_text: str
    vin_history_text: str
    price: int

@app.post("/analyze")
def analyze_car(data: CarRequest):
    if not GOOGLE_API_KEY:
        return {"error": "API Key not configured"}
    prompt = f"""
    Role: Strict Georgian Car Expert.
    Listing: {data.myauto_text}
    Price: {data.price}
    History: {data.vin_history_text}
    Output JSON format: {{ "score": 0-100, "verdict": "string", "analysis": "string" }}
    """
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)