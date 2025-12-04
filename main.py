import os
import uvicorn
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
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

# 1. ახალი მოთხოვნა: მომხმარებელი აგზავნის ლინკს (URL)
class LinkRequest(BaseModel):
    url: str

# 2. სკრაპინგის ფუნქცია (MyAuto-დან ინფორმაციის წამოღება)
def scrape_myauto(url):
    try:
        # თავს ვაჩვენებთ როგორც ნამდვილი ბრაუზერი (User-Agent)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        # ვეძებთ აღწერას (MyAuto-ს სტრუქტურა იცვლება, ეს არის სავარაუდო კლასები)
        # ვცდილობთ ვიპოვოთ აღწერის ტექსტი
        description = ""
        desc_div = soup.find('div', class_='product-desc') # ძველი დიზაინი
        if not desc_div:
            # ვცადოთ მეტა ტეგი (უფრო საიმედოა)
            meta_desc = soup.find('meta', property='og:description')
            if meta_desc:
                description = meta_desc.get('content', '')
        else:
            description = desc_div.get_text(strip=True)

        return description
    except Exception as e:
        print(f"Scraping Error: {e}")
        return None

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

# 3. ახალი API: ლინკის დამუშავება
@app.post("/scrape_and_analyze")
def scrape_analyze(data: LinkRequest):
    if not GOOGLE_API_KEY:
        return {"error": "API Key not configured"}

    # ნაბიჯი A: ინფორმაციის წამოღება ლინკიდან
    scraped_text = scrape_myauto(data.url)
    
    if not scraped_text:
        return {"error": "ვერ მოხერხდა ინფორმაციის წამოღება ლინკიდან. სცადეთ ტექსტის ხელით ჩაწერა."}

    # ნაბიჯი B: AI ანალიზი (ჯერჯერობით ისტორიის გარეშე, მარტო განცხადებას ვაფასებთ)
    prompt = f"""
    Role: Strict Georgian Car Expert.
    Task: Analyze this car listing text from MyAuto.
    Look for hidden meanings (e.g., "requires hand" means broken).
    
    Listing Text: {scraped_text}
    
    Output JSON format: {{ 
        "score": 0-100, 
        "verdict": "string (Georgian)", 
        "analysis": "string (Georgian - explain pros and cons based on text)",
        "scraped_info": "{scraped_text[:100]}..." 
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

# ძველი ფუნქციაც დავტოვოთ, თუ ხელით ჩაწერა მოუნდებათ
class CarRequest(BaseModel):
    myauto_text: str
    vin_history_text: str
    price: int

@app.post("/analyze")
def analyze_car(data: CarRequest):
    # ... (ძველი კოდი იგივე რჩება) ...
    pass 

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)