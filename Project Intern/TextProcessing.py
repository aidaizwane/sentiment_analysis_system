import os
from datetime import datetime

from DBConnector import insert_text_record, get_all_scenarios
from AnalyzeText import extract_text_from_file, analyze_text_all_in_one, format_language_used
from Utils import detect_file_type, get_file_created_at

def process_single_text_file(file_path: str):
    """
    Analyze a single text-based file and insert record into DB.
    Returns dict for UI usage.
    """
    scenarios = get_all_scenarios()
    scenario_text = "\n".join(
        f"ID {s['id']}: {s['name']} — {s['description']}"
        for s in scenarios
    )

    text = extract_text_from_file(file_path)
    result = analyze_text_all_in_one(text, scenario_text)

    if result.get("error"):
        print("[Error] Text analysis failed:", result.get("raw", ""))
        return {"success": False, "error": result.get("error"), "raw": result.get("raw")}

    language_used = format_language_used(result.get("language_used"))
    sentiment = result.get("sentiment", {}) or {}

    file_created_at = get_file_created_at(file_path)
    uploaded_at = datetime.now()

    insert_text_record(
        file_name=os.path.basename(file_path),
        text_path=file_path,
        file_type=detect_file_type(file_path),
        transcript=result.get("transcript"),
        translation=result.get("translation"),
        sentiment_label=sentiment.get("label"),
        sentiment_score=sentiment.get("score"),
        sentiment_tone=sentiment.get("tone"),
        explanation=sentiment.get("explanation"),
        scenario_id=result.get("scenario_id"),
        language_used=language_used,
        file_created_at=file_created_at,
        uploaded_at=uploaded_at
    )

    return {
        "success": True,
        "file_name": os.path.basename(file_path),
        "file_type": "text",
        "transcript": result.get("transcript"),
        "translation": result.get("translation"),
        "language_used": language_used,
        "sentiment": sentiment.get("label"),
        "score": sentiment.get("score"),
        "tone": sentiment.get("tone"),
        "explanation": sentiment.get("explanation"),
        "scenario_id": result.get("scenario_id")
    }
