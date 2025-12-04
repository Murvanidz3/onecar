import os
import uvicorn
import google.generativeai as genai
import requests
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
    model = genai.GenerativeModel('gemini-1.5-flash',
                                  generation_config={"response_mime_type": "application/json"})

class LinkRequest(BaseModel):
    url: str # აქ შეიძლება იყოს ლინკიც და ID-იც

# დამხმარე ფუნქცია ID-ის ამოსაღებად
def extract_id(input_str):
    # თუ პირდაპირ ციფრებია (მაგ: 119361637)
    if input_str.isdigit():
        return input_str
    
    # თუ ლინკია (მაგ: myauto.ge/ka/pr/119361637/...)
    match = re.search(r'/pr/(\d+)', input_str)
    if match:
        return match.group(1)
    
    # სხვა შემთხვევაში ვეძებთ ნებისმიერ გრძელ ციფრს
    match = re.search(r'(\d{8,})', input_str)
    if match:
        return match.group(1)
        
    return None

def get_myauto_data(car_id):
    try:
        # მივმართავთ პირდაპირ API-ს (საიდუმლო კარი)
        api_url = f"https://api2.myauto.ge/ka/products/{car_id}"
        
        # User-Agent აუცილებელია, რომ არ დაგვბლოკონ
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(api_url, headers=headers)
        
        if response.status_code != 200:
            return None
            
        data = response.json().get('data', {})
        
        if not data:
            return None

        # ვაგროვებთ საჭირო ინფოს სუფთად
        info = f"""
        მანქანა: {data.get('man_id')} {data.get('mod_id')} (წელი: {data.get('prod_year')})
        ფასი: {data.get('price_usd', 0)}$
        გარბენი: {data.get('car_run_km')} კმ
        ძრავი: {data.get('engine_volume')}
        აღწერა: {data.get('product_description')}
        განბაჟება: {data.get('customs_passed')}
        """
        return info
        
    except Exception as e:
        print(f"API Error: {e}")
        return None

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

@app.post("/scrape_and_analyze")
def scrape_analyze(data: LinkRequest):
    if not GOOGLE_API_KEY:
        return {"error": "API Key not configured"}

    # 1. ვიღებთ ID-ს
    car_id = extract_id(data.url)
    if not car_id:
        return {"error": "ვერ ვიპოვე ID ლინკში. სცადეთ ხელით ჩაწერა."}

    # 2. ვიღებთ ინფოს API-დან
    car_info = get_myauto_data(car_id)
    if not car_info:
        return {"error": "MyAuto-ს API არ პასუხობს. სცადეთ მოგვიანებით."}

    # 3. ვაანალიზებთ AI-ით
    prompt = f"""
    Role: Strict Georgian Car Expert.
    Task: Analyze this car data fetched from MyAuto API.
    
    Car Data: {car_info}
    
    Output JSON format: {{ 
        "score": 0-100, 
        "verdict": "string (Georgian)", 
        "analysis": "string (Georgian - detailed analysis)",
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

# ძველი ფუნქცია (ხელით შესავსები)
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
    Price: {data.price} USD
    Real History: {data.vin_history_text}
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