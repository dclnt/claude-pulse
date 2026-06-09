# Architecture — Composite Latency Report + Outage Integration

Extends the static dashboard (no backend; CI fetch writes data.js; index.html reads PULSE_DATA; file:// safe; mobile-friendly; honesty preserved).

## Data sources (verified)
| Source | Use | Verdict |
|---|---|---|
| LLM Overwatch `fetch.php?response` (browser UA) | rich latency: overview, lastHour, 24h, 7d, 30d, peakHours, 16 models + byHourData | KEEP — only rich free feed (single vantage) |
| Artificial Analysis | one US vantage, 72h median, time-series paywalled | SKIP v1 (fragile scrape, one stale number) |
| GPT for Work | render-only, regions unnamed | UNUSABLE |
| Self-probe (Anthropic API) | your own path; needs key+cost; CI = single US-east | DEFER to optional Phase 4 |
| status.claude.com `summary.json` | official status, components[6], active incidents | ADD |
| status.claude.com `incidents.json` | 50-incident history + impact | ADD |

Honest takeaway: multi-source "aggregation" mostly isn't available. The real wins: (1) a smarter composite from Overwatch's own dimensions, (2) reconciling official outage status vs measured latency.

## PULSE_DATA additions
- `report`: { current_ms (recency-weighted), baseline_ms (allTimeAverage), deviation_pct, verdict (FAST/NORMAL/SLOW/VERY_SLOW), confidence {score, level, sample_count, reason}, inputs{}, model_scope }
- `status`: { official{indicator, description, last_updated, components[6]}, active_incidents[], recent_incidents[] (last ~5, duration_min), reconciliation{state, message, latency_deviation_pct}, fetch_ok }

## Composite latency (the honest "optimization")
A blend of Overwatch's OWN dimensions, not a multi-provider merge:
- current_ms = 0.6·last15MinAverage + 0.3·lastHour.average + 0.1·allTimeAverage; shift weight off last15Min when its dataCount is low.
- baseline = allTimeAverage. peakHours[hour] shown as secondary "typical for this hour", not the baseline.
- deviation_pct = (current − baseline)/baseline·100.
- confidence: from summed dataCount + staleness of lastUpdated. Thin/stale data lowers confidence (shown as a chip), never silently passes.
- If last15Min and lastHour diverge sharply: lower confidence, headline uses the smoothed value, still show the fresh one.

## fetch_overwatch.py changes
1. Keep Overwatch fetch (browser UA).
2. Add `summary.json` + `incidents.json` (plain urllib, no UA), each try/except.
3. Compute `report` (weighted blend + deviation + confidence) server-side for "all" scope.
4. Build `status` (official, active_incidents from summary, recent_incidents trimmed from incidents.json).
5. Compute `reconciliation`: indicator!=none → OFFICIAL_INCIDENT; indicator==none & deviation>~40% → LATENCY_DIVERGENCE; both bad → DEGRADED_BOTH; else ALL_CLEAR.
6. Resilience: status fetch fail → status.official=null, UI falls back to measured (Overwatch) badge, labeled "(measured)". fetch_ok flag. Never break the page.

## UI changes
Feature 1: center verdict reads report.current_ms/verdict; add confidence chip (HIGH/MED/LOW + tooltip reason); deviation line "X ms · N% above/below normal"; optional "typical for this hour"; per-model report recomputed client-side from models[]/byHourData. Keep disclaimer.
Feature 2: badge → official indicator (measured fallback); dismissible incident banner colored by impact (minor amber / major orange / critical red); reconciliation strip ("Operational, but latency 57% above normal" = the money line); collapsible recent-incident history (collapsed on mobile).
States: all-clear · latency-divergence · active-incident{minor|major|critical} · recently-resolved · status-feed-down(fallback).

## Key decisions
F1: (1) no 2nd latency source for v1 (AA fragile, self-probe key+cost). (2) weighted blend + confidence over single freshest value. (3) baseline = all-time, peak-hour as context. (4) per-model report = client recompute (zero new payload).
F2: (1) official badge with measured fallback. (2) use summary.json only for active incidents (skip unresolved.json). (3) reconciliation threshold ~+40%, require persistence to avoid alarm fatigue. (4) ~5 recent incidents, collapsed on mobile.

## Risks
Single-vantage truth (keep disclaimer + confidence) · thin/stale last15Min lying (confidence + staleness) · status JSON drift/outage at the worst moment (try/except + fallback) · false reconciliation alarms (tune threshold + persistence) · mobile clutter (collapse/dismiss) · honesty regression (label "smarter read of one source", never "aggregated across providers").

## Phased build order
1. Outage integration (highest value, lowest risk, no math traps). Ship first.
2. Composite report + confidence.
3. Reconciliation signal (needs 1 + 2).
4. (Optional, opt-in) Self-probe cross-check (API key + cost; label "your own path").

Files that change at build: fetch_overwatch.py (pipeline + report/status), index.html (badge, banner, reconciliation strip, confidence chip, per-model report).
