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

# აქ არ ვუთითებთ კონკრეტულ მოდელს, რომ არ "გაკრაშოს" დასაწყისშივე
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

class LinkRequest(BaseModel):
    url: str

# --- სადიაგნოსტიკო ფუნქცია (მთავარი ხსნა) ---
@app.get("/check_models")
def check_models_availability():
    if not GOOGLE_API_KEY:
        return {"status": "ERROR", "message": "API Key ვერ ვიპოვე Render-ში"}
    
    try:
        model_list = []
        # ვთხოვთ Google-ს ყველა მოდელის სიას
        for m in genai.list_models():
            model_list.append(m.name)
            
        return {
            "status": "SUCCESS", 
            "your_key_is_working": True,
            "available_models": model_list
        }
    except Exception as e:
        return {
            "status": "CRITICAL ERROR", 
            "message": str(e),
            "hint": "თუ აქ 400/403 ერორია, ესეიგი API Key არასწორია ან დაბლოკილი."
        }

# --- დანარჩენი კოდი ---

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
        if response.status_code != 200: return None
        data = response.json().get('data', {})
        if not data: return None
        return f"მანქანა: {data.get('man_id')} {data.get('mod_id')}, წელი: {data.get('prod_year')}, გარბენი: {data.get('car_run_km')}კმ, აღწერა: {data.get('product_description')}"
    except: return None

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

@app.post("/scrape_and_analyze")
def scrape_analyze(data: LinkRequest):
    if not GOOGLE_API_KEY: return {"error": "API Key missing"}
    
    car_id = extract_id(data.url)
    if not car_id: return {"error": "ID ვერ ვიპოვე"}
    
    car_info = get_myauto_data(car_id)
    if not car_info: return {"error": "MyAuto დაბლოკილია"}

    # აქ ვიყენებთ gemini-pro-ს, მაგრამ ჯერ დიაგნოსტიკაა მთავარი
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(f"Analyze: {car_info}. Output JSON.")
        text = response.text.replace('```json', '').replace('```', '')
        return json.loads(text)
    except Exception as e:
        return {"error": f"AI Error: {str(e)}"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)