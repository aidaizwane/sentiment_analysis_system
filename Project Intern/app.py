import os
import re
import json
from datetime import datetime
from functools import wraps
from io import BytesIO
from threading import Lock

from docx import Document
from pypdf import PdfReader

from dotenv import load_dotenv
load_dotenv()

from werkzeug.security import check_password_hash

from flask import (
    Flask,
    Response,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_file,
    abort,
    jsonify,
)

# ========================
# Optional Push (safe import)
# ========================
try:
    from pywebpush import webpush, WebPushException
    HAS_PUSH = True
except Exception:
    HAS_PUSH = False
    webpush = None
    WebPushException = Exception

# ========================
# Use YOUR existing DBConnector.py (NO db.py needed)
# ========================
from DBConnector import get_db_connection


# ========================
# Paths / App Config
# ========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Template root = Interface
# render:
# - Interface/login.html
# - Interface/admin/dashboard.html   -> render_template("admin/dashboard.html")
# - Interface/user/dashboard.html    -> render_template("user/dashboard.html")
TEMPLATE_ROOT = os.path.join(BASE_DIR, "Interface")

STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploaded_files")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

TRANSCRIPT_FOLDER = os.path.join(BASE_DIR, "transcripts")
os.makedirs(TRANSCRIPT_FOLDER, exist_ok=True)

app = Flask(
    __name__,
    template_folder=TEMPLATE_ROOT,
    static_folder=STATIC_DIR
)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ========================
# Jobs + Push storage
# ========================
JOBS = {}
JOBS_LOCK = Lock()

PUSH_SUBSCRIPTIONS = {}
PUSH_SUB_FILE = os.path.join(BASE_DIR, "push_subscriptions.json")
PUSH_LOCK = Lock()


