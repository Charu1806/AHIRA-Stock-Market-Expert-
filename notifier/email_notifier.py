"""Email notifier — sends ARIA digest and lesson via SMTP (Gmail / any provider)."""
from __future__ import annotations

import logging
import os
import smtplib
import time
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("aria.email")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Config — all from env vars
# ---------------------------------------------------------------------------
# SMTP_HOST     e.g. smtp.gmail.com
# SMTP_PORT     e.g. 587
# SMTP_USER     your Gmail address
# SMTP_PASS     Gmail App Password (not your login password)
# EMAIL_TO      recipient address (comma-separated for multiple)
# ---------------------------------------------------------------------------


class EmailNotifier:
    def __init__(self):
        self._host  = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self._port  = int(os.getenv("SMTP_PORT", "587"))
        self._user  = os.getenv("SMTP_USER", "")
        self._pass  = os.getenv("SMTP_PASS", "")
        self._to    = [a.strip() for a in os.getenv("EMAIL_TO", "").split(",") if a.strip()]

    def _configured(self) -> bool:
        if not all([self._user, self._pass, self._to]):
            logger.warning("[email] SMTP_USER / SMTP_PASS / EMAIL_TO not set — skipping.")
            return False
        return True

    # ------------------------------------------------------------------
    def send_daily_digest(
        self,
        us_data: dict,
        india_data: dict,
        stocks_data: dict,
        snapshot: dict | None = None,
    ) -> bool:
        if not self._configured():
            return False
        today = date.today().strftime("%d %b %Y")
        subject = f"🤖 ARIA Morning Brief — {today}"
        html = _build_digest_html(us_data, india_data, stocks_data, snapshot, today)
        return self._send(subject, html)

    def send_learning(self, lesson_data: dict) -> bool:
        if not self._configured():
            return False
        today = date.today().strftime("%d %b %Y")
        subject = f"🎓 ARIA Evening Lesson — {today}"
        html = _build_lesson_html(lesson_data, today)
        return self._send(subject, html)

    # ------------------------------------------------------------------
    def _send(self, subject: str, html: str) -> bool:
        for attempt in range(1, 4):
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"]    = f"ARIA Stock Agent <{self._user}>"
                msg["To"]      = ", ".join(self._to)
                msg.attach(MIMEText(html, "html"))

                with smtplib.SMTP(self._host, self._port) as s:
                    s.ehlo()
                    s.starttls()
                    s.login(self._user, self._pass)
                    s.sendmail(self._user, self._to, msg.as_string())

                logger.info("[email] Sent '%s' to %s", subject, self._to)
                return True
            except Exception as exc:
                logger.warning("[email] Attempt %d/3 failed: %s", attempt, exc)
                if attempt < 3:
                    time.sleep(5)
        return False


# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------

_CSS = """
body{font-family:'Helvetica Neue',Arial,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:0}
.wrap{max-width:640px;margin:0 auto;padding:24px 16px}
h1{font-size:1.4rem;color:#58a6ff;margin-bottom:4px}
.sub{color:#8b949e;font-size:.85rem;margin-bottom:24px}
.section{margin-bottom:28px}
.section-title{font-size:.8rem;font-weight:700;color:#8b949e;letter-spacing:.8px;
  text-transform:uppercase;border-bottom:1px solid #30363d;padding-bottom:6px;margin-bottom:14px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px 16px;margin-bottom:10px}
.card.bullish{border-left:4px solid #2da44e}
.card.bearish{border-left:4px solid #cf222e}
.headline{font-size:1rem;font-weight:700;margin-bottom:6px}
.summary{font-size:.85rem;color:#cdd9e5;line-height:1.6}
.aria-take{background:#1c2128;border-left:3px solid #58a6ff;border-radius:4px;
  padding:8px 12px;margin-top:10px;font-size:.83rem;color:#cdd9e5;font-style:italic}
.snap-row{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:4px}
.snap-cell{background:#161b22;border:1px solid #30363d;border-radius:6px;
  padding:10px 14px;text-align:center;min-width:90px;flex:1}
.snap-label{font-size:.65rem;font-weight:700;color:#8b949e;text-transform:uppercase;margin-bottom:3px}
.snap-val{font-size:1rem;font-weight:700}
.up{color:#2da44e}.down{color:#cf222e}
.stock-row{display:flex;justify-content:space-between;align-items:center;
  padding:8px 0;border-bottom:1px solid #30363d}
.stock-row:last-child{border-bottom:none}
.ticker{font-family:monospace;font-weight:800;font-size:1rem}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.7rem;font-weight:700}
.badge-buy   {background:rgba(45,164,78,.15);color:#2da44e;border:1px solid #2da44e}
.badge-sell  {background:rgba(207,34,46,.15);color:#cf222e;border:1px solid #cf222e}
.badge-hold  {background:rgba(210,153,34,.15);color:#d29922;border:1px solid #d29922}
.badge-watch {background:rgba(88,166,255,.15);color:#58a6ff;border:1px solid #58a6ff}
.lesson-concept{font-size:1.5rem;font-weight:800;color:#58a6ff;margin-bottom:8px}
.takeaway{background:rgba(45,164,78,.1);border:1px solid #2da44e;border-radius:6px;padding:12px 14px;color:#2da44e;font-size:.88rem}
.mistake {background:rgba(207,34,46,.1);border:1px solid #cf222e;border-radius:6px;padding:12px 14px;color:#cf222e;font-size:.88rem}
.footer{text-align:center;color:#8b949e;font-size:.75rem;padding-top:24px;border-top:1px solid #30363d}
"""

