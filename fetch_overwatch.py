"""
fetch_overwatch.py
Fetches Anthropic performance data from LLM Overwatch's public JSON feed,
plus official status from status.claude.com.
Writes data.js (window.PULSE_DATA = {...}) for index.html.

No API key required. No cost. Data is measured by LLM Overwatch's servers.

Usage:
    python fetch_overwatch.py          # fetch + write data.js
    python fetch_overwatch.py --once   # same (explicit; default behavior)

On fetch failure, keeps any existing data.js and writes status=unknown marker.
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_JS_FILE = SCRIPT_DIR / "data.js"

ENDPOINT = "https://llmoverwatch.com/api/fetch.php?response"
STATUS_SUMMARY_URL = "https://status.claude.com/api/v2/summary.json"
STATUS_INCIDENTS_URL = "https://status.claude.com/api/v2/incidents.json"

# Required to avoid 403. The API blocks plain Python user-agents.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
    "Referer": "https://llmoverwatch.com/",
}


def fetch_raw() -> dict:
    """GET the Overwatch endpoint. Returns parsed JSON or raises on failure."""
    req = urllib.request.Request(ENDPOINT, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_status_json() -> tuple[dict | None, dict | None]:
    """
    Fetch summary.json and incidents.json from status.claude.com.
    Returns (summary, incidents) — either may be None on failure.
    Each fetch is wrapped in its own try/except so one failure doesn't kill the other.
    """
    summary = None
    incidents = None

    try:
        with urllib.request.urlopen(STATUS_SUMMARY_URL, timeout=15) as resp:
            summary = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"WARN — status summary fetch failed: {exc}", file=sys.stderr)

    try:
        with urllib.request.urlopen(STATUS_INCIDENTS_URL, timeout=15) as resp:
            incidents = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"WARN — status incidents fetch failed: {exc}", file=sys.stderr)

    return summary, incidents


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 string to a UTC-aware datetime, or return None."""
    if not ts:
        return None
    try:
        # Python 3.7+ fromisoformat doesn't handle trailing Z
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _duration_min(started: str | None, resolved: str | None) -> int | None:
    """Return duration in whole minutes between two ISO timestamps, or None."""
    s = _parse_iso(started)
    r = _parse_iso(resolved)
    if s and r:
        return max(0, int((r - s).total_seconds() / 60))
    return None


