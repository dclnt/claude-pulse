# Claude Pulse

**A tiny, honest dashboard for how *fast* Claude's API is responding right now — plus official outage status.**

🔗 **Live:** https://dclnt.github.io/claude-pulse/

> **What is this, in two sentences?**
> Claude Pulse is a single static web page that shows a live "how slow/fast is Claude right now" dial, the official Anthropic service status, and a separate latency card for **Claude Fable 5**. It has **no backend** — data is fetched on a schedule by two small Python scripts and baked into the page.

> ⚠️ **Unofficial.** This is an independent project. It is **not** affiliated with, endorsed by, or operated by Anthropic. All numbers come from third-party measurement feeds (see [Where the data comes from](#-where-the-data-comes-from)).

---

## Contents

- [⚡ What you see](#-what-you-see)
- [🧭 Honest by design](#-honest-by-design)
- [📡 Where the data comes from](#-where-the-data-comes-from)
- [🏗️ How it works](#️-how-it-works)
- [🚀 Run it yourself](#-run-it-yourself)
- [🗂️ Project layout](#️-project-layout)
- [⚠️ Limits (read these)](#️-limits-read-these)
- [🙏 Credit](#-credit)
- [📄 License](#-license)

---

## ⚡ What you see

**One screen, four readouts:**

- **🕐 The dial** — a 24-hour clock where each arc is one hour. Brighter = faster, amber = unusually slow. A hand sweeps in real time.
- **📊 The center number** — a single "right now" latency, blended from recent + all-time data, with a **HIGH / MED / LOW confidence** chip so you know how much to trust it.
- **🟢 Status pill + incident banner** — pulled from Anthropic's official status page. Tells you if there's a real outage, and reconciles it against measured latency (e.g. *"Operational, but latency 57% above normal"*).
- **⭐ Claude Fable 5 card** — Fable's latency from a different source (it isn't on the main feed yet), clearly labelled as a slow-moving 72-hour median.

---

## 🧭 Honest by design

This project's whole point is to **not lie to you.** The rules it follows:

> **It measures time, not quality.** A fast response can still be wrong; a slow one can still be right. This tracks **milliseconds**, nothing else.

> **It's not measuring *your* connection.** The numbers come from a measurement service's servers to Anthropic's API — not from your machine.

> **It shows its uncertainty.** Thin or stale data drops the confidence chip to MED/LOW. Old data greys out behind a "stale" ribbon. Missing data shows a **SAMPLE** banner instead of faking it.

> **It never invents numbers.** If a feed doesn't track something, the dashboard says so or hides the element. No made-up data, ever.

---

## 📡 Where the data comes from

| Source | What it powers | Refresh | Key needed? |
|---|---|---|---|
| **[LLM Overwatch](https://llmoverwatch.com)** | The hourly dial, 24h/7d strips, the center number + confidence | ~every few minutes | No |
| **[status.claude.com](https://status.claude.com)** | Status pill, incident banner, reconciliation strip | with each refresh | No |
| **[Artificial Analysis](https://artificialanalysis.ai)** | The Claude Fable 5 latency card (72h median) | ~every 3 hours | Yes (free) |

---

## 🏗️ How it works

**No server, no database, no framework.** The flow is dead simple:

1. **GitHub Actions runs two Python scripts** on a schedule.
2. Each script fetches a feed and writes a small JS file (`data.js`, `data_fable.js`) that just sets a global variable.
3. **`index.html` reads those globals and draws everything** in the browser.
4. The page is published to **GitHub Pages**.

```
 feeds ──> fetch_overwatch.py ──> data.js ─────┐
                                                ├──> index.html ──> GitHub Pages
 AA  ────> fetch_aa.py ────────> data_fable.js ─┘
```

**Quota-aware:** Artificial Analysis' free tier allows ~100 requests/day, so `fetch_aa.py` only runs **once per 3-hour window** (cached between deploys) while the keyless Overwatch feed refreshes far more often.

---

## 🚀 Run it yourself

### 1. Just look at it (zero setup)

It's a static page. Serve the folder and open it:

```bash
python -m http.server 7823
# then open http://localhost:7823
```

> No data files yet? The page automatically shows **SAMPLE DATA** so you can see the layout.

### 2. Pull real data locally

```bash
# Overwatch + official status — no key needed:
python fetch_overwatch.py

# Claude Fable 5 latency — needs a free Artificial Analysis key:
echo "AA_API_KEY=your_key_here" > .env
python fetch_aa.py
```

> 🔑 Get a free key at [Artificial Analysis → Data API](https://artificialanalysis.ai/data-api). Keep it in `.env` (already git-ignored). **Never** commit it or put it in the HTML.

### 3. Deploy your own copy

1. **Fork** this repo.
2. Enable **GitHub Pages** → *Build and deployment* → **GitHub Actions**.
3. *(Optional, for the Fable card)* add a repo secret named **`AA_API_KEY`**.
4. Push. The workflow fetches data and publishes the site automatically.

---

## 🗂️ Project layout

| File | Job |
|---|---|
| `index.html` | The entire dashboard — UI + drawing logic |
| `fetch_overwatch.py` | Fetches LLM Overwatch + official status → writes `data.js` |
| `fetch_aa.py` | Fetches Claude Fable 5 latency from Artificial Analysis → writes `data_fable.js` |
| `data.sample.js` | Synthetic fallback shown when no real data is present |
| `.github/workflows/deploy.yml` | Scheduled fetch + GitHub Pages deploy |
| `ARCHITECTURE.md` | Deeper design notes and decisions |

> `data.js` and `data_fable.js` are **generated**, not committed (git-ignored). They're created fresh by the fetchers / CI.

---

## ⚠️ Limits (read these)

- **Single vantage point.** Latency is measured from one external location, not globally and not from you.
- **Time ≠ quality.** This says nothing about whether Claude's answers are good.
- **The Fable card is a 72-hour median** for a max-effort reasoning configuration, so its numbers include "thinking" time and are **much higher** than the dial's near-real-time response times. That's expected — it's a different measurement, shown separately on purpose.
- **The dial only shows models its feed tracks.** If LLM Overwatch hasn't added a model yet, it won't appear on the dial.

---

## 🙏 Credit

Latency and status data is measured and published by these independent services — this project only visualizes them:

- **[LLM Overwatch](https://llmoverwatch.com)** — primary latency feed
- **[Artificial Analysis](https://artificialanalysis.ai)** — Claude Fable 5 latency
- **[Anthropic Status](https://status.claude.com)** — official service status

"Claude" and "Anthropic" are trademarks of Anthropic. This project is not affiliated with them.

---

## 📄 License

No license file has been added yet. Until one exists, default copyright applies — open an issue if you'd like to reuse this.
