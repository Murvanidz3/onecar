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
            "odometer": "უცნობია",
            "damage": "უცნობია",
            "source": "Global Search"
        }
    }

    try:
        print(f"🔍 Searching logic for: {vin}")
        
        # 1. სურათების ძებნა (DuckDuckGo Images)
        # ვეძებთ კონკრეტულად აუქციონის ფოტოებს
        with DDGS() as ddgs:
            # ვეძებთ: VIN + "bidfax" ან "auction"
            keywords = f"{vin} car auction"
            ddg_images = list(ddgs.images(
                keywords, 
                region="wt-wt", 
                safesearch="off", 
                max_results=10
            ))

            if ddg_images:
                print(f"✅ Found {len(ddg_images)} images via Search")
                for img in ddg_images:
                    # ვიღებთ სურათის პირდაპირ ლინკს
                    if 'image' in img:
                        data['images'].append(img['image'])
                    elif 'thumbnail' in img:
                        data['images'].append(img['thumbnail'])

        # 2. ტექსტური ინფორმაციის ძებნა (სათაურისთვის)
        with DDGS() as ddgs:
            ddg_text = list(ddgs.text(f"{vin} bidfax", max_results=1))
            if ddg_text:
                first_result = ddg_text[0]
                # სათაურიდან ვცდილობთ მანქანის სახელის ამოღებას
                # მაგ: "2018 BMW 5 SERIES - Bidfax"
                title_raw = first_result.get('title', '')
                clean_title = title_raw.split('-')[0].split('|')[0].strip()
                data['title'] = clean_title
                
                # აღწერაში შეიძლება იყოს გარბენი
                body_text = first_result.get('body', '')
                if 'mi' in body_text or 'km' in body_text:
                    data['info']['odometer'] = "იხილეთ ფოტოზე" # ზუსტი ამოღება რთულია, მაგრამ ფოტო გვაქვს

        if not data['images']:
            return {"error": "სამწუხაროდ, ამ VIN-ზე ფოტოები საძიებო სისტემაშიც არ იძებნება."}

        return data

    except Exception as e:
        print(f"🔥 Search Error: {e}")
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