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

def scrape_bidcars(vin):
    try:
        # 1. ძებნა VIN კოდით Bid.cars-ზე
        search_url = f"https://bid.cars/en/search/results?search-term={vin}"
        print(f"🔍 Searching: {search_url}")
        
        # ვიყენებთ Chrome-ის იმიტაციას (დაცვის გასავლელად)
        response = cffi_requests.get(search_url, impersonate="chrome124")
        
        if response.status_code != 200:
            return {"error": f"ვერ დავუკავშირდი საიტს (Status: {response.status_code})"}

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 2. ვეძებთ შედეგს (მანქანის ლინკს)
        car_link = None
        
        # ვამოწმებთ, პირდაპირ ხომ არ გადაგვაგდო მანქანის გვერდზე?
        if "/lot/" in response.url:
            car_link = response.url
        else:
            # თუ არა, ვეძებთ სიაში
            results = soup.find_all('a', href=True)
            for link in results:
                if "/lot/" in link['href']:
                    car_link = link['href']
                    break
        
        if not car_link:
             return {"error": "მანქანა არქივში ვერ მოიძებნა 🤷‍♂️"}

        # სრული ლინკის აწყობა
        if not car_link.startswith("http"):
            full_link = f"https://bid.cars{car_link}"
        else:
            full_link = car_link

        print(f"✅ Found Page: {full_link}")

        # 3. შევდივართ მანქანის გვერდზე
        page_response = cffi_requests.get(full_link, impersonate="chrome124")
        page_soup = BeautifulSoup(page_response.content, 'html.parser')

        # 4. მონაცემების ამოღება
        data = {
            "title": "უცნობი",
            "images": [],
            "info": {}
        }

        # სათაური
        h1 = page_soup.find('h1')
        if h1: data['title'] = h1.get_text(strip=True)

        # ფოტოები (ვეძებთ დიდ სურათებს)
        images = []
        img_tags = page_soup.find_all('img')
        for img in img_tags:
            src = img.get('src') or img.get('data-src')
            if src and "media.bid.cars" in src and "small" not in src:
                # ვასუფთავებთ ლინკს რომ დიდი ზომა მივიღოთ
                full_size = src.replace("thumbnails/", "").replace("small/", "")
                if full_size not in images:
                    images.append(full_size)
        
        # ვიღებთ პირველ 5 ფოტოს
        data['images'] = images[:5]

        # ტექნიკური ინფო (ტექსტიდან ამოღება)
        info_block = page_soup.get_text()
        
        odometer = re.search(r'Odometer[:\s]+([\d,]+)', info_block)
        damage = re.search(r'Primary Damage[:\s]+([A-Za-z\s]+)', info_block)
        engine = re.search(r'Engine[:\s]+([0-9\.]+L)', info_block)

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

# ახალი ენდპოინტი
@app.post("/check_vin")
def check_vin_handler(req: VinRequest):
    result = scrape_bidcars(req.vin)
    return result

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)