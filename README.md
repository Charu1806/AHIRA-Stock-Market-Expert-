# 🤖 ARIA — Autonomous Research & Investment Agent

ARIA is an AI-powered stock intelligence system that ingests live financial news from 8+ RSS sources, analyses them with Groq (LLaMA 3.3) or Gemini, and delivers structured signals, watchlists, and daily market education — via a Streamlit dashboard, a self-contained HTML file, and Telegram alerts.

---

## Architecture

```
RSS Feeds (Reuters · Bloomberg · CNBC · WSJ · ET · Moneycontrol · Mint · FT)
        │
        ▼
  NewsFetcher ──── 15-min JSON cache ────────────────────────────────────────┐
        │                                                                     │
  PriceFetcher ─── 30-min parquet cache (yfinance)                          │
        │                                                                     │
        ▼                                                                     │
  ┌─────────────────────────────────────────────────────┐                    │
  │                    AIEngine                         │                    │
  │   callARIA(prompt)                                  │                    │
  │        │                                            │                    │
  │   ┌────▼────┐    429 / fail    ┌──────────────┐     │                    │
  │   │  Groq   │ ─────────────▶  │    Gemini    │     │                    │
  │   │llama-3.3│                 │gemini-1.5-fl │     │                    │
  │   └─────────┘                 └──────────────┘     │                    │
  └─────────────────────────────────────────────────────┘                    │
        │                                                                     │
        ├── NewsAgent   (US · Global · India stories + stock impact)         │
        ├── StockAgent  (US + India watchlists, technical indicators)        │
        ├── LearningAgent (daily concept, signal history, accuracy)          │
        └── SignalAgent   (blends sentiment + technicals → recommendation)   │
                                                                             │
        ▼                                               ◀────────────────────┘
  ┌──────────────────────────────────────────────────────┐
  │  Outputs                                             │
  │  • Streamlit dashboard  (6 tabs, dark/light theme)  │
  │  • aria_dashboard.html  (zero-server, Netlify-ready) │
  │  • Telegram Bot         (morning digest + alerts)    │
  └──────────────────────────────────────────────────────┘
        │
  Scheduler (schedule library — weekdays 08:45 IST + 19:00 IST)
```

---

## Quick Start

**1 · Clone**
```bash
git clone https://github.com/yourname/aria-stock-agent
cd aria-stock-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**2 · Configure**
```bash
cp .env.example .env
# Fill in your API keys (see "Get Free API Keys" below)
```

**3 · Verify config**
```bash
python config.py          # shows which keys are loaded / missing
python main.py --test     # sends test message to Telegram
```

**4 · Run a single analysis**
```bash
python main.py --tab us-news          # US market stories
python main.py --tab us-stocks        # AI watchlist
python main.py --now --notify         # full morning run + Telegram digest
```

**5 · Launch dashboard**
```bash
streamlit run dashboard/app.py
# Open http://localhost:8501
```

---

## Get Free API Keys

| Service | Where | Free limit |
|---------|-------|-----------|
| **Groq** (primary LLM) | [console.groq.com/keys](https://console.groq.com/keys) | 14,400 req/day |
| **Gemini** (fallback LLM) | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) | 1,500 req/day |
| **Telegram Bot** | Message [@BotFather](https://t.me/BotFather) → `/newbot` | Free |
| **Telegram Chat ID** | Message [@userinfobot](https://t.me/userinfobot) | Free |

Add to your `.env`:
```
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
TELEGRAM_BOT_TOKEN=123456:AAF...
TELEGRAM_CHAT_ID=987654321
```

---

## Deploy to Railway (3 steps)

Railway gives you a persistent server that runs ARIA 24/7 including the scheduler.

**Step 1 — Push to GitHub**
```bash
git init && git add . && git commit -m "ARIA initial"
git remote add origin https://github.com/yourname/aria-stock-agent
git push -u origin main
```

**Step 2 — Connect Railway**
1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Select your repo → Railway detects the `Dockerfile` automatically

**Step 3 — Add environment variables**
In Railway dashboard → Variables, add:
```
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Railway auto-deploys on every push to `main`.  
For CI/CD via GitHub Actions, add `RAILWAY_TOKEN` to your repo secrets.

