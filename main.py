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
active_model = None

# --- აი აქ არის მთავარი ცვლილება ---
def setup_model():
    global active_model
    if not GOOGLE_API_KEY:
        print("❌ API Key is missing!")
        return

    genai.configure(api_key=GOOGLE_API_KEY)
    
    try:
        print("🔍 Asking Google for available models...")
        # ვითხოვთ სიას
        available_models = []
        for m in genai.list_models():
            # ვფილტრავთ მხოლოდ იმათ, ვისაც ტექსტის გენერაცია შეუძლია
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        print(f"📋 Found models: {available_models}")

        # პრიორიტეტი: ვეძებთ 'flash'-ს ან 'pro'-ს სიაში
        selected_name = None
        
        # ჯერ ვეძებთ 1.5-flash-ს (ყველაზე სწრაფია)
        for name in available_models:
            if "gemini-1.5-flash" in name:
                selected_name = name
                break
        
        # თუ ვერ ვიპოვეთ, ნებისმიერი "gemini" ავიღოთ
        if not selected_name:
            for name in available_models:
                if "gemini" in name:
                    selected_name = name
                    break
        
        # თუ მაინც ვერ ვიპოვეთ, ავიღოთ სიის პირველი წევრი
        if not selected_name and available_models:
            selected_name = available_models[0]

        if selected_name:
            print(f"✅ Selected Model: {selected_name}")
            active_model = genai.GenerativeModel(selected_name)
            
            # სატესტო გაშვება
            try:
                active_model.generate_content("Test")
                print("🚀 Test generation successful!")
            except Exception as e:
                print(f"⚠️ Model selected but failed test: {e}")
        else:
            print("❌ No suitable generation model found in the list.")

    except Exception as e:
        print(f"❌ Setup failed: {e}")

# გაშვებისას ვარჩევთ მოდელს
if GOOGLE_API_KEY:
    setup_model()

# --- დანარჩენი ლოგიკა იგივეა ---

class LinkRequest(BaseModel):
    url: str

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
        response = cffi_requests.get(api_url, impersonate="chrome")
        if response.status_code != 200: return None
        data = response.json().get('data', {})
        if not data: return None
        return f"მანქანა: {data.get('man_id')} {data.get('mod_id')}, წელი: {data.get('prod_year')}, გარბენი: {data.get('car_run_km')}კმ, ძრავი: {data.get('engine_volume')}, აღწერა: {data.get('product_description')}"
    except: return None

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

@app.post("/scrape_and_analyze")
def scrape_analyze(data: LinkRequest):
    if not active_model:
        setup_model() # კიდევ ერთხელ ვცადოთ
        if not active_model:
            return {"error": "სერვერმა ვერ იპოვა აქტიური AI მოდელი. გთხოვთ შეამოწმოთ ლოგები."}

    car_id = extract_id(data.url)
    if not car_id: return {"error": "ID ვერ ვიპოვე"}

    car_info = get_myauto_data(car_id)
    if not car_info: return {"error": "ვერ მოხერხდა დაკავშირება. სცადეთ ხელით შევსება."}

    prompt = f"""
    Role: Strict Georgian Car Expert.
    Task: Analyze MyAuto data: {car_info}
    Output JSON format: {{ "score": 0-100, "verdict": "geo string", "analysis": "geo string" }}
    """
    
    try:
        response = active_model.generate_content(prompt)
        return json.loads(clean_json_text(response.text))
    except Exception as e:
        return {"error": f"AI Error: {str(e)}"}

class CarRequest(BaseModel):
    myauto_text: str
    vin_history_text: str
    price: int

@app.post("/analyze")
def analyze_car(data: CarRequest):
    if not active_model:
        setup_model()
        if not active_model: return {"error": "AI სისტემა მიუწვდომელია"}
            
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