def _h(s: str) -> str:
    """HTML-escape a string."""
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _sig_badge(sig: str) -> str:
    s = sig.lower()
    cls = s if s in ("buy","sell","hold","watch") else "hold"
    return f'<span class="badge badge-{cls}">{s.upper()}</span>'

def _chg_cls(pct) -> str:
    try: return "up" if float(pct) >= 0 else "down"
    except: return "up"

def _snap_cell(label: str, data: dict) -> str:
    if "error" in data or not data:
        return f'<div class="snap-cell"><div class="snap-label">{label}</div><div class="snap-val">—</div></div>'
    price = data.get("price","—")
    chg   = data.get("change_pct")
    arrow = "▲" if (chg or 0) >= 0 else "▼"
    cls   = _chg_cls(chg)
    chg_s = f"{chg:+.2f}%" if chg is not None else "—"
    return f'<div class="snap-cell"><div class="snap-label">{label}</div><div class="snap-val">{price:,}</div><div class="snap-val {cls}" style="font-size:.8rem">{arrow} {chg_s}</div></div>'

def _story_card(story: dict) -> str:
    impacts = story.get("impacted_stocks", [])[:3]
    border  = "bullish" if any(i.get("signal")=="bullish" for i in impacts) else \
              "bearish" if any(i.get("signal")=="bearish" for i in impacts) else ""
    imp_html = ""
    if impacts:
        imp_html = "<div style='margin-top:10px'>"
        for i in impacts:
            sig = i.get("signal","neutral")
            pct = i.get("impact_pct",0)
            cls = "up" if sig=="bullish" else "down" if sig=="bearish" else ""
            imp_html += f'<span style="margin-right:12px"><b style="font-family:monospace">{_h(i.get("ticker",""))}</b> <span class="{cls}">{pct:+.1f}%</span></span>'
        imp_html += "</div>"
    take = f'<div class="aria-take">💡 {_h(story.get("aria_take",""))}</div>' if story.get("aria_take") else ""
    return f'''<div class="card {border}">
  <div class="headline">{_h(story.get("headline",""))}</div>
  <div style="color:#8b949e;font-size:.75rem;margin-bottom:8px">{_h(story.get("category","").replace("_"," ").title())} · {_h(story.get("source",""))} · {_h(story.get("date",""))}</div>
  <div class="summary">{_h(story.get("summary",""))}</div>
  {imp_html}{take}
</div>'''

def _stock_row(s: dict, direction: str) -> str:
    is_up = direction == "up"
    chg   = s.get("est_change", 0)
    cls   = "up" if is_up else "down"
    sig   = s.get("signal","hold")
    return f'''<div class="stock-row">
  <div>
    <span class="ticker">{_h(s.get("ticker",""))}</span>
    <span style="color:#8b949e;font-size:.8rem;margin-left:8px">{_h(s.get("company",""))}</span><br>
    <span style="font-size:.78rem;color:#8b949e">{_h(s.get("catalyst",""))}</span>
  </div>
  <div style="text-align:right">
    {_sig_badge(sig)}
    <div class="{cls}" style="font-weight:700;font-family:monospace">{chg:+.1f}%</div>
  </div>
</div>'''


