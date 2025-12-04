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
    # ცვლილება 1: გადავედით "gemini-pro"-ზე და წავშალეთ json კონფიგურაცია
    try:
        model = genai.GenerativeModel('gemini-pro')
    except Exception as e:
        print(f"Model Init Error: {e}")

class LinkRequest(BaseModel):
    url: str

# დამხმარე ფუნქცია: AI-ს პასუხის გასასუფთავებლად (Markdown-ის მოშორება)
def clean_json_text(text):
    # შლის ```json და ``` სიმბოლოებს
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    return text.strip()

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
        response = cffi_requests.get(api_url, impersonate="chrome")
        
        if response.status_code != 200:
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
        print(f"Scraper Error: {e}")
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

    car_info = get_myauto_data(car_id)
    if not car_info:
        return {"error": "ვერ მოხერხდა დაკავშირება. გთხოვთ სცადოთ ხელით შევსება."}

    # ცვლილება 2: პრომპტში მკაცრად ვთხოვთ JSON-ს
    prompt = f"""
    You are a strict Georgian Car Expert.
    Analyze this car data from MyAuto.
    
    Data: {car_info}
    
    Output ONLY valid JSON (no markdown, no extra text) with these keys:
    {{
        "score": 0-100, 
        "verdict": "short georgian verdict", 
        "analysis": "detailed georgian analysis"
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        # ცვლილება 3: ვასუფთავებთ პასუხს
        clean_text = clean_json_text(response.text)
        return json.loads(clean_text)
    except Exception as e:
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
    You are a strict Georgian Car Expert.
    Analyze listing: {data.myauto_text}
    Price: {data.price}
    History: {data.vin_history_text}
    
    Output ONLY valid JSON:
    {{ "score": 0-100, "verdict": "geo string", "analysis": "geo string" }}
    """
    try:
        response = model.generate_content(prompt)
        clean_text = clean_json_text(response.text)
        return json.loads(clean_text)
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)