def _load_push_subs():
    if not os.path.exists(PUSH_SUB_FILE):
        return {}
    try:
        with open(PUSH_SUB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_push_subs(data):
    try:
        with open(PUSH_SUB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


PUSH_SUBSCRIPTIONS = _load_push_subs()


# ========================
# Push Notification Config
# ========================
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY_PEM = ""

pem_path = os.getenv("VAPID_PRIVATE_KEY_PEM_PATH", "")
if pem_path:
    pem_path = os.path.join(BASE_DIR, pem_path)
    if os.path.exists(pem_path):
        try:
            with open(pem_path, "r", encoding="utf-8") as f:
                VAPID_PRIVATE_KEY_PEM = f.read()
        except Exception:
            VAPID_PRIVATE_KEY_PEM = ""

VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@company.com")
VAPID_CLAIMS = {"sub": VAPID_SUBJECT}


def send_push_to_user(username: str, title: str, body: str, url: str = "/sentiment_result"):
    """
    Safe push sender.
    If pywebpush not installed -> returns False, message.
    """
    if not HAS_PUSH:
        return False, "pywebpush not installed"

    if not (VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY_PEM):
        return False, "VAPID keys not configured"

    with PUSH_LOCK:
        sub = PUSH_SUBSCRIPTIONS.get(username)

    if not sub:
        return False, "No push subscription saved"

    payload = json.dumps({"title": title, "body": body, "url": url})

    try:
        webpush(
            subscription_info=sub,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY_PEM,
            vapid_claims=VAPID_CLAIMS,
        )
        return True, "Sent"
    except WebPushException as e:
        return False, f"Push failed: {repr(e)}"
    except Exception as e:
        return False, f"Push error: {repr(e)}"


# ========================
# Utils
# ========================
def parse_date(d):
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        return None


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", os.path.basename(name or "file"))


def detect_file_type(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".wav"):
        return "wav"
    if name.endswith(".mp3"):
        return "mp3"
    if name.endswith(".m4a"):
        return "m4a"
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".docx"):
        return "docx"
    if name.endswith(".txt"):
        return "txt"
    return "unknown"


def format_dt_parts(dt):
    if not dt:
        return ("Not available", "")
    if not isinstance(dt, datetime):
        try:
            dt = datetime.fromisoformat(str(dt))
        except Exception:
            return (str(dt), "")
    return (dt.strftime("%d %b %Y"), dt.strftime("%I:%M %p"))


def normalize_sentiment(label: str) -> str:
    s = (label or "").strip().lower()
    if "complaint" in s and "non" not in s:
        return "complaint"
    if "non" in s:
        return "non"
    if "positive" in s:
        return "non"
    if "neutral" in s:
        return "non"
    return ""


# ========================
# Document extract
# ========================
def extract_text_from_docx(file_storage) -> str:
    data = file_storage.read()
    doc = Document(BytesIO(data))
    parts = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n".join(parts).strip()


def extract_text_from_pdf(file_storage) -> str:
    data = file_storage.read()
    reader = PdfReader(BytesIO(data))
    parts = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            parts.append(t)
    return "\n".join(parts).strip()


def allowed_audio(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"wav", "mp3", "m4a"}


def allowed_doc(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"pdf", "docx", "txt"}


# ========================
# Auth decorators
# ========================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        if session.get("account_type") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def user_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        if session.get("account_type") != "user":
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ========================
# DB helpers (your schema)
# ========================
def fetch_admin(username: str):
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT adminID, admin_username, admin_password FROM admin_account WHERE admin_username=%s LIMIT 1",
            (username,)
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def fetch_user(username: str):
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT userID, username, full_name, email, role, user_password
            FROM user_account
            WHERE username=%s
            LIMIT 1
            """,
            (username,)
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def verify_password(stored: str, provided: str) -> bool:
    """
    Supports:
    - werkzeug hashed (pbkdf2:/scrypt:/argon2:)
    - plaintext compare
    """
    if not stored:
        return False

    stored = str(stored)
    provided = str(provided or "")

    if stored.startswith(("pbkdf2:", "scrypt:", "argon2:")):
        try:
            return check_password_hash(stored, provided)
        except Exception:
            return False

    return stored == provided


# ========================
# Sessions fetch/update (match your tables)
# audio_sessions PK = session_id
# text_sessions PK = id
# ========================
def fetch_sessions_for_ui(limit: int = 2000):
    conn = get_db_connection()
    if not conn:
        return []
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            f"""
            SELECT
                a.session_id AS id,
                'audio' AS source_type,
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
                t.id AS id,
                'text' AS source_type,
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
            LIMIT {int(limit)}
            """
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def update_human_sentiment_label(source_type: str, record_id: int, label: str):
    """
    label: "Complaint" / "Non-Complaint"
    """
    label = (label or "").strip()
    if label not in ("Complaint", "Non-Complaint"):
        raise ValueError("Invalid label. Use 'Complaint' or 'Non-Complaint'")

    conn = get_db_connection()
    if not conn:
        raise RuntimeError("DB connection failed")

    cur = conn.cursor()
    try:
        if source_type == "audio":
            cur.execute(
                """
                UPDATE audio_sessions
                SET human_sentiment_label=%s, human_updated_at=%s
                WHERE session_id=%s
                """,
                (label, datetime.now(), int(record_id))
            )
        elif source_type == "text":
            cur.execute(
                """
                UPDATE text_sessions
                SET human_sentiment_label=%s, human_updated_at=%s
                WHERE id=%s
                """,
                (label, datetime.now(), int(record_id))
            )
        else:
            raise ValueError("Invalid source_type. Must be 'audio' or 'text'")

        conn.commit()
    finally:
        cur.close()
        conn.close()


# ========================
# Dashboard builder (safe fallback)
# ========================
def _build_dashboard_data_safe(username: str, period: str, source_type: str, is_admin: bool):
    """
    Try to use your services.dashboard_service.build_dashboard_data
    If signature mismatch / error => fallback simple data.
    """
    try:
        from Services.dashboard_service import build_dashboard_data  # local import to avoid crash
        # Common patterns:
        # build_dashboard_data(username, period, source_type)
        # or build_dashboard_data(username=username, period=..., source_type=...)
        try:
            return build_dashboard_data(username=username, period=period, source_type=source_type)
        except TypeError:
            return build_dashboard_data(username, period, source_type)
    except Exception as e:
        # fallback minimal payload so template won't crash (if template expects dashboard_data)
        now = datetime.now()
        return {
            "period": period or f"{now.year}-{now.month:02d}",
            "source_type": source_type or "",
            "error": f"dashboard_service error: {e}"
        }


# ========================
# Service Worker + Push endpoints
# ========================
@app.get("/sw.js")
def sw():
    return app.send_static_file("sw.js")


@app.get("/vapidPublicKey")
@login_required
def vapid_public_key():
    if not VAPID_PUBLIC_KEY:
        return ("VAPID_PUBLIC_KEY not set", 500)
    return Response(VAPID_PUBLIC_KEY, mimetype="text/plain")


@app.post("/saveSubscription")
@login_required
def save_subscription():
    sub = request.get_json(force=True)
    username = session.get("username")

    with PUSH_LOCK:
        PUSH_SUBSCRIPTIONS[username] = sub
        _save_push_subs(PUSH_SUBSCRIPTIONS)

    return jsonify({"ok": True})


@app.get("/debug_subs")
@login_required
def debug_subs():
    username = session.get("username")
    return jsonify({
        "current_user": username,
        "has_subscription": username in PUSH_SUBSCRIPTIONS,
        "saved_users": list(PUSH_SUBSCRIPTIONS.keys())
    })


# ========================
# Root redirect
# ========================
@app.route("/")
def root():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    if session.get("account_type") == "admin":
        return redirect(url_for("admin_dashboard"))

    return redirect(url_for("dashboard"))


# ========================
# LOGIN (two buttons)
# login.html must send login_as = admin/user
# ========================
@app.route("/login", methods=["GET", "POST"])
def login():
    """
    login_as:
      - "admin"
      - "user"
    """
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        login_as = (request.form.get("login_as") or "").strip().lower()

        if not username or not password:
            flash("Please enter username and password.")
            return render_template("login.html")

        if login_as not in ("admin", "user"):
            flash("Please click Admin Login or User Login.")
            return render_template("login.html")

        # ADMIN login
        if login_as == "admin":
            admin = fetch_admin(username)
            if admin and verify_password(admin.get("admin_password"), password):
                session.clear()
                session["logged_in"] = True
                session["account_type"] = "admin"
                session["adminID"] = admin.get("adminID")
                session["username"] = admin.get("admin_username")
                flash("Admin login successful.")
                return redirect(url_for("admin_dashboard"))

            flash("Invalid admin username or password.")
            return render_template("login.html")

        # USER login
        user = fetch_user(username)
        if user and verify_password(user.get("user_password"), password):
            session.clear()
            session["logged_in"] = True
            session["account_type"] = "user"
            session["userID"] = user.get("userID")
            session["username"] = user.get("username")
            session["full_name"] = user.get("full_name") or user.get("username")
            session["email"] = user.get("email") or ""
            session["role"] = user.get("role") or "user"
            flash("User login successful.")
            return redirect(url_for("dashboard"))

        flash("Invalid user username or password.")
        return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))


# ========================
# Admin Dashboard
# Template path: Interface/admin/dashboard.html
# ========================
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    period = request.args.get("period", "")
    source_type = request.args.get("source_type", "")

    dashboard_data = _build_dashboard_data_safe(
        username=session.get("username"),
        period=period,
        source_type=source_type,
        is_admin=True
    )

    # IMPORTANT: template must exist at Interface/admin/dashboard.html
    return render_template(
        "admin/dashboard.html",
        dashboard_data=dashboard_data,
        dashboard_action=url_for("admin_dashboard"),
        is_admin=True,
        username=session.get("username"),
        adminID=session.get("adminID"),
    )


# ========================
# User Dashboard
# Template path: Interface/user/dashboard.html
# ========================
@app.route("/dashboard")
@user_required
def dashboard():
    period = request.args.get("period", "")
    source_type = request.args.get("source_type", "")
    username = session.get("username")

    dashboard_data = _build_dashboard_data_safe(
        username=username,
        period=period,
        source_type=source_type,
        is_admin=False
    )

    return render_template(
        "user/dashboard.html",
        dashboard_data=dashboard_data,
        dashboard_action=url_for("dashboard"),
        is_admin=False,
        username=username,
        full_name=session.get("full_name"),
        email=session.get("email"),
        role=session.get("role"),
    )


# ========================
# Sentiment Result List
# Template path: Interface/user/sentiment_result.html
# ========================
@app.route("/sentiment_result")
@login_required
def sentiment_result():
    file_type = request.args.get("file_type", "")
    sentiment = request.args.get("sentiment", "")
    start = parse_date(request.args.get("start_date", ""))
    end = parse_date(request.args.get("end_date", ""))
    q = (request.args.get("q", "") or "").strip().lower()

    page = int(request.args.get("page", 1))
    per_page = 10

    rows = fetch_sessions_for_ui(limit=5000)

    filtered = []
    for r in rows:
        fname = r.get("file_name") or ""
        ftype = detect_file_type(fname)

        if file_type and ftype != file_type:
            continue

        if sentiment and str(r.get("sentiment_label") or "").strip().lower() != sentiment.strip().lower():
            continue

        dt = r.get("uploaded_at")
        if (start or end):
            if not isinstance(dt, datetime):
                try:
                    dt = datetime.fromisoformat(str(dt))
                except Exception:
                    continue
            d = dt.date()
            if start and d < start:
                continue
            if end and d > end:
                continue

        if q and q not in fname.lower():
            continue

        summ = (r.get("sentiment_explanation") or "").strip()
        summ = re.sub(r"\s+", " ", summ)
        if len(summ) > 90:
            summ = summ[:90] + "..."

        d_disp, t_disp = format_dt_parts(dt)

        filtered.append({
            "db_id": r.get("id"),
            "source_type": r.get("source_type"),
            "audio_file": fname,
            "file_type": ftype,
            "summary": summ,
            "sentiment": r.get("sentiment_label") or "",
            "score": r.get("sentiment_score"),
            "tone": r.get("sentiment_tone") or "",
            "explanation": r.get("sentiment_explanation") or "",
            "scenario_id": r.get("scenario_id"),
            "transcript": r.get("transcript_raw") or "",
            "translation": r.get("transcript_english") or "",
            "datetime": dt,
            "date_display": d_disp,
            "time_display": t_disp,
            "human_sentiment_label": r.get("human_sentiment_label"),
            "human_updated_at": r.get("human_updated_at"),
        })

    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start_i = (page - 1) * per_page
    end_i = start_i + per_page

    page_rows = filtered[start_i:end_i]

    return render_template(
        "user/sentiment_result.html",
        rows=page_rows,
        total=total,
        page=page,
        total_pages=total_pages,
        file_type=file_type,
        sentiment=sentiment,
        start_date=request.args.get("start_date", ""),
        end_date=request.args.get("end_date", ""),
        q=request.args.get("q", ""),
    )


# ========================
# Comment / Human label update
# Template: Interface/user/comment.html
# ========================
@app.route("/comment/<source_type>/<int:db_id>", methods=["GET", "POST"])
@login_required
def comment_page(source_type, db_id):
    source_type = (source_type or "").strip().lower()
    if source_type not in ("audio", "text"):
        abort(404)

    rows = fetch_sessions_for_ui(limit=5000)
    row = None
    for r in rows:
        try:
            if r.get("source_type") == source_type and int(r.get("id")) == int(db_id):
                row = r
                break
        except Exception:
            continue
    if not row:
        abort(404)

    comments_file = os.path.join(BASE_DIR, "comments_store.json")
    try:
        if os.path.exists(comments_file):
            with open(comments_file, "r", encoding="utf-8") as f:
                store = json.load(f)
        else:
            store = {}
    except Exception:
        store = {}

    store_key = f"{source_type}:{db_id}"

    if request.method == "POST":
        comment = (request.form.get("comment") or "").strip()
        store[store_key] = comment

        try:
            with open(comments_file, "w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # If comment indicates label => store DB
        c_low = comment.lower()
        if c_low in ("complaint", "non-complaint", "non complaint", "non"):
            human_label = "Complaint" if ("complaint" in c_low and "non" not in c_low) else "Non-Complaint"
            try:
                update_human_sentiment_label(source_type, db_id, human_label)
            except Exception as e:
                flash(f"Failed to save label: {e}")

        flash("Comment saved.")
        return redirect(url_for("sentiment_result"))

    existing_comment = store.get(store_key, "")

    return render_template(
        "user/comment.html",
        row=row,
        row_id=db_id,
        source_type=source_type,
        existing_comment=existing_comment
    )


# ========================
# Transcript view
# Template: Interface/user/transcript_view.html
# ========================
@app.route("/transcript/<source_type>/<int:db_id>")
@login_required
def transcript_view(source_type, db_id):
    source_type = (source_type or "").strip().lower()
    if source_type not in ("audio", "text"):
        abort(404)

    rows = fetch_sessions_for_ui(limit=5000)
    row = None
    for r in rows:
        try:
            if r.get("source_type") == source_type and int(r.get("id")) == int(db_id):
                row = r
                break
        except Exception:
            continue
    if not row:
        abort(404)

    file_name = row.get("file_name") or ""
    safe_name = safe_filename(file_name)
    safe_base = os.path.splitext(safe_name)[0]
    txt_path = os.path.join(TRANSCRIPT_FOLDER, f"{safe_base}.txt")

    transcript_text = ""
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                transcript_text = f.read().strip()
        except Exception:
            transcript_text = ""

    if not transcript_text:
        transcript_text = (row.get("transcript_raw") or "").strip()

    if not transcript_text:
        transcript_text = "No transcript available."

    return render_template(
        "user/transcript_view.html",
        audio_file=file_name,
        scenario_title=str(row.get("scenario_id") or ""),
        transcript=transcript_text
    )


# ========================
# Audio streaming
# ========================
@app.route("/audio/<path:filename>")
@login_required
def audio_stream(filename):
    safe_name = safe_filename(filename)
    audio_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    if not os.path.exists(audio_path):
        abort(404)
    return send_file(audio_path, mimetype="audio/wav", as_attachment=False)


# ========================
# Job status API
# ========================
@app.get("/api/job_status")
@login_required
def api_job_status():
    job_id = request.args.get("job_id") or session.get("last_job_id")
    if not job_id:
        return jsonify({"status": "none"})

    with JOBS_LOCK:
        job = JOBS.get(job_id)

    if not job:
        return jsonify({"status": "none"})

    if job.get("username") != session.get("username"):
        return jsonify({"status": "none"})

    return jsonify({"status": job.get("status"), "message": job.get("message", "")})


# ========================
# Notifications API (placeholder so JS won't crash)
# ========================
@app.get("/api/notifications/unread-count")
@login_required
def api_unread_count():
    return jsonify({"unread_count": 0})


@app.get("/api/notifications")
@login_required
def api_notifications():
    return jsonify({"unread_count": 0, "items": []})


@app.post("/api/notifications/mark-read")
@login_required
def api_mark_read():
    return jsonify({"ok": True})


@app.post("/api/notifications/mark-all-read")
@login_required
def api_mark_all_read():
    return jsonify({"ok": True})


# ========================
# Run
# ========================
if __name__ == "__main__":
    # use_reloader False to avoid double threads
    app.run(debug=True, use_reloader=False)
