import os
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import classification_report, confusion_matrix

from DBConnector import get_db_connection

def fetch_labeled_data():
    """
    Requires:
      audio_sessions.human_sentiment_label (Complaint / Non-Complaint)
    Uses:
      transcript_english if exists else transcript_raw
    """
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("DB connection failed")

    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            COALESCE(transcript_english, transcript_raw) AS text,
            human_sentiment_label AS label
        FROM audio_sessions
        WHERE human_sentiment_label IS NOT NULL
          AND (transcript_raw IS NOT NULL OR transcript_english IS NOT NULL)
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["text"] = df["text"].fillna("").astype(str)
    df["y"] = df["label"].apply(lambda x: 1 if "complaint" in str(x).lower() else 0)
    return df

def main():
    df = fetch_labeled_data()

    if len(df) < 50:
        print(f"Not enough labeled data to train SVM. Found {len(df)} rows. Need ~50 minimum, 200+ recommended.")
        return

    X_train, X_test, y_train, y_test = train_test_split(
        df["text"], df["y"],
        test_size=0.2,
        random_state=42,
        stratify=df["y"]
    )

    base = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1,2), max_features=50000)),
        ("svm", LinearSVC(class_weight="balanced"))
    ])

    clf = CalibratedClassifierCV(base, cv=3)  # adds predict_proba
    clf.fit(X_train, y_train)

    pred = clf.predict(X_test)
    print("Confusion matrix:\n", confusion_matrix(y_test, pred))
    print(classification_report(y_test, pred, digits=4))

    os.makedirs("models", exist_ok=True)
    out_path = "models/complaint_svm.joblib"
    joblib.dump(clf, out_path)
    print("Saved model:", out_path)

if __name__ == "__main__":
    main()
