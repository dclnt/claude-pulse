# Claude Performance Pulse-Clock — Build Plan (v3, pivoted to LLM Overwatch)

Pivoted 2026-06-08: data engine replaced from self-probe via Anthropic API
to LLM Overwatch's free public JSON feed. No API key, no cost.

## Goal
Show **when Claude is actually fastest** using LLM Overwatch's continuous
probe data, plus a live status layer. Keep the luminous radial dial; swap
the data source and evidence layer.

## Honest framing (locked)
- Data is **measured by LLM Overwatch's servers**, not this machine. Labels
  say "faster / slower," never "better." Attribution is visible on every load.
- No answer-quality claims. Response time only.

## Data source (pivoted)
- **LLM Overwatch public feed:** `GET https://llmoverwatch.com/api/fetch.php?response`
  Free, no auth, JSON, no CORS header (fetch server-side only).
- Requires browser-like User-Agent + Referer header or returns 403.
- Updates ~every 5-10 minutes. We fetch every 30 minutes via scheduled task.
- `providers.anthropic.response` contains: `overview`, `peakHours` (24 hourly avgs,
  UTC hour index), `twentyFourHours` (rolling 24h trend), `sevenDays` (7 daily avgs),
  `models` (16 models with per-hour data), `incidents`, `reliability`.
- Values are response time in **milliseconds** (e.g. 26202 ms = 26.2 s).
- `peakHours.data[h].hour` is **UTC** hour-of-day (confirmed by cross-checking
  fetch timestamp at 14:30 UTC against peak flags at hours 8-10, 13, 15).

## Form (locked: luminous radial pulse-clock)
- **Hero:** dark 24h radial dial. Arcs = `peakHours.data[24]` by UTC hour.
  Brightness = faster (lower ms). Sweeping now-hand tracks current UTC hour.
  Center = live verdict from `overview`: last-15min avg + % diff vs all-time.
- **Evidence layer:** 24-hour trend strip + 7-day strip (luminance scale, ms labels).
  Compact per-model chip list below.
- **Status badge:** from `anthropic.status` + `overview.lastUpdated`.
- **Attribution:** "Data: LLM Overwatch" in subtitle + "Measured by LLM Overwatch"
  footer, both linking https://llmoverwatch.com.

## Color (locked)
- Arcs + strips: **luminance ramp** (dim = slow, bright = fast), tied to real ms
  min/max from the feed. Legend = horizontal gradient bar with ms ticks.
- Center verdict: relative ("58% slower than usual").

## Animations (locked)
1. Sweeping now-hand at current UTC time.
2. Verdict count-up + glow pulse on render.
3. Current-hour arc ring highlight.

## Architecture
```
fetch_overwatch.py  --scheduled task, every 30 min-->
   GET llmoverwatch.com/api/fetch.php?response (browser UA required)
   extract providers.anthropic + metadata
   emit data.js  (window.PULSE_DATA = {...})
                          |
index.html  <-- <script src="data.js">  (file:// safe, no fetch())
   renders radial dial + 24h strip + 7-day strip + model chips
   from PULSE_DATA
```
- No API key anywhere. No measurements.jsonl. No data/ directory.
- On fetch failure: keeps last good data.js intact; writes error marker only
  if no prior file exists.

## Data model (PULSE_DATA shape)
```
{
  source, sourceUrl, fetchedAt, feedGeneratedAt, sourceTz="UTC",
  verdict: { status, last15MinAverage_ms, allTimeAverage_ms,
             performanceDiff_ms, lastUpdated },
  hourly: [24 x { hour, average_ms, dataCount, isPeak }],   // UTC hour-of-day
  trend24h: [24 x { hour, average_ms, dataCount, dataType }],
  trend24hAverage_ms,
  week: [7 x { dayIndex, average_ms, byHourData[24] }],     // 0=today
  weekAverage_ms,
  models: [16 x { name, status, metrics, byHourData[24] }],
  incidents: { summary: {...} }
}
```

## Key correctness fixes (carried from eng review)
- **file:// fix:** inline `data.js` via script tag, not `fetch()` of local JSON. (CRITICAL)
- **No CORS on the feed:** the page can't fetch llmoverwatch.com directly, so the local
  fetch step (`fetch_overwatch.py`) pulls it server-side and writes `data.js`.
- **Feed needs a browser-like User-Agent + Referer** or it 403s. Handled in the fetcher.
- **Timezone:** feed hours are UTC; `index.html` converts to the viewer's local zone at
  render time (follows DST via the device offset). Dial, now-hand, strips, status time all local.
- **Graceful failure:** on fetch error, keep the last good `data.js`; badge shows grey
  "unknown," never default green.

## States (specified)
- **Cold-start / no data.js:** verdict shows "Could not load data.js"; run a fetch.
- **Loading:** dial chrome draws first, arcs fill from `data.js`.
- **Stale:** ribbon keyed off the feed's `lastUpdated` ("feed last updated Nh ago").
- **Status unknown:** grey badge when the feed is missing the status field.

## Honesty UI
- Footer: "Measured by LLM Overwatch · response time, not answer quality · updated ~every 10 min."
- Subtitle + footer both credit and link https://llmoverwatch.com.
- `ⓘ How this works` panel: data source, what's measured (their servers, not your machine),
  dial meaning, timezone conversion, status badge, limitations.

## Out of scope (v1)
Per-machine probing, model-quality claims, public hosting, a true 7x24 grid
(feed only exposes 24 hour-of-day + 7 day-of-week separately, not the cross-product).

## Success criteria (met)
- `fetch_overwatch.py` pulls the real feed and writes `data.js`. No API key, no cost.
- Dial + 24h strip + 7-day strip + model chips render from real data via `data.js` (file:// safe).
- Hours shown in the viewer's local timezone; status/stale states present.
- Clearly better than the old donut: luminous dark dial, sweeping hand, glow-on-update.

## Defaults (stated)
- Refresh: **every 30 min** via `setup-task.ps1` (feed updates ~every 5-10 min), or
  `refresh.bat` on demand. Stack: **single HTML + one Python fetch script**, no key, no cost.
