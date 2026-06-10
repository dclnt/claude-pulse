"""
fetch_aa.py
Fetches Claude Fable 5 latency from the Artificial Analysis Data API (free tier),
and writes data_fable.js (window.FABLE_DATA = {...}) for index.html.

Why this exists: LLM Overwatch (the dashboard's main feed) does not track Fable.
Artificial Analysis does — as a single 72h median per metric, measured ~8x/day
(every ~3h). This is a SLOW, SMOOTH signal, NOT the hourly curve Overwatch gives.
The UI must label it as a 72h median, not "live".

Auth: reads AA_API_KEY from .env (git-ignored) or the environment.
The key is NEVER printed. Keep it server-side only.

Usage:
    python fetch_aa.py            # fetch + write data_fable.js
    python fetch_aa.py --inspect  # also dump the matched model's raw keys (schema discovery)

Free tier: median-only, ~100 requests/day. Docs: https://artificialanalysis.ai/data-api/docs
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
ENV_FILE = SCRIPT_DIR / ".env"
OUT_FILE = SCRIPT_DIR / "data_fable.js"

# Free language-models endpoint (median performance + pricing). Key in x-api-key header.
ENDPOINT = "https://artificialanalysis.ai/api/v2/language/models/free"

# We want the Anthropic Claude Fable model. AA's slug is "claude-fable-5".
MODEL_MATCH = "fable"

# Latency/speed fields documented for AA language models (verified live below).
LATENCY_FIELDS = [
    "median_time_to_first_token_seconds",
    "median_time_to_first_answer_token_seconds",
    "median_output_tokens_per_second",
    "median_end_to_end_response_time_seconds",
]


def load_api_key() -> str:
    """Read AA_API_KEY from .env, falling back to the process environment.
    Returns the key string. Never logs or prints the value."""
    import os

    # .env wins if present (project-local), else environment.
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == "AA_API_KEY":
                return value.strip().strip('"').strip("'")
    return os.environ.get("AA_API_KEY", "").strip()


def _get_page(api_key: str, page: int) -> dict:
    """GET one page of the free language-models endpoint."""
    req = urllib.request.Request(
        f"{ENDPOINT}?page={page}",
        headers={
            "x-api-key": api_key,
            "Accept": "application/json",
            "User-Agent": "claude-pulse/fetch_aa (+static dashboard)",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_models(api_key: str) -> list:
    """Fetch ALL pages of the free endpoint and return a flat list of model dicts.
    The endpoint paginates (page_size 200, ~3 pages); page 1 alone misses most
    models including Fable. Safety-capped at 20 pages."""
    models: list = []
    page = 1
    total_pages = 1
    while page <= total_pages and page <= 20:
        payload = _get_page(api_key, page)
        data = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(data, list):
            models.extend(m for m in data if isinstance(m, dict))
        pg = payload.get("pagination", {}) if isinstance(payload, dict) else {}
        total_pages = pg.get("total_pages", page)
        page += 1
    return models


def model_label(m: dict) -> str:
    """Best-effort human label from common id fields."""
    for k in ("slug", "name", "id", "model_name"):
        v = m.get(k)
        if isinstance(v, str) and v:
            return v
    return "<unknown>"


def find_fable(models: list) -> dict | None:
    """First model whose id/slug/name contains 'fable' (case-insensitive)."""
    for m in models:
        for k in ("slug", "name", "id", "model_name"):
            v = m.get(k)
            if isinstance(v, str) and MODEL_MATCH in v.lower():
                return m
    return None


def find_latency_values(m: dict) -> dict:
    """Pull documented latency fields wherever they live in the model dict.
    AA may nest them (e.g. under 'evaluations' or 'median_...'). We search the
    top level first, then one level of nested dicts. Missing -> None."""
    found = {f: None for f in LATENCY_FIELDS}

    def scan(d: dict):
        for key, val in d.items():
            if key in found and isinstance(val, (int, float)):
                found[key] = val
            elif isinstance(val, dict):
                scan(val)

    scan(m)
    return found


def main():
    inspect = "--inspect" in sys.argv
    fetched_at = datetime.now(timezone.utc).isoformat()

    api_key = load_api_key()
    if not api_key:
        print("FAIL — AA_API_KEY not found in .env or environment.", file=sys.stderr)
        print("       Add a line `AA_API_KEY=your_key` to .env (git-ignored).", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching Artificial Analysis free language-models feed... ({fetched_at})")
    try:
        models = fetch_models(api_key)
    except urllib.error.HTTPError as exc:
        # Surface status without echoing the key. 401/403 = key problem.
        print(f"FAIL — HTTP {exc.code}: {exc.reason}", file=sys.stderr)
        if exc.code in (401, 403):
            print("       Key was rejected. Check the value in .env.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"FAIL — request error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"  models returned: {len(models)} (all pages)")
    if not models:
        print("FAIL — no models in response (all pages empty).", file=sys.stderr)
        sys.exit(2)

    fable = find_fable(models)
    if fable is None:
        sample = ", ".join(model_label(m) for m in models[:8])
        print("FAIL — no model matching 'fable' in the free endpoint.", file=sys.stderr)
        print(f"       Free endpoint may not include newly-added models. Sample ids: {sample}", file=sys.stderr)
        sys.exit(3)

    label = model_label(fable)
    print(f"  matched model:   {label}")

    if inspect:
        print("  --- raw keys on matched model ---")
        for k in sorted(fable.keys()):
            v = fable[k]
            shown = v if isinstance(v, (int, float, str, bool, type(None))) else f"<{type(v).__name__}>"
            print(f"    {k}: {shown}")

    latency = find_latency_values(fable)
    print("  latency (median, 72h window):")
    for k, v in latency.items():
        print(f"    {k}: {v}")

    if all(v is None for v in latency.values()):
        print("WARN — no documented latency fields populated. Run with --inspect to see the real schema.", file=sys.stderr)

    out = {
        "source": "Artificial Analysis",
        "sourceUrl": "https://artificialanalysis.ai/models/claude-fable-5/providers",
        "fetchedAt": fetched_at,
        "model": label,
        "name": fable.get("name"),
        "releaseDate": fable.get("release_date"),
        "window": "72h median (P50)",
        "updateCadence": "~3h (8x/day)",
        "measurement": "single US vantage; median, not hourly. Latency includes reasoning time (Adaptive Reasoning, Max Effort).",
        "latency": latency,
    }
    content = (
        "// Auto-generated by fetch_aa.py — do not edit by hand.\n"
        "// Fable latency from Artificial Analysis (https://artificialanalysis.ai), 72h median.\n"
        "window.FABLE_DATA = " + json.dumps(out, indent=2) + ";\n"
    )
    OUT_FILE.write_text(content, encoding="utf-8")
    print(f"OK — wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
