from datetime import datetime
from DBConnector import get_db_connection

def _normalize_source_type(source_type: str):
    st = (source_type or "").strip().lower()
    if st in ("audio", "text"):
        return st
    return ""

def _normalize_sentiment(label: str):
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

def build_dashboard_data(username=None, period: str = "", source_type: str = ""):
    """
    Dashboard aggregation from DB tables:
      - audio_sessions
      - text_sessions

    NOTE:
    Your tables currently do NOT store username/userID consistently.
    So by default we aggregate GLOBAL.

    If later you add columns:
      - audio_sessions.username
      - text_sessions.username
    then we can filter by username.
    """
    now = datetime.now()
    if period:
        try:
            selected_year, selected_month = map(int, period.split("-"))
        except Exception:
            selected_year, selected_month = now.year, now.month
    else:
        selected_year, selected_month = now.year, now.month

    st = _normalize_source_type(source_type)

    # month labels
    month_labels = [f"{m:02d}" for m in range(1, 13)]
    line_complaint = [0] * 12
    line_non = [0] * 12

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Aggregate counts by month + sentiment (audio + text)
        # We use YEAR(uploaded_at) for timeline
        sql = """
            SELECT MONTH(uploaded_at) AS m, sentiment_label, COUNT(*) AS total
            FROM (
              SELECT uploaded_at, sentiment_label FROM audio_sessions
              UNION ALL
              SELECT uploaded_at, sentiment_label FROM text_sessions
            ) x
            WHERE YEAR(uploaded_at) = %s
        """
        params = [selected_year]

        # Optional source_type filter
        if st == "audio":
            sql = """
                SELECT MONTH(uploaded_at) AS m, sentiment_label, COUNT(*) AS total
                FROM audio_sessions
                WHERE YEAR(uploaded_at) = %s
                GROUP BY MONTH(uploaded_at), sentiment_label
            """
            params = [selected_year]
        elif st == "text":
            sql = """
                SELECT MONTH(uploaded_at) AS m, sentiment_label, COUNT(*) AS total
                FROM text_sessions
                WHERE YEAR(uploaded_at) = %s
                GROUP BY MONTH(uploaded_at), sentiment_label
            """
            params = [selected_year]
        else:
            sql += " GROUP BY MONTH(uploaded_at), sentiment_label"

        cur.execute(sql, params)
        rows = cur.fetchall()

        for m, label, total in rows:
            idx = int(m) - 1
            norm = _normalize_sentiment(label)
            if norm == "complaint":
                line_complaint[idx] += int(total)
            elif norm == "non":
                line_non[idx] += int(total)

        # Donut (selected month)
        month_c = line_complaint[selected_month - 1]
        month_n = line_non[selected_month - 1]
        total_all = month_c + month_n
        pct_c = round((month_c / total_all) * 100) if total_all else 0
        pct_n = round((month_n / total_all) * 100) if total_all else 0

        # Scenario overview for selected month (top 10)
        if st == "audio":
            sql2 = """
                SELECT scenario_id, sentiment_label, COUNT(*) AS total
                FROM audio_sessions
                WHERE YEAR(uploaded_at)=%s AND MONTH(uploaded_at)=%s
                GROUP BY scenario_id, sentiment_label
            """
            params2 = [selected_year, selected_month]
        elif st == "text":
            sql2 = """
                SELECT scenario_id, sentiment_label, COUNT(*) AS total
                FROM text_sessions
                WHERE YEAR(uploaded_at)=%s AND MONTH(uploaded_at)=%s
                GROUP BY scenario_id, sentiment_label
            """
            params2 = [selected_year, selected_month]
        else:
            sql2 = """
                SELECT scenario_id, sentiment_label, COUNT(*) AS total
                FROM (
                  SELECT uploaded_at, scenario_id, sentiment_label FROM audio_sessions
                  UNION ALL
                  SELECT uploaded_at, scenario_id, sentiment_label FROM text_sessions
                ) x
                WHERE YEAR(uploaded_at)=%s AND MONTH(uploaded_at)=%s
                GROUP BY scenario_id, sentiment_label
            """
            params2 = [selected_year, selected_month]

        cur.execute(sql2, params2)
        scen_rows = cur.fetchall()

        scen_map = {}
        for sid, label, total in scen_rows:
            sid_str = str(sid if sid is not None else "Unknown")
            if sid_str not in scen_map:
                scen_map[sid_str] = {"complaint": 0, "non": 0}
            norm = _normalize_sentiment(label)
            if norm == "complaint":
                scen_map[sid_str]["complaint"] += int(total)
            elif norm == "non":
                scen_map[sid_str]["non"] += int(total)

        scen_sorted = sorted(
            scen_map.items(),
            key=lambda kv: kv[1]["complaint"] + kv[1]["non"],
            reverse=True
        )[:10]

        scenario_labels = [k for k, _ in scen_sorted]
        scenario_complaint = [v["complaint"] for _, v in scen_sorted]
        scenario_non = [v["non"] for _, v in scen_sorted]

        return {
            "month_labels": month_labels,
            "line_complaint": line_complaint,
            "line_non": line_non,
            "pct_complaint": pct_c,
            "pct_non": pct_n,
            "scenario_labels": scenario_labels,
            "scenario_complaint": scenario_complaint,
            "scenario_non": scenario_non,
            "period": f"{selected_year}-{selected_month:02d}",
            "source_type": st,
            "username": username or "",
        }

    finally:
        cur.close()
        conn.close()