def build_report(overview: dict, last_hour_avg: float | None, current_utc_hour: int, peak_hours: list) -> dict:
    """
    Compute the composite latency report for the 'all' scope.

    Blend weights: 0.6 last15Min + 0.3 lastHour + 0.1 allTime.
    When last15Min dataCount is low (<10), shift its 0.6 weight into lastHour.
    """
    last15    = overview.get("last15MinAverage")
    all_time  = overview.get("allTimeAverage")
    last15_count = overview.get("dataCount", 0) or 0
    last_updated_str = overview.get("lastUpdated")

    # Staleness: if lastUpdated is more than 20 minutes old, confidence drops
    now_utc = datetime.now(timezone.utc)
    stale = False
    last_updated_dt = _parse_iso(last_updated_str)
    if last_updated_dt:
        age_min = (now_utc - last_updated_dt).total_seconds() / 60
        stale = age_min > 20

    # Decide weight split
    thin_last15 = last15_count < 10
    if thin_last15:
        w15, wh, wa = 0.0, 0.9, 0.1
    else:
        w15, wh, wa = 0.6, 0.3, 0.1

    # Gather available values
    components = []
    if last15 is not None and not thin_last15:
        components.append(("last15Min", last15, w15))
    if last_hour_avg is not None:
        components.append(("lastHour", last_hour_avg, wh if thin_last15 else wh))
    if all_time is not None:
        components.append(("allTime", all_time, wa))

    if not components or all_time is None:
        return {
            "model_scope": "all",
            "current_ms": None,
            "baseline_ms": round(all_time) if all_time else None,
            "deviation_pct": None,
            "verdict": "UNKNOWN",
            "confidence": {"score": 0.0, "level": "LOW", "sample_count": 0, "reason": "Insufficient data"},
            "inputs": {
                "last15MinAverage": last15,
                "lastHourAverage": last_hour_avg,
                "peakHourExpected": None,
                "allTimeAverage": all_time,
            },
        }

    # Renormalize weights to sum to 1 with available components
    total_w = sum(c[2] for c in components)
    current_ms = sum(val * w / total_w for _, val, w in components)
    current_ms = round(current_ms)
    baseline_ms = round(all_time)

    deviation_pct = round((current_ms - baseline_ms) / baseline_ms * 100, 1) if baseline_ms else None

    # Verdict thresholds (deviation from baseline)
    if deviation_pct is None:
        verdict = "UNKNOWN"
    elif deviation_pct <= -10:
        verdict = "FAST"
    elif deviation_pct <= 15:
        verdict = "NORMAL"
    elif deviation_pct <= 50:
        verdict = "SLOW"
    else:
        verdict = "VERY_SLOW"

    # Confidence
    sample_count = last15_count
    score = 1.0
    reasons = []
    if thin_last15:
        score -= 0.35
        reasons.append("few last-15min samples")
    if stale:
        score -= 0.3
        reasons.append("data >20min old")
    if last_hour_avg is None:
        score -= 0.15
        reasons.append("no lastHour data")
    score = max(0.0, round(score, 2))
    if score >= 0.7:
        level = "HIGH"
    elif score >= 0.4:
        level = "MED"
    else:
        level = "LOW"
    reason = "; ".join(reasons) if reasons else "good sample coverage"

    # Peak hour context
    peak_entry = next((p for p in peak_hours if p.get("hour") == current_utc_hour), None)
    peak_hour_expected = round(peak_entry["average"]) if peak_entry and peak_entry.get("average") else None

    return {
        "model_scope": "all",
        "current_ms": current_ms,
        "baseline_ms": baseline_ms,
        "deviation_pct": deviation_pct,
        "verdict": verdict,
        "confidence": {
            "score": score,
            "level": level,
            "sample_count": sample_count,
            "reason": reason,
        },
        "inputs": {
            "last15MinAverage": last15,
            "lastHourAverage": last_hour_avg,
            "peakHourExpected": peak_hour_expected,
            "allTimeAverage": all_time,
        },
    }


