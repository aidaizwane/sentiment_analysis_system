import os
from datetime import datetime

from DBConnector import insert_session_record, get_all_scenarios
from AnalyzeAudio import analyze_audio_all_in_one, transcribe_translate_audio, format_language_used
from Utils import detect_file_type, get_file_created_at

# SVM is optional: if model not trained yet, we fallback to Gemini FULL
try:
    from LocalSVM import predict_complaint, should_call_gemini
    _SVM_AVAILABLE = True
except Exception:
    _SVM_AVAILABLE = False

def process_single_audio_file(audio_path: str):
    """
    Hybrid pipeline:
    1) Gemini (cheap) -> transcript + translation
    2) Local SVM -> first-pass complaint vs non-complaint
    3) If SVM uncertain OR model missing -> Gemini (full) for sentiment + scenario + explanation

    Returns dict for UI usage.
    """
    scenarios = get_all_scenarios()
    scenario_text = "\n".join(
        f"ID {s['id']}: {s['name']} — {s['description']}"
        for s in scenarios
    )

    # 1) Cheap transcription/translation
    base = transcribe_translate_audio(audio_path)
    if base.get("error"):
        print("[Error] Transcribe/translate failed:", base.get("raw", ""))
        return {"success": False, "error": base.get("error"), "raw": base.get("raw")}

    transcript = base.get("transcript")
    translation = base.get("translation")
    language_used = format_language_used(base.get("language_used"))

    # 2) SVM first-pass (optional)
    sentiment_label = None
    sentiment_score = None
    sentiment_tone = None
    explanation = None
    scenario_id = None

    need_full = True
    p = 0.5

    if _SVM_AVAILABLE:
        try:
            text_for_cls = (translation or transcript or "").strip()
            svm_label, p = predict_complaint(text_for_cls)
            need_full = should_call_gemini(p)
            if not need_full:
                sentiment_label = "Complaint" if svm_label == "Complaint" else "Non-Complaint"
                sentiment_score = int(round(p * 100))
                sentiment_tone = "auto"
                explanation = f"Auto-classified by local SVM (confidence={sentiment_score}%)."
                scenario_id = None
        except Exception as e:
            # any SVM error -> fallback to Gemini full
            print("[SVM] Fallback to Gemini FULL due to error:", e)
            need_full = True

    # 3) Gemini FULL if needed
    if need_full:
        full = analyze_audio_all_in_one(audio_path, scenario_text)
        if full.get("error"):
            print("[Error] Full audio analysis failed:", full.get("raw", ""))
            return {"success": False, "error": full.get("error"), "raw": full.get("raw")}

        sentiment = full.get("sentiment", {}) or {}
        sentiment_label = sentiment.get("label")
        sentiment_score = sentiment.get("score")
        sentiment_tone = sentiment.get("tone")
        explanation = sentiment.get("explanation")
        scenario_id = full.get("scenario_id")

        transcript = full.get("transcript") or transcript
        translation = full.get("translation") or translation
        language_used = format_language_used(full.get("language_used")) or language_used

    file_created_at = get_file_created_at(audio_path)
    uploaded_at = datetime.now()

    insert_session_record(
        file_name=os.path.basename(audio_path),
        audio_path=audio_path,
        file_type=detect_file_type(audio_path),
        transcript=transcript,
        translation=translation,
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
        sentiment_tone=sentiment_tone,
        explanation=explanation,
        scenario_id=scenario_id,
        language_used=language_used,
        file_created_at=file_created_at,
        uploaded_at=uploaded_at
    )

    return {
        "success": True,
        "file_name": os.path.basename(audio_path),
        "file_type": "audio",
        "transcript": transcript,
        "translation": translation,
        "language_used": language_used,
        "sentiment": sentiment_label,
        "score": sentiment_score,
        "tone": sentiment_tone,
        "explanation": explanation,
        "scenario_id": scenario_id
    }
