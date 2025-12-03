import os
import uvicorn
import google.generativeai as genai
from fastapi import FastAPI
from pydantic import BaseModel
import json

app = FastAPI()

# Render-ს სჭირდება გარემოს ცვლადები (Environment Variables)
# ამას Render-ის პარამეტრებში ჩავწერთ მოგვიანებით
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash',
                                  generation_config={"response_mime_type": "application/json"})
else:
    print("Warning: GOOGLE_API_KEY not found!")

class CarRequest(BaseModel):
    myauto_text: str
    vin_history_text: str
    price: int

@app.get("/")
def home():
    return {"message": "Auto Detector API is running!"}

@app.post("/analyze")
def analyze_car(data: CarRequest):
    if not GOOGLE_API_KEY:
        return {"error": "API Key not configured"}

    prompt = f"""
    Role: Strict Georgian Car Expert.
    Task: Analyze car listing vs real history.
    
    Listing: {data.myauto_text}
    Price: {data.price} USD
    Real History: {data.vin_history_text}
    
    Output JSON: {{ "score": 0-100, "verdict": "string", "analysis": "string" }}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    # Render-ი დინამიურად გაძლევს პორტს, ამიტომ ეს აუცილებელია!
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)