def build_status(summary: dict | None, incidents_data: dict | None, deviation_pct: float | None) -> dict:
    """
    Build the status block from official status.claude.com data.
    Falls back gracefully when either feed is unavailable.
    """
    fetch_ok = summary is not None

    official = None
    active_incidents = []
    recent_incidents = []
    reconciliation = {"state": "ALL_CLEAR", "message": "Operational · latency normal", "latency_deviation_pct": deviation_pct}

    if summary:
        st = summary.get("status", {})
        indicator = st.get("indicator", "none")
        description = st.get("description", "")

        components_raw = summary.get("components", [])
        components = [
            {"name": c.get("name"), "status": c.get("status")}
            for c in components_raw
        ]

        # last_updated from the page_metadata or components updated_at
        last_updated = summary.get("page", {}).get("updated_at")

        official = {
            "indicator": indicator,
            "description": description,
            "last_updated": last_updated,
            "components": components,
        }

        # Active incidents from summary (these are unresolved)
        for inc in summary.get("incidents", []):
            if inc.get("status") not in ("resolved", "postmortem"):
                active_incidents.append({
                    "id": inc.get("id"),
                    "name": inc.get("name"),
                    "status": inc.get("status"),
                    "impact": inc.get("impact", "none"),
                    "started_at": inc.get("started_at") or inc.get("created_at"),
                    "url": "https://status.claude.com",
                })

        # Reconciliation
        has_incident = indicator != "none" or len(active_incidents) > 0
        has_latency_divergence = deviation_pct is not None and deviation_pct > 40

        if has_incident and has_latency_divergence:
            reconciliation = {
                "state": "DEGRADED_BOTH",
                "message": f"Incident reported · latency {abs(round(deviation_pct))}% above normal",
                "latency_deviation_pct": deviation_pct,
            }
        elif has_incident:
            reconciliation = {
                "state": "OFFICIAL_INCIDENT",
                "message": description or "Incident reported on status.claude.com",
                "latency_deviation_pct": deviation_pct,
            }
        elif has_latency_divergence:
            reconciliation = {
                "state": "LATENCY_DIVERGENCE",
                "message": f"Operational, but latency is {abs(round(deviation_pct))}% above normal",
                "latency_deviation_pct": deviation_pct,
            }
        else:
            reconciliation = {
                "state": "ALL_CLEAR",
                "message": "Operational · latency normal",
                "latency_deviation_pct": deviation_pct,
            }

    # Recent resolved incidents from incidents.json (last ~5 resolved)
    if incidents_data:
        all_incidents = incidents_data.get("incidents", [])
        resolved = [
            i for i in all_incidents
            if i.get("status") in ("resolved", "postmortem") and i.get("resolved_at")
        ]
        # Sort newest-resolved first
        resolved.sort(key=lambda i: i.get("resolved_at", ""), reverse=True)
        now_utc = datetime.now(timezone.utc)
        for inc in resolved[:5]:
            resolved_dt = _parse_iso(inc.get("resolved_at"))
            hours_ago = None
            if resolved_dt:
                hours_ago = round((now_utc - resolved_dt).total_seconds() / 3600, 1)
            recent_incidents.append({
                "id": inc.get("id"),
                "name": inc.get("name"),
                "impact": inc.get("impact", "none"),
                "started_at": inc.get("started_at") or inc.get("created_at"),
                "resolved_at": inc.get("resolved_at"),
                "duration_min": _duration_min(
                    inc.get("started_at") or inc.get("created_at"),
                    inc.get("resolved_at")
                ),
                "hours_ago": hours_ago,
            })

    return {
        "official": official,
        "active_incidents": active_incidents,
        "recent_incidents": recent_incidents,
        "reconciliation": reconciliation,
        "fetch_ok": fetch_ok,
    }