def _build_digest_html(us: dict, india: dict, stocks: dict, snap: dict | None, today: str) -> str:
    # Snapshot
    snap_html = ""
    if snap:
        us_s = snap.get("us",{}); in_s = snap.get("india",{})
        snap_html = f'''<div class="section">
  <div class="section-title">📊 Market Snapshot</div>
  <div class="snap-row">
    {_snap_cell("S&amp;P 500", us_s.get("S&P 500",{}))}
    {_snap_cell("NASDAQ",     us_s.get("NASDAQ",{}))}
    {_snap_cell("VIX",        us_s.get("VIX",{}))}
  </div>
  <div class="snap-row">
    {_snap_cell("NIFTY 50",  in_s.get("NIFTY 50",{}))}
    {_snap_cell("SENSEX",    in_s.get("SENSEX",{}))}
    {_snap_cell("INDIA VIX", in_s.get("INDIA VIX",{}))}
  </div>
</div>'''

    # Top US story
    us_stories  = us.get("stories", [])
    in_stories  = india.get("stories", [])
    top_us      = next((s for s in us_stories    if s.get("impacted_stocks")), us_stories[0]  if us_stories  else None)
    top_india   = next((s for s in in_stories    if s.get("impacted_stocks")), in_stories[0]  if in_stories  else None)

    us_html     = f'<div class="section"><div class="section-title">🇺🇸 Top US Story</div>{_story_card(top_us)}</div>'   if top_us    else ""
    india_html  = f'<div class="section"><div class="section-title">🇮🇳 Top India Story</div>{_story_card(top_india)}</div>' if top_india else ""

    # Watchlist
    def _wl_rows(data, key, direction, limit=3):
        return "".join(_stock_row(s, direction) for s in data.get(key, [])[:limit])

    us_wl    = stocks.get("us", stocks)
    india_wl = stocks.get("india", {})
    wl_html = f'''<div class="section">
  <div class="section-title">⚡ ARIA Watchlist</div>
  <div class="card">
    <div style="font-size:.8rem;font-weight:700;color:#2da44e;margin-bottom:6px">🟢 BUY signals</div>
    {_wl_rows(us_wl,    "trending_up",   "up",   2)}
    {_wl_rows(india_wl, "trending_up",   "up",   1)}
    <div style="font-size:.8rem;font-weight:700;color:#cf222e;margin:10px 0 6px">🔴 AVOID</div>
    {_wl_rows(us_wl,    "trending_down", "down", 2)}
  </div>
</div>'''

    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ARIA Morning Brief — {today}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
  <h1>🤖 ARIA Morning Brief</h1>
  <div class="sub">{today} · Powered by Groq + Gemini</div>
  {snap_html}{us_html}{india_html}{wl_html}
  <div class="footer">
    ⚠️ Not financial advice · <a href="https://console.groq.com" style="color:#58a6ff">Groq</a> ·
    <a href="https://aistudio.google.com" style="color:#58a6ff">Gemini</a>
  </div>
</div></body></html>'''


def _build_lesson_html(lesson: dict, today: str) -> str:
    expl  = lesson.get("explanation", {})
    steps = lesson.get("next_steps", [])
    steps_html = "".join(f"<li style='margin-bottom:4px'>→ {_h(s)}</li>" for s in steps[:3])
    diff  = lesson.get("difficulty","intermediate")
    diff_color = {"beginner":"#2da44e","intermediate":"#d29922","advanced":"#cf222e"}.get(diff,"#8b949e")

    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ARIA Evening Lesson — {today}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
  <h1>🎓 ARIA Evening Lesson</h1>
  <div class="sub">{today}</div>

  <div class="lesson-concept">{_h(lesson.get("concept",""))}</div>
  <div style="font-size:.95rem;color:#cdd9e5;margin-bottom:6px">{_h(lesson.get("tagline",""))}</div>
  <div style="margin-bottom:20px"><span style="background:rgba(139,148,158,.15);color:{diff_color};
    border:1px solid {diff_color};border-radius:20px;padding:2px 10px;font-size:.72rem;font-weight:700">
    {diff.upper()}</span></div>

  <div class="card" style="margin-bottom:16px">
    <div class="section-title">Why now?</div>
    <div class="summary">{_h(lesson.get("relevance",""))}</div>
    <div style="margin-top:12px"><b style="color:#58a6ff">Core Idea</b>
    <div class="summary">{_h(expl.get("core_idea",""))}</div></div>
    <div style="margin-top:10px"><b style="color:#58a6ff">Why it matters now</b>
    <div class="summary">{_h(expl.get("why_it_matters_now",""))}</div></div>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
    <div class="takeaway"><b>✅ Takeaway</b><br><br>{_h(lesson.get("takeaway",""))}</div>
    <div class="mistake"><b>❌ Mistake</b><br><br>{_h(lesson.get("common_mistake",""))}</div>
  </div>

  {f'<div class="card"><div class="section-title">Next Steps</div><ul style="list-style:none;padding:0;color:#cdd9e5;font-size:.85rem">{steps_html}</ul></div>' if steps else ""}

  <div class="footer">⚠️ Not financial advice · ARIA Stock Agent</div>
</div></body></html>'''
