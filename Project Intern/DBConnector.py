import os
import mysql.connector
from mysql.connector import Error
from datetime import datetime
from typing import List, Dict, Optional


# DB Connection (use ENV if available)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "root@123")
DB_NAME = os.getenv("DB_NAME", "sentiment_analysis")
DB_PORT = int(os.getenv("DB_PORT", "3306"))


def get_db_connection():
    """
    Create and return a MySQL connection.
    Returns None if connection fails.
    """
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            port=DB_PORT
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print("[DB ERROR]", e)
    return None

# INSERT: audio_sessions
def insert_session_record(
    *,
    file_name: str,
    audio_path: str,
    file_type: str,
    transcript: str,
    translation: str = None,
    sentiment_label: str = None,
    sentiment_score = None,  # allow decimal/int
    sentiment_tone: str = None,
    explanation: str = None,
    scenario_id: int = None,
    language_used: str = "Unknown",
    file_created_at=None,
    uploaded_at=None
):
    connection = get_db_connection()
    if not connection:
        return

    cursor = connection.cursor()

    sql = """
        INSERT INTO audio_sessions (
            audio_filename,
            audio_path,
            file_type,
            transcript_raw,
            transcript_english,
            sentiment_label,
            sentiment_score,
            sentiment_tone,
            sentiment_explanation,
            scenario_id,
            language_used,
            file_created_at,
            uploaded_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    values = (
        file_name,
        audio_path,
        file_type,
        transcript,
        translation,
        sentiment_label,
        sentiment_score,
        sentiment_tone,
        explanation,
        scenario_id,
        language_used,
        file_created_at,
        uploaded_at
    )

    try:
        cursor.execute(sql, values)
        connection.commit()
        print(f"[DB] Inserted AUDIO session: {file_name} (type={file_type})")
    except Error as e:
        print("[DB ERROR]", e)
    finally:
        cursor.close()
        connection.close()


# INSERT: text_sessions
def insert_text_record(
    *,
    file_name: str,
    text_path: str,
    file_type: str,
    transcript: str,
    translation: str = None,
    sentiment_label: str = None,
    sentiment_score = None,
    sentiment_tone: str = None,
    explanation: str = None,
    scenario_id: int = None,
    language_used: str = "Unknown",
    file_created_at=None,
    uploaded_at=None
):
    connection = get_db_connection()
    if not connection:
        return

    cursor = connection.cursor()

    sql = """
        INSERT INTO text_sessions (
            text_filename,
            text_path,
            file_type,
            transcript_raw,
            transcript_english,
            sentiment_label,
            sentiment_score,
            sentiment_tone,
            sentiment_explanation,
            scenario_id,
            language_used,
            file_created_at,
            uploaded_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    values = (
        file_name,
        text_path,
        file_type,
        transcript,
        translation,
        sentiment_label,
        sentiment_score,
        sentiment_tone,
        explanation,
        scenario_id,
        language_used,
        file_created_at,
        uploaded_at
    )

    try:
        cursor.execute(sql, values)
        connection.commit()
        print(f"[DB] Inserted TEXT session: {file_name} (type={file_type})")
    except Error as e:
        print("[DB ERROR]", e)
    finally:
        cursor.close()
        connection.close()


# SCENARIOS
def get_all_scenarios() -> List[Dict]:
    connection = get_db_connection()
    if not connection:
        return []

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                scenario_id AS id,
                scenario_name AS name,
                scenario_description AS description
            FROM scenarios
        """)
        return cursor.fetchall()
    except Error as e:
        print("[DB ERROR]", e)
        return []
    finally:
        cursor.close()
        connection.close()


# UPDATE HUMAN LABEL (AUDIO)
def update_human_sentiment_label(session_id: int, human_label: str) -> bool:
    """
    Store CS correction label (Complaint / Non-Complaint) for a given audio_sessions row.
    Table audio_sessions PK = session_id (NOT id).
    Requires DB columns:
      human_sentiment_label, human_updated_at
    """
    connection = get_db_connection()
    if not connection:
        return False

    cursor = connection.cursor()
    try:
        cursor.execute("""
            UPDATE audio_sessions
            SET human_sentiment_label = %s,
                human_updated_at = %s
            WHERE session_id = %s
        """, (human_label, datetime.now(), int(session_id)))
        connection.commit()
        return True
    except Error as e:
        print("[DB ERROR]", e)
        return False
    finally:
        cursor.close()
        connection.close()


# FETCH FOR UI (AUDIO + TEXT)
def fetch_sessions_for_ui(limit: int = 500) -> List[Dict]:
    """
    Returns combined latest sessions (audio + text) for UI.
    Output fields:
      source_type, session_pk, file_name, file_type, transcript_raw, transcript_english,
      sentiment_label, sentiment_score, sentiment_tone, sentiment_explanation,
      scenario_id, uploaded_at, human_sentiment_label, human_updated_at
    """
    connection = get_db_connection()
    if not connection:
        return []

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                'audio' AS source_type,
                a.session_id AS session_pk,
                a.audio_filename AS file_name,
                a.file_type,
                a.transcript_raw,
                a.transcript_english,
                a.sentiment_label,
                CAST(a.sentiment_score AS DECIMAL(10,2)) AS sentiment_score,
                a.sentiment_tone,
                a.sentiment_explanation,
                a.scenario_id,
                a.uploaded_at,
                a.human_sentiment_label,
                a.human_updated_at
            FROM audio_sessions a

            UNION ALL

            SELECT
                'text' AS source_type,
                t.id AS session_pk,
                t.text_filename AS file_name,
                t.file_type,
                t.transcript_raw,
                t.transcript_english,
                t.sentiment_label,
                CAST(t.sentiment_score AS DECIMAL(10,2)) AS sentiment_score,
                t.sentiment_tone,
                t.sentiment_explanation,
                t.scenario_id,
                t.uploaded_at,
                t.human_sentiment_label,
                t.human_updated_at
            FROM text_sessions t

            ORDER BY uploaded_at DESC
            LIMIT %s
        """, (int(limit),))
        return cursor.fetchall()
    except Error as e:
        print("[DB ERROR]", e)
        return []
    finally:
        cursor.close()
        connection.close()


def find_admin(admin_username: str) -> Optional[Dict]:
    """
    admin_account:
      adminID, admin_username, admin_password
    """
    connection = get_db_connection()
    if not connection:
        return None

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT adminID, admin_username, admin_password
            FROM admin_account
            WHERE admin_username = %s
            LIMIT 1
        """, (admin_username,))
        return cursor.fetchone()
    except Error as e:
        print("[DB ERROR]", e)
        return None
    finally:
        cursor.close()
        connection.close()


def find_user(username: str) -> Optional[Dict]:
    """
    user_account:
      userID, username, full_name, email, role, user_password
    """
    connection = get_db_connection()
    if not connection:
        return None

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT userID, username, full_name, email, role, user_password
            FROM user_account
            WHERE username = %s
            LIMIT 1
        """, (username,))
        return cursor.fetchone()
    except Error as e:
        print("[DB ERROR]", e)
        return None
    finally:
        cursor.close()
        connection.close()