def build_pulse_data(raw: dict, fetched_at: str, summary: dict | None = None, incidents_data: dict | None = None) -> dict:
    """
    Extract providers.anthropic from the raw feed and build PULSE_DATA.

    peakHours timezone: the feed is generated at a UTC timestamp and the
    hour objects carry explicit integer keys 0-23. Cross-checking the fetch
    time (14:30 UTC) against the isPeak flags (8,9,10,13,15,23 marked peak)
    is consistent with UTC business-hour traffic. We label hours as UTC.
    """
    ant = raw["providers"]["anthropic"]
    resp = ant["response"]
    meta = raw["metadata"]

    overview = resp["overview"]
    peak_hours = resp["peakHours"]["data"]   # list of 24 {hour,isPeak,average,dataCount}
    t24 = resp["twentyFourHours"]            # {data:[24 {hour,average,...}], average}
    s7 = resp["sevenDays"]                   # {days:[7 {byHourData,average}], average}
    models_raw = resp["models"]              # list of 16 model objects

    # -- peakHours: 24 hourly averages, indexed by hour-of-day (UTC) --
    hourly = [
        {
            "hour": entry["hour"],
            "average_ms": round(entry["average"]) if entry["average"] else None,
            "dataCount": entry["dataCount"],
            "isPeak": entry.get("isPeak", False),
        }
        for entry in sorted(peak_hours, key=lambda e: e["hour"])
    ]

    # -- 24-hour trend (most recent 24h, hour 0 = oldest, 23 = most recent) --
    trend24h = [
        {
            "hour": entry["hour"],
            "average_ms": round(entry["average"]) if entry.get("average") else None,
            "dataCount": entry.get("dataCount", 0),
            "dataType": entry.get("dataType", ""),
        }
        for entry in t24["data"]
    ]

    # -- 7-day strip (day 0 = today/partial, day 6 = 6 days ago) --
    week = [
        {
            "dayIndex": i,           # 0 = today, 1 = yesterday, ...
            "average_ms": round(day["average"]) if day.get("average") else None,
            "byHourData": [
                {
                    "hour": h["hour"],
                    "average_ms": round(h["average"]) if h.get("average") else None,
                    "dataCount": h.get("dataCount", 0),
                    "dataType": h.get("dataType", ""),
                }
                for h in day.get("byHourData", [])
            ],
        }
        for i, day in enumerate(s7["days"])
    ]

    # -- Models: name + status + byHourData --
    models = [
        {
            "name": m["name"],
            "status": m.get("status", "unknown"),
            "metrics": m.get("metrics", {}),
            "byHourData": [
                {
                    "hour": h["hour"],
                    "average_ms": round(h["average"]) if h.get("average") else None,
                    "dataCount": h.get("dataCount", 0),
                }
                for h in m.get("byHourData", [])
            ],
        }
        for m in models_raw
    ]

    # -- Verdict from overview --
    last15 = overview.get("last15MinAverage")
    all_time = overview.get("allTimeAverage")
    diff = overview.get("performanceDiff")

    verdict = {
        "status": ant.get("status", "unknown"),
        "last15MinAverage_ms": round(last15) if last15 is not None else None,
        "allTimeAverage_ms": round(all_time) if all_time is not None else None,
        "performanceDiff_ms": round(diff) if diff is not None else None,
        "lastUpdated": overview.get("lastUpdated"),
    }

    # -- Incidents summary (Overwatch's own) --
    incidents = ant.get("incidents", {})

    # -- Composite report --
    last_hour_avg = t24.get("average") or None
    current_utc_hour = datetime.now(timezone.utc).hour
    report = build_report(overview, last_hour_avg, current_utc_hour, peak_hours)

    # -- Official status block --
    status = build_status(summary, incidents_data, report.get("deviation_pct"))

    return {
        "source": "LLM Overwatch",
        "sourceUrl": "https://llmoverwatch.com",
        "fetchedAt": fetched_at,
        "feedGeneratedAt": meta.get("generated"),
        "sourceTz": "UTC",
        "hourlyDialNote": "peakHours hours 0-23 are UTC hour-of-day",
        "verdict": verdict,
        "report": report,
        "status": status,
        "hourly": hourly,
        "trend24h": trend24h,
        "trend24hAverage_ms": round(t24["average"]) if t24.get("average") else None,
        "week": week,
        "weekAverage_ms": round(s7["average"]) if s7.get("average") else None,
        "models": models,
        "incidents": incidents,
    }


def load_existing_data_js() -> str | None:
    """Return the current data.js content, or None if it does not exist."""
    if DATA_JS_FILE.exists():
        return DATA_JS_FILE.read_text(encoding="utf-8")
    return None


def write_data_js(pulse_data: dict):
    content = (
        "// Auto-generated by fetch_overwatch.py — do not edit by hand.\n"
        "// Data measured by LLM Overwatch (https://llmoverwatch.com), not from this machine.\n"
        "window.PULSE_DATA = "
        + json.dumps(pulse_data, indent=2)
        + ";\n"
    )
    DATA_JS_FILE.write_text(content, encoding="utf-8")


