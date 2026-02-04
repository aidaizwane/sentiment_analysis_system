import os
import json
from GeminiClient import safe_generate_content
from Config import MODEL_NAME, ALL_IN_ONE_UNIVERSAL_PROMPT
from pypdf import PdfReader
from docx import Document

def extract_text_from_file(file_path: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Text file not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()

    if ext == ".pdf":
        parts = []
        with open(file_path, "rb") as f:
            reader = PdfReader(f)
            for page in reader.pages:
                t = page.extract_text() or ""
                if t.strip():
                    parts.append(t)
        return "\n".join(parts).strip()

    if ext == ".docx":
        doc = Document(file_path)
        parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(parts).strip()

    raise ValueError(f"Unsupported text-based file type: {ext}")


def analyze_text_all_in_one(text: str, scenarios_text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"error": "Empty text input"}

    prompt = (
        ALL_IN_ONE_UNIVERSAL_PROMPT
        + f"\n\nScenarios:\n{scenarios_text}"
        + f'\n\nINPUT TEXT:\n"""{text}"""'
    )

    response = safe_generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )

    raw = response.text or ""
    print("RAW TEXT ALL-IN-ONE RESPONSE:", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON returned", "raw": raw}


def format_language_used(languages):
    if not languages:
        return "Unknown"

    if isinstance(languages, str):
        languages = [languages]

    mapping = {
        "english": "English",
        "bahasa": "Bahasa",
        "bahasa melayu": "Bahasa",
        "malay": "Bahasa",
        "hokkien": "Hokkien",
        "mandarin": "Mandarin",
        "chinese": "Mandarin"
    }

    normalized = []
    for lang in languages:
        key = str(lang).lower().strip()
        normalized.append(mapping.get(key, lang))

    return ", ".join(sorted(set(normalized)))
