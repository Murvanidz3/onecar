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

def scrape_carfast(vin):
    try:
        # Carfast-ის ძებნის ლინკი
        search_url = f"https://carfast.express/en/cars/buy_report?vin={vin}"
        print(f"🔍 Searching Carfast: {search_url}")
        
        # ვიყენებთ Chrome-ის იმიტაციას
        response = cffi_requests.get(
            search_url, 
            impersonate="chrome120",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
        )
        
        if response.status_code != 200:
            return {"error": f"Carfast Error: {response.status_code}"}

        soup = BeautifulSoup(response.content, 'html.parser')
        
        data = {
            "title": "ნაპოვნია!",
            "images": [],
            "info": {}
        }

        # 1. ძირითადი ფოტო (Carfast-ზე ხშირად მხოლოდ 1 ფოტო ჩანს უფასოდ)
        # ვეძებთ სურათს 'car-photo' კლასში ან მსგავსში
        main_img = soup.find('img', class_='car-card__img') # სავარაუდო კლასი
        
        if not main_img:
            # ვცადოთ უფრო ზოგადი ძებნა
            images = soup.find_all('img')
            for img in images:
                src = img.get('src', '')
                # Carfast-ის სურათები ხშირად "photos" ან "images" საქაღალდეშია
                if '/photos/' in src or 'blob:' not in src and src.startswith('http'):
                    if 'logo' not in src and 'icon' not in src:
                        data['images'].append(src)
                        break # პირველივე რეალურ ფოტოს ვიღებთ
        else:
            src = main_img.get('src')
            if src: data['images'].append(src)

        # 2. ინფორმაციის ამოღება (ცხრილიდან)
        # ვეძებთ "VIN", "Model", "Engine"
        info_blocks = soup.find_all('div', class_='car-card__row') # სავარაუდო სტრუქტურა
        
        # თუ კლასები შეიცვალა, ვეძებთ ტექსტით
        text_content = soup.get_text()
        
        model_match = re.search(r'Model\s+([A-Za-z0-9\s]+)', text_content)
        engine_match = re.search(r'Engine\s+([A-Za-z0-9\.\s]+)', text_content)
        
        if model_match:
            data['title'] = model_match.group(1).strip()
        else:
            # სათაურის ალტერნატიული ძებნა
            h1 = soup.find('h1')
            if h1: data['title'] = h1.get_text(strip=True)

        if engine_match:
            data['info']['engine'] = engine_match.group(1).strip()

        # თუ ფოტო ვერ ვიპოვეთ, ე.ი. არაფერი ჩანს
        if not data['images']:
            # კიდევ ერთი ცდა: ვეძებთ background-image-ს
            divs = soup.find_all('div', style=True)
            for div in divs:
                style = div['style']
                if 'background-image' in style and 'url' in style:
                    url_match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
                    if url_match:
                        img_url = url_match.group(1)
                        if 'car' in img_url or 'photo' in img_url:
                            data['images'].append(img_url)
                            break

        if not data['images']:
             return {"error": "ფოტო ვერ მოიძებნა (შესაძლოა ფასიანია ან VIN არასწორია)"}

        return data

    except Exception as e:
        print(f"🔥 Error scraping: {e}")
        return {"error": str(e)}

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

@app.post("/check_vin")
def check_vin_handler(req: VinRequest):
    result = scrape_carfast(req.vin)
    return result

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)