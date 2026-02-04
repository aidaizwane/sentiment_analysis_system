import os
import joblib
from typing import Tuple

MODEL_PATH = os.getenv("SVM_MODEL_PATH", "models/complaint_svm.joblib")
_model = None

def load_model():
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"SVM model not found at {MODEL_PATH}. Train it first (run train_svm.py)."
            )
        _model = joblib.load(MODEL_PATH)
    return _model

def predict_complaint(text: str) -> Tuple[str, float]:
    """
    Returns (label, p_complaint).
    label: 'Complaint' or 'Non-Complaint'
    """
    text = (text or "").strip()
    if not text:
        return "Non-Complaint", 0.5

    m = load_model()
    proba = m.predict_proba([text])[0]  # [p(non), p(complaint)]
    p_complaint = float(proba[1])
    label = "Complaint" if p_complaint >= 0.5 else "Non-Complaint"
    return label, p_complaint

def should_call_gemini(p: float, low: float = 0.25, high: float = 0.75) -> bool:
    """Uncertain zone -> call Gemini full."""
    return low <= p <= high
