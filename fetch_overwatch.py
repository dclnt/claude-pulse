"""
fetch_overwatch.py
Fetches Anthropic performance data from LLM Overwatch's public JSON feed.
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
    """GET the endpoint. Returns parsed JSON or raises on failure."""
    req = urllib.request.Request(ENDPOINT, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_pulse_data(raw: dict, fetched_at: str) -> dict:
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

    # -- Incidents summary --
    incidents = ant.get("incidents", {})

    return {
        "source": "LLM Overwatch",
        "sourceUrl": "https://llmoverwatch.com",
        "fetchedAt": fetched_at,
        "feedGeneratedAt": meta.get("generated"),
        "sourceTz": "UTC",
        "hourlyDialNote": "peakHours hours 0-23 are UTC hour-of-day",
        "verdict": verdict,
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

    # Confirm key fields are present before proceeding
    try:
        pulse_data = build_pulse_data(raw, fetched_at)
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

    print(f"OK")
    print(f"  status:          {v['status']}")
    print(f"  last 15min avg:  {last15_s}  ({last15} ms)")
    print(f"  all-time avg:    {all_time_s}  ({all_time} ms)")
    print(f"  diff:            {diff_s}")
    print(f"  hourly entries:  {len(pulse_data['hourly'])}")
    print(f"  models:          {len(pulse_data['models'])}")
    print(f"  feed generated:  {pulse_data['feedGeneratedAt']}")
    print(f"data.js written to {DATA_JS_FILE}")


if __name__ == "__main__":
    main()
