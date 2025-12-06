import os
import uvicorn
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import re

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

class VinRequest(BaseModel):
    vin: str

def scrape_bidfax(vin):
    try:
        # Bidfax-ის ძებნის URL
        search_url = f"https://en.bidfax.info/?do=search&subaction=search&story={vin}"
        print(f"🔍 Searching Bidfax: {search_url}")
        
        # Chrome-ის იმიტაცია
        response = cffi_requests.get(
            search_url, 
            impersonate="chrome124",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        )

        if response.status_code != 200:
            return {"error": f"Bidfax Error: {response.status_code}"}

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # ვეძებთ მანქანის ლინკს ძებნის შედეგებში
        # Bidfax-ზე შედეგები არის h2 ტეგში, კლასით "short-teaser-title" ან უბრალოდ ლინკები
        car_link = None
        
        # ვეძებთ ყველა ლინკს, რომელიც შეიცავს VIN კოდს ან ტიპიურ სტრუქტურას
        main_block = soup.find('div', id='dle-content')
        if main_block:
            first_result = main_block.find('a', href=True)
            if first_result:
                car_link = first_result['href']
        
        if not car_link:
            return {"error": "მანქანა არქივში ვერ მოიძებნა (Bidfax) 🤷‍♂️"}

        print(f"✅ Found Page: {car_link}")

        # 2. შევდივართ მანქანის გვერდზე
        page_response = cffi_requests.get(car_link, impersonate="chrome124")
        page_soup = BeautifulSoup(page_response.content, 'html.parser')

        data = {
            "title": "უცნობი",
            "images": [],
            "info": {}
        }

        # სათაური
        h1 = page_soup.find('h1')
        if h1: data['title'] = h1.get_text(strip=True)

        # ფოტოები (Bidfax-ზე არის "full-img" კლასში ან "slider")
        images = []
        # ვეძებთ დიდ ფოტოებს
        img_tags = page_soup.find_all('img')
        for img in img_tags:
            src = img.get('src')
            if src and "bidfax.info/uploads/posts" in src:
                # full path-ის აღება (ხანდახან thumbs-ია, ვცვლით full-ზე)
                full_src = src.replace("thumbs/", "") # Bidfax-ის ლოგიკა შეიძლება განსხვავდებოდეს, მაგრამ ძირითადად პირდაპირ ლინკებია
                if full_src not in images:
                    images.append(full_src)
        
        # ვიღებთ პირველ 8 ფოტოს
        data['images'] = images[:8]

        # ინფო (ტექსტიდან ამოღება)
        full_text = page_soup.get_text()
        
        odometer = re.search(r'Mileage[:\s]+(\d+[\d\s]*mi|\d+[\d\s]*km)', full_text, re.IGNORECASE)
        damage = re.search(r'Primary Damage[:\s]+([A-Za-z\s]+)', full_text, re.IGNORECASE)
        engine = re.search(r'Engine[:\s]+([0-9\.]+L)', full_text, re.IGNORECASE)

        if odometer: data['info']['odometer'] = odometer.group(1).strip()
        if damage: data['info']['damage'] = damage.group(1).strip()
        if engine: data['info']['engine'] = engine.group(1).strip()

        return data

    except Exception as e:
        print(f"🔥 Error scraping: {e}")
        return {"error": str(e)}

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

@app.post("/check_vin")
def check_vin_handler(req: VinRequest):
    result = scrape_bidfax(req.vin)
    return result

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)