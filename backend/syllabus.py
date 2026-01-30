import re
from collections import Counter
from pathlib import Path

import pymupdf

def extract_clean_body_text(
    pdf_path, top_margin_ratio=0.1, bottom_margin_ratio=0.1, repetition_threshold=0.6,font_size_tolerance=1.5):

    doc = pymupdf.open(pdf_path)
    num_pages = len(doc)

    # ------------------------------------------------------------
    # Pass 1: Collect global statistics
    # ------------------------------------------------------------
    line_counter = Counter()
    font_sizes = Counter()

    for page in doc:
        page_dict = page.get_text("dict")
        for block in page_dict["blocks"]:
            for line in block.get("lines", []):
                line_text = "".join(span["text"] for span in line["spans"]).strip()
                if line_text:
                    line_counter[line_text.lower()] += 1
                for span in line["spans"]:
                    font_sizes[span["size"]] += 1

    # Most common font size = body text
    body_font_size = font_sizes.most_common(1)[0][0]

    # ------------------------------------------------------------
    # Helper functions
    # ------------------------------------------------------------
    def is_repeated(text):
        return line_counter[text.lower()] / num_pages >= repetition_threshold

    def is_page_number(text):
        return bool(re.fullmatch(r"\d{1,4}", text))

    def is_body_font(size):
        return abs(size - body_font_size) <= font_size_tolerance

    # ------------------------------------------------------------
    # Pass 2: Extract filtered body text
    # ------------------------------------------------------------
    output_pages = []

    for page in doc:
        page_height = page.rect.height
        page_dict = page.get_text("dict")
        page_lines = []

        for block in page_dict["blocks"]:  
            if block["type"] != 0:  # not text
                continue

            y0, y1 = block["bbox"][1], block["bbox"][3]

            # Positional filtering (header/footer)
            if y0 < page_height * top_margin_ratio:
                continue
            if y1 > page_height * (1 - bottom_margin_ratio):
                continue

            for line in block.get("lines", []):
                spans = line["spans"]
                text = "".join(span["text"] for span in spans).strip()

                if not text:
                    continue
                if is_page_number(text):
                    continue
                if is_repeated(text):
                    continue
                if not any(is_body_font(span["size"]) for span in spans):
                    continue

                page_lines.append(text)

        output_pages.append("\n".join(page_lines))

    full_text = "\n\n".join(output_pages)

    # Fix hyphenation and whitespace
    full_text = re.sub(r"-\n", "", full_text)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)

    return full_text.strip()


def save_syllabus_text(text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    # Extract Syllabi
    clean_text = extract_clean_body_text("/home/ernie/grail_scraper/syllabi/9570_y26_sy.pdf")
    output_path = Path("/home/ernie/grail_scraper/syllabi/econs.txt")
    save_syllabus_text(clean_text, output_path)
    print(clean_text)
