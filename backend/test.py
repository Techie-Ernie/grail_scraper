import glob 
import pymupdf
from scraper import HolyGrailScraper
from collections import Counter 
import re
from pathlib import Path
import os

project_root = Path(__file__).resolve().parents[1]
documents_root = Path(os.environ.get("DOCUMENTS_ROOT", str(project_root / "documents")))
files = glob.glob(str(documents_root / "*.pdf"))
for file in files:
    print(file)
    doc = pymupdf.open(file)
    for page in doc: # iterate the document pages
        text = page.get_text() # get plain text encoded as UTF-8
    clean_text = extract_clean_body_text(file)
    print(clean_text)