---

## HTML-only version (no server needed)

```bash
python dashboard/export_html.py
# → writes aria_dashboard.html (~50 KB)
```

Open in any browser — or drag to [netlify.com/drop](https://app.netlify.com/drop) for an instant public URL.

- API keys stored in `localStorage` only
- Calls Groq/Gemini directly from the browser
- Works completely offline for rendering (AI calls require internet)
- Zero backend, zero build step

---

## CLI Reference

```bash
python main.py --now                       # Full morning run + Telegram digest
python main.py --evening                   # Evening lesson + Telegram
python main.py --test                      # Test Telegram connection
python main.py --tab us-news               # Run single tab
python main.py --tab india-stocks --notify # Tab + send to Telegram
python main.py --schedule                  # Start weekday scheduler (blocking)
python main.py --dashboard                 # Launch Streamlit
python main.py --tab snapshot              # Live index values
```

Available `--tab` values: `us-news` · `india-news` · `global-news` · `us-stocks` · `india-stocks` · `lesson` · `snapshot`

---

## Estimated API Costs

ARIA runs on **free tiers** from day one:

| Scenario | Groq calls/day | Cost |
|----------|----------------|------|
| Full morning + evening run | 6 agent calls | $0 (free tier) |
| Dashboard with all 6 tabs | 6 calls | $0 (free tier) |
| Paid Groq usage (if exceeded) | $0.05 / 1M tokens | < $0.05/day |

Groq's free tier allows ~14,400 requests/day. ARIA uses 6 per full run.

---

## Add Your Own Stocks / News Sources

**Add news sources** — edit `config.py`:
```python
NEWS_SOURCES = {
    "us": {
        "my_source": "https://example.com/feed.rss",
        ...
    }
}
```

**Change LLM model** — edit `agents/ai_engine.py`:
```python
_GROQ_MODEL   = "llama-3.3-70b-versatile"   # or "mixtral-8x7b-32768"
_GEMINI_MODEL = "gemini-1.5-flash"            # or "gemini-1.5-pro"
```

**Adjust watchlist size** — edit the prompt in `agents/stock_agent.py`:
- Change `"exactly 10"` to any number

**Add a Telegram group** — set `TELEGRAM_CHAT_ID` to the group's negative ID  
(forward any group message to @userinfobot to get it)

---

## Project Structure

```
aria-stock-agent/
├── main.py                  # CLI + scheduler entry point
├── config.py                # Settings, RSS URLs, env loader
├── requirements.txt
├── Dockerfile               # Production container
├── start.sh                 # Container entrypoint (scheduler + Streamlit)
├── railway.toml             # Railway deployment config
├── .env.example             # Key template
├── aria_dashboard.html      # Self-contained zero-server dashboard
│
├── agents/
│   ├── ai_engine.py         # Groq → Gemini fallback, JSON parsing
│   ├── news_agent.py        # US / Global / India news analysis
│   ├── stock_agent.py       # Watchlists + technical indicators
│   ├── learning_agent.py    # Daily lesson + signal history
│   └── signal_agent.py      # Blends sentiment + technicals
│
├── fetchers/
│   ├── news_fetcher.py      # RSS ingestion, dedup, caching
│   └── price_fetcher.py     # yfinance OHLCV + market snapshot
│
├── notifier/
│   └── telegram.py          # Daily digest, signal alerts, lessons
│
├── dashboard/
│   ├── app.py               # Streamlit 6-tab dashboard
│   └── export_html.py       # Generates aria_dashboard.html
│
└── data/
    ├── cache/               # RSS + price cache (auto-managed)
    └── reports/             # Signal history JSON
```

---

## Disclaimer

ARIA is an experimental AI research tool built for **educational and informational purposes only**.  
It does **not** constitute financial advice. All signals, watchlists, and analysis are generated by LLMs and may be inaccurate, incomplete, or outdated.  
**Never invest based solely on AI-generated output.** Always consult a registered financial advisor before making investment decisions.  
Past performance of any signal does not guarantee future results.
