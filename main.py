import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from duckduckgo_search import DDGS

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

class VinRequest(BaseModel):
    vin: str

def smart_vin_search(vin):
    data = {
        "title": f"VIN: {vin}",
        "images": [],
        "info": {
            "odometer": "იხილეთ ფოტოზე",
            "damage": "იხილეთ ფოტოზე",
            "source": "Global Search"
        }
    }

    print(f"🔍 Starting Smart Filter Search for: {vin}")

    # სანდო წყაროების სია (მხოლოდ ამათგან წამოვიღებთ ფოტოებს)
    TRUSTED_DOMAINS = [
        "bidfax", "en.bidfax", "bid.cars", "poctra", "autoastat", 
        "copart", "iaai", "stat.vin", "carfast", "plc.ua"
    ]

    # საძიებო სიტყვების კომბინაციები
    queries = [
        f"{vin} bidfax",
        f"{vin} en.bidfax",
        f"{vin} poctra",
        f"{vin} car auction",
        f"{vin}" # ბოლო იმედი
    ]

    found_images = set() # დუბლიკატების თავიდან ასაცილებლად

    try:
        with DDGS() as ddgs:
            for q in queries:
                if len(data['images']) >= 8: break # თუ უკვე გვაქვს 8 ფოტო, ვჩერდებით

                print(f"   Trying query: {q}")
                results = list(ddgs.images(q, region="wt-wt", safesearch="off", max_results=15))

                for img in results:
                    image_url = img.get('image', '')
                    thumbnail = img.get('thumbnail', '')
                    source_url = img.get('url', '').lower() # საიტი, სადაც ფოტო დევს
                    title = img.get('title', '').lower()

                    # ფილტრი 1: შევამოწმოთ არის თუ არა სანდო წყაროდან
                    is_trusted = any(domain in source_url for domain in TRUSTED_DOMAINS)
                    
                    # ფილტრი 2: გადავამოწმოთ, ხომ არ არის ლოგო ან აიკონი
                    is_junk = any(x in image_url.lower() for x in ['logo', 'icon', 'banner', 'button', 'svg'])

                    # ფილტრი 3: სათაურში ან ლინკში უნდა იყოს VIN (სასურველია)
                    has_vin = vin.lower() in source_url or vin.lower() in title

                    # ლოგიკა: ვიღებთ თუ სანდოა და არ არის ნაგავი
                    # ან თუ შეიცავს VIN-ს და არ არის ნაგავი
                    if (is_trusted or has_vin) and not is_junk:
                        if image_url not in found_images:
                            data['images'].append(image_url)
                            found_images.add(image_url)
                            print(f"   ✅ Added image from: {source_url}")

        # ტექსტური ინფოს მცდელობა (სათაურის გასასწორებლად)
        if not data['images']:
             return {"error": "ვერცერთი სანდო ფოტო ვერ მოიძებნა. სცადეთ სხვა VIN."}
        
        # ვცადოთ მანქანის სახელის ამოღება პირველი შედეგიანი საძიებო მოთხოვნიდან
        with DDGS() as ddgs:
            text_results = list(ddgs.text(f"{vin} bidfax", max_results=1))
            if text_results:
                raw_title = text_results[0].get('title', '')
                # ვასუფთავებთ სათაურს (მაგ: "2018 TOYOTA CAMRY - Bidfax..." -> "2018 TOYOTA CAMRY")
                clean = raw_title.split('-')[0].split('|')[0].strip()
                data['title'] = clean

        return data

    except Exception as e:
        print(f"🔥 Error: {e}")
        return {"error": str(e)}

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

@app.post("/check_vin")
def check_vin_handler(req: VinRequest):
    result = smart_vin_search(req.vin)
    return result

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)