import os
import uvicorn
import requests  # ვიყენებთ სტანდარტულ requests-ს Google-ისთვის
from curl_cffi import requests as cffi_requests # MyAuto-სთვის
import re
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import json

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

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
        # MyAuto-ს დაცვის გვერდის ავლით
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

# --- ახალი AI ფუნქცია (პირდაპირი REST API) ---
def ask_gemini_direct(prompt):
    if not GOOGLE_API_KEY:
        return {"error": "API Key is missing"}

    # პირდაპირი მისამართი Google-ის სერვერზე (REST API)
    # ვიყენებთ gemini-1.5-flash-ს
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    
    # მონაცემების გამზადება Google-ის ფორმატით
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        # ვაგზავნით მოთხოვნას პირდაპირ, ბიბლიოთეკის გარეშე
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            # თუ მაინც ერორია, ვცადოთ gemini-pro (Backup)
            fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GOOGLE_API_KEY}"
            response = requests.post(fallback_url, headers=headers, json=payload)
            
            if response.status_code != 200:
                return {"error": f"Google API Error: {response.text}"}

        result = response.json()
        
        # პასუხის ამოღება JSON სტრუქტურიდან
        if 'candidates' in result and result['candidates']:
            text_response = result['candidates'][0]['content']['parts'][0]['text']
            # AI აბრუნებს ტექსტს, რომელიც JSON-ს შეიცავს. ჩვენ მას ვასუფთავებთ და ობიექტად ვაქცევთ.
            return json.loads(clean_json_text(text_response))
        else:
            return {"error": "AI-მ ცარიელი პასუხი დააბრუნა."}

    except Exception as e:
        return {"error": f"Connection Error: {str(e)}"}

# --- Routes ---

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

@app.post("/scrape_and_analyze")
def scrape_analyze(data: LinkRequest):
    car_id = extract_id(data.url)
    if not car_id: return {"error": "ID ვერ ვიპოვე"}

    car_info = get_myauto_data(car_id)
    if not car_info: return {"error": "MyAuto-სთან დაკავშირება ვერ მოხერხდა."}

    prompt = f"""
    Role: Strict Georgian Car Expert.
    Task: Analyze MyAuto data: {car_info}
    Output JSON format: {{ "score": 0-100, "verdict": "geo string", "analysis": "geo string" }}
    """
    
    return ask_gemini_direct(prompt)

@app.post("/analyze")
def analyze_car(data: CarRequest):
    prompt = f"""
    Role: Strict Georgian Car Expert.
    Listing: {data.myauto_text}, Price: {data.price}, History: {data.vin_history_text}
    Output JSON format: {{ "score": 0-100, "verdict": "geo string", "analysis": "geo string" }}
    """
    return ask_gemini_direct(prompt)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)