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

def scrape_autoastat(vin):
    try:
        # AutoAstat - Bidfax-ის კლონი
        search_url = f"https://autoastat.com/en/search/?q={vin}"
        print(f"🔍 Searching AutoAstat: {search_url}")
        
        # ვიყენებთ Chrome 110-ს (უფრო ძველი ვერსია ზოგჯერ უკეთ მუშაობს მარტივ საიტებზე)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
        }

        response = cffi_requests.get(search_url, impersonate="chrome110", headers=headers)
        
        if response.status_code != 200:
            return {"error": f"საიტმა არ გვიპასუხა (Code: {response.status_code})"}

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 1. ვეძებთ მანქანის ლინკს შედეგებში
        car_link = None
        
        # AutoAstat-ზე შედეგები არის .page-content -> .row -> a
        # ვეძებთ ნებისმიერ ლინკს, რომელიც შეიცავს VIN-ს ან '/cars/'
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            # ვამოწმებთ ლინკის სტრუქტურას
            if "/cars/" in href and vin.lower() not in href: # ზოგჯერ VIN არ წერია ლინკში
                 car_link = href
                 break
            if vin.lower() in href.lower():
                car_link = href
                break
        
        if not car_link:
            return {"error": "მანქანა ბაზაში ვერ მოიძებნა 🤷‍♂️"}

        # სრული ლინკი
        if not car_link.startswith("http"):
            full_link = f"https://autoastat.com{car_link}"
        else:
            full_link = car_link

        print(f"✅ Found Page: {full_link}")

        # 2. შევდივართ მანქანის გვერდზე
        page_response = cffi_requests.get(full_link, impersonate="chrome110", headers=headers)
        page_soup = BeautifulSoup(page_response.content, 'html.parser')

        data = {
            "title": "ნაპოვნია!",
            "images": [],
            "info": {}
        }

        # სათაური (h1)
        h1 = page_soup.find('h1')
        if h1: data['title'] = h1.get_text(strip=True)

        # ფოტოები (Gallery)
        # AutoAstat-ზე ფოტოები არის .fotorama დივში
        images = []
        img_tags = page_soup.find_all('img')
        for img in img_tags:
            src = img.get('src') or img.get('data-src')
            if src and ("/upload/" in src or "images" in src) and "logo" not in src:
                if not src.startswith("http"):
                    src = "https://autoastat.com" + src
                if src not in images:
                    images.append(src)
        
        # ვიღებთ 8 ფოტოს
        data['images'] = images[:8]

        # ინფო (ტექსტიდან ამოღება)
        full_text = page_soup.get_text()
        
        odometer = re.search(r'Odometer[:\s]+([\d,]+.*?)(mi|km)', full_text, re.IGNORECASE)
        damage = re.search(r'Primary Damage[:\s]+([A-Za-z\s]+)', full_text, re.IGNORECASE)
        engine = re.search(r'Engine[:\s]+([0-9\.]+L)', full_text, re.IGNORECASE)

        if odometer: data['info']['odometer'] = f"{odometer.group(1)} {odometer.group(2)}"
        if damage: data['info']['damage'] = damage.group(1).strip()
        if engine: data['info']['engine'] = engine.group(1).strip()

        return data

    except Exception as e:
        print(f"🔥 Error: {e}")
        return {"error": str(e)}

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

@app.post("/check_vin")
def check_vin_handler(req: VinRequest):
    result = scrape_autoastat(req.vin)
    return result

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)