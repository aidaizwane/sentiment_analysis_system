from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def _normalize_sentiment(label: Any) -> str:
    s = (str(label or "")).strip().lower()
    if "complaint" in s and "non" not in s:
        return "complaint"
    if "non" in s:
        return "non"
    if "positive" in s or "neutral" in s:
        return "non"
    return ""


def _month_series_last_n(n: int = 12) -> List[Tuple[int, int]]:
    now = datetime.now()
    y, m = now.year, now.month
    out = []
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


def build_dashboard_data(
    *,
    rows: List[Dict[str, Any]],
    period: str = "",
    source_type: str = "",
) -> Dict[str, Any]:
    """
    Build dashboard aggregates from a unified rows list.

    Expected row keys (best effort):
      - uploaded_at: datetime or iso string
      - source_type: 'audio'/'text'
      - sentiment_label
      - scenario_id

    NOTE:
      Your current MySQL schema (audio_sessions/text_sessions) does NOT store username,
      so this dashboard is global for all users.
    """
    # Optional filter by month period (YYYY-MM)
    if period:
        try:
            y_sel, m_sel = map(int, period.split("-"))
        except Exception:
            y_sel, m_sel = None, None
    else:
        y_sel, m_sel = None, None

    def _dt(v: Any) -> Optional[datetime]:
        if isinstance(v, datetime):
            return v
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v))
        except Exception:
            return None

    # Filter rows by source_type if requested
    if source_type in ("audio", "text"):
        rows_f = [r for r in rows if (r.get("source_type") == source_type)]
    else:
        rows_f = list(rows)

    # Filter by selected month if provided
    if y_sel and m_sel:
        rows_f = [
            r for r in rows_f
            if (_dt(r.get("uploaded_at")) is not None)
            and (_dt(r.get("uploaded_at")).year == y_sel)
            and (_dt(r.get("uploaded_at")).month == m_sel)
        ]

    months = _month_series_last_n(12)
    c_map = {k: 0 for k in months}
    n_map = {k: 0 for k in months}

    # for chart we always use the last 12 months from all rows (not only filtered month)
    # but still respect source_type.
    rows_chart = [r for r in rows if (source_type not in ("audio", "text") or r.get("source_type") == source_type)]

    for r in rows_chart:
        dt = _dt(r.get("uploaded_at"))
        if not dt:
            continue
        k = (dt.year, dt.month)
        if k not in c_map:
            continue
        s = _normalize_sentiment(r.get("sentiment_label"))
        if s == "complaint":
            c_map[k] += 1
        elif s == "non":
            n_map[k] += 1

    month_labels = [f"{mm:02d}" for (_, mm) in months]
    line_complaint = [c_map[k] for k in months]
    line_non = [n_map[k] for k in months]

    total_c = sum(line_complaint)
    total_n = sum(line_non)
    total_all = total_c + total_n
    pct_c = round((total_c / total_all) * 100) if total_all else 0
    pct_n = round((total_n / total_all) * 100) if total_all else 0

    # Scenario counts (top 10) from filtered set (period filter applies here)
    scen: Dict[str, Dict[str, int]] = {}
    for r in rows_f:
        sid = str(r.get("scenario_id") or "Unknown")
        scen.setdefault(sid, {"complaint": 0, "non": 0})
        s = _normalize_sentiment(r.get("sentiment_label"))
        if s == "complaint":
            scen[sid]["complaint"] += 1
        elif s == "non":
            scen[sid]["non"] += 1

    scen_sorted = sorted(
        scen.items(),
        key=lambda x: x[1]["complaint"] + x[1]["non"],
        reverse=True,
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
        "period": period or "",
        "source_type": source_type or "",
    }
