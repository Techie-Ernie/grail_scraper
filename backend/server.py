from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pymupdf
from scraper import HolyGrailScraper
import glob 
from collections import Counter
import re

app = FastAPI()

# Enable CORS for frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapedData(BaseModel):
    text: str

class AIResult(BaseModel):
    result: str


@app.get("/test")
def test_connection():
    return {"status": "connected", "message": "FastAPI backend is running!"}

@app.get("/data")
def get_data():
    files = glob.glob('/home/ernie/grail_scraper/documents/econs/question_papers/*.pdf')
    syllabus = "/home/ernie/grail_scraper/syllabi/econs.txt"
    with open(syllabus, 'r') as f:
        syllabus_text = f.read()
    prompts = ["Syllabus: " + syllabus_text + "Text: \n"]
    model_prompt = ""
    doc = pymupdf.open(files[0])
    for page in doc:
        model_prompt += str(page.get_text()).replace('\n', ' ')
        model_prompt = re.sub(r'(\.\s*)\n\[(\d+)\]', r'\1 [\2]', model_prompt) # pre-merge lines with the marks
    print(model_prompt)
    prompts.append(model_prompt)
    return {"text": str(prompts)}

@app.post("/data")
def receive_data(data: ScrapedData):
    print("Received data:", data.text)
    return {"status": "ok"}

@app.post("/ai-result")
def receive_ai_result(result: AIResult):
    print("AI OUTPUT:", result.result)

    # trigger next step 
    return {"status": "received"}
