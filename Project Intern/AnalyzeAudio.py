import os
import json
from google.genai import types
from GeminiClient import safe_generate_content
from Config import ALL_IN_ONE_UNIVERSAL_PROMPT, TRANSCRIBE_TRANSLATE_ONLY_PROMPT, MODEL_NAME

def _call_gemini_with_audio(prompt: str, audio_path: str) -> dict:
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    audio_part = types.Part.from_bytes(
        data=audio_bytes,
        mime_type="audio/wav"
    )

    response = safe_generate_content(
        model=MODEL_NAME,
        contents=[prompt, audio_part],
        config={"response_mime_type": "application/json"},
        max_retries=10,
        base_delay=5.0,
        jitter=1.5
    )

    raw = response.text or ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON returned", "raw": raw}

def transcribe_translate_audio(audio_path: str) -> dict:
    """Cheaper Gemini call: transcript + translation only."""
    return _call_gemini_with_audio(TRANSCRIBE_TRANSLATE_ONLY_PROMPT, audio_path)

def analyze_audio_all_in_one(audio_path: str, scenarios_text: str) -> dict:
    prompt = ALL_IN_ONE_UNIVERSAL_PROMPT + f"\n\nScenarios:\n{scenarios_text}"
    return _call_gemini_with_audio(prompt, audio_path)

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
