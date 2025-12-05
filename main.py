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

# გლობალური ცვლადი მოდელისთვის
active_model = None

def setup_model():
    global active_model
    if not GOOGLE_API_KEY:
        print("❌ API Key is missing!")
        return

    genai.configure(api_key=GOOGLE_API_KEY)
    
    # მოდელების სია პრიორიტეტის მიხედვით
    candidates = [
        "gemini-1.5-flash",
        "gemini-1.5-flash-001",
        "gemini-1.5-flash-002",
        "gemini-1.5-flash-latest",
        "gemini-pro",
        "gemini-1.0-pro",
        "gemini-1.0-pro-latest"
    ]
    
    print("🔍 Searching for a working model...")
    
    for model_name in candidates:
        try:
            print(f"Testing model: {model_name}...")
            # ვცდილობთ მარტივ მოთხოვნას
            m = genai.GenerativeModel(model_name)
            response = m.generate_content("Hello")
            
            if response and response.text:
                print(f"✅ SUCCESS! Using model: {model_name}")
                # თუ json mode-ს მხარდაჭერა აქვს (flash ვერსიებს), ვრთავთ
                if "flash" in model_name:
                    active_model = genai.GenerativeModel(model_name, generation_config={"response_mime_type": "application/json"})
                else:
                    active_model = genai.GenerativeModel(model_name)
                return
        except Exception as e:
            print(f"❌ {model_name} failed: {e}")
            continue
            
    print("⚠️ CRITICAL: No working model found in the list.")

# აპლიკაციის ჩართვისას ვეძებთ მოდელს
if GOOGLE_API_KEY:
    setup_model()

class LinkRequest(BaseModel):
    url: str

def clean_json_text(text):
    # ასუფთავებს AI-ს პასუხს
    text = text.replace('```json', '').replace('```', '')
    # ზოგჯერ json-ის გარეთაც წერს რაღაცებს, ვცდილობთ მოვძებნოთ { }
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
    if not active_model:
        # თუ მოდელი ვერ შეირჩა, თავიდან ვცადოთ
        setup_model()
        if not active_model:
            return {"error": "AI სისტემა დროებით მიუწვდომელია (Model selection failed)."}

    car_id = extract_id(data.url)
    if not car_id: return {"error": "ID ვერ ვიპოვე"}

    car_info = get_myauto_data(car_id)
    if not car_info: return {"error": "ვერ მოხერხდა დაკავშირება. გამოიყენეთ ხელით შემოწმება."}

    prompt = f"""
    Role: Strict Georgian Car Expert.
    Task: Analyze MyAuto data: {car_info}
    Output JSON format: {{ "score": 0-100, "verdict": "geo string", "analysis": "geo string" }}
    """
    
    try:
        response = active_model.generate_content(prompt)
        return json.loads(clean_json_text(response.text))
    except Exception as e:
        # თუ არჩეულმა მოდელმა აურია, თავიდან ვცადოთ არჩევა შემდეგისთვის
        setup_model()
        return {"error": f"AI Error: {str(e)}"}

class CarRequest(BaseModel):
    myauto_text: str
    vin_history_text: str
    price: int

@app.post("/analyze")
def analyze_car(data: CarRequest):
    if not active_model:
        setup_model()
        if not active_model:
            return {"error": "AI სისტემა მიუწვდომელია"}
            
    prompt = f"""
    Role: Strict Georgian Car Expert.
    Listing: {data.myauto_text}, Price: {data.price}, History: {data.vin_history_text}
    Output JSON format: {{ "score": 0-100, "verdict": "geo string", "analysis": "geo string" }}
    """
    try:
        response = active_model.generate_content(prompt)
        return json.loads(clean_json_text(response.text))
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)