def write_unknown_marker(fetched_at: str, error_msg: str):
    """
    Overwrite only the status/fetchedAt fields in PULSE_DATA to signal
    a fetch failure, while keeping last-good data intact if present.
    Falls back to writing a minimal error-only PULSE_DATA.
    """
    existing = load_existing_data_js()
    if existing:
        # Keep the file but we cannot safely patch JSON in a regex-free way,
        # so we'll prepend a comment and leave the existing data intact.
        # The UI checks fetchedAt age to detect staleness.
        print(
            f"FAIL — keeping last good data.js. Error: {error_msg}",
            file=sys.stderr,
        )
        # No write needed; existing data.js survives.
        return

    # No existing file: write a minimal error payload so the UI shows unknown.
    minimal = {
        "source": "LLM Overwatch",
        "sourceUrl": "https://llmoverwatch.com",
        "fetchedAt": fetched_at,
        "feedGeneratedAt": None,
        "sourceTz": "UTC",
        "hourlyDialNote": "peakHours hours 0-23 are UTC hour-of-day",
        "verdict": {
            "status": "unknown",
            "last15MinAverage_ms": None,
            "allTimeAverage_ms": None,
            "performanceDiff_ms": None,
            "lastUpdated": None,
        },
        "report": None,
        "status": {
            "official": None,
            "active_incidents": [],
            "recent_incidents": [],
            "reconciliation": {"state": "ALL_CLEAR", "message": "Status unavailable", "latency_deviation_pct": None},
            "fetch_ok": False,
        },
        "hourly": [],
        "trend24h": [],
        "trend24hAverage_ms": None,
        "week": [],
        "weekAverage_ms": None,
        "models": [],
        "incidents": {},
        "_fetchError": error_msg,
    }
    write_data_js(minimal)
    print(f"FAIL — wrote error-state data.js. Error: {error_msg}", file=sys.stderr)


def main():
    fetched_at = datetime.now(timezone.utc).isoformat()
    print(f"Fetching LLM Overwatch feed... ({fetched_at})")

    try:
        raw = fetch_raw()
    except urllib.error.HTTPError as exc:
        write_unknown_marker(fetched_at, f"HTTP {exc.code}: {exc.reason}")
        sys.exit(1)
    except Exception as exc:
        write_unknown_marker(fetched_at, str(exc))
        sys.exit(1)

    # Fetch official status feeds (failures are non-fatal — each is wrapped)
    print("Fetching status.claude.com feeds...")
    summary, incidents_data = fetch_status_json()

    # Confirm key fields are present before proceeding
    try:
        pulse_data = build_pulse_data(raw, fetched_at, summary, incidents_data)
    except (KeyError, TypeError) as exc:
        write_unknown_marker(fetched_at, f"Parse error: {exc}")
        sys.exit(1)

    write_data_js(pulse_data)

    v = pulse_data["verdict"]
    last15 = v["last15MinAverage_ms"]
    all_time = v["allTimeAverage_ms"]
    diff = v["performanceDiff_ms"]
    last15_s = f"{last15/1000:.1f}s" if last15 is not None else "n/a"
    all_time_s = f"{all_time/1000:.1f}s" if all_time is not None else "n/a"
    diff_s = f"{diff/1000:+.1f}s vs all-time avg" if diff is not None else ""

    r = pulse_data.get("report") or {}
    s = pulse_data.get("status") or {}
    recon = s.get("reconciliation") or {}

    print(f"OK")
    print(f"  status:          {v['status']}")
    print(f"  last 15min avg:  {last15_s}  ({last15} ms)")
    print(f"  all-time avg:    {all_time_s}  ({all_time} ms)")
    print(f"  diff:            {diff_s}")
    print(f"  composite:       {r.get('current_ms')} ms  verdict={r.get('verdict')}  confidence={r.get('confidence', {}).get('level')}")
    print(f"  reconciliation:  {recon.get('state')} — {recon.get('message')}")
    print(f"  status fetch ok: {s.get('fetch_ok')}  active incidents: {len(s.get('active_incidents', []))}")
    print(f"  hourly entries:  {len(pulse_data['hourly'])}")
    print(f"  models:          {len(pulse_data['models'])}")
    print(f"  feed generated:  {pulse_data['feedGeneratedAt']}")
    print(f"data.js written to {DATA_JS_FILE}")


if __name__ == "__main__":
    main()
