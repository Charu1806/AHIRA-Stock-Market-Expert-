"""ARIA — Stock Intelligence Agent · Streamlit Dashboard."""
from __future__ import annotations

import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Page config (must be first Streamlit call) ─────────────────────────────
st.set_page_config(
    page_title="ARIA — Stock Intelligence Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme definitions ──────────────────────────────────────────────────────
_THEMES: dict[str, dict] = {
    "Dark": {
        "bg":           "#0d1117",
        "sidebar_bg":   "#161b22",
        "card_bg":      "#161b22",
        "card_alt_bg":  "#1c2128",
        "border":       "#30363d",
        "text":         "#e6edf3",
        "text_muted":   "#8b949e",
        "text_body":    "#cdd9e5",
        "accent":       "#58a6ff",
        "badge_cat_bg": "#1a2040",
        "badge_cat_fg": "#79c0ff",
        "badge_cat_br": "#388bfd",
        "tab_inactive": "#8b949e",
        "tab_active":   "#58a6ff",
        "metric_bg":    "#161b22",
        "logo_color":   "#58a6ff",
        # signal badges
        "buy_bg": "#1a4a2a",   "buy_fg": "#2ea043",
        "sel_bg": "#4a1a1a",   "sel_fg": "#da3633",
        "hld_bg": "#3a3000",   "hld_fg": "#d29922",
        "wch_bg": "#1a2a4a",   "wch_fg": "#58a6ff",
        "sid_bg": "#2a2a3a",   "sid_fg": "#8b949e",
        # diff badges
        "beg_bg": "#0d2818",   "beg_fg": "#3fb950",
        "int_bg": "#2d1e00",   "int_fg": "#d29922",
        "adv_bg": "#300d0d",   "adv_fg": "#f85149",
        # takeaway / mistake
        "take_bg":  "#0d2818", "take_fg": "#3fb950", "take_br": "#2ea043",
        "mist_bg":  "#300d0d", "mist_fg": "#f85149", "mist_br": "#da3633",
        # plotly
        "plot_bg": "#0d1117",  "plot_grid": "#30363d", "plot_zero": "#58a6ff",
    },
    "Light": {
        "bg":           "#f6f8fa",
        "sidebar_bg":   "#ffffff",
        "card_bg":      "#ffffff",
        "card_alt_bg":  "#f0f4f8",
        "border":       "#d0d7de",
        "text":         "#1f2328",
        "text_muted":   "#57606a",
        "text_body":    "#24292f",
        "accent":       "#0969da",
        "badge_cat_bg": "#ddf4ff",
        "badge_cat_fg": "#0550ae",
        "badge_cat_br": "#54aeff",
        "tab_inactive": "#57606a",
        "tab_active":   "#0969da",
        "metric_bg":    "#f0f4f8",
        "logo_color":   "#0969da",
        # signal badges
        "buy_bg": "#dafbe1",   "buy_fg": "#116329",
        "sel_bg": "#ffd8d3",   "sel_fg": "#a0111f",
        "hld_bg": "#fff8c5",   "hld_fg": "#7d4e00",
        "wch_bg": "#ddf4ff",   "wch_fg": "#0550ae",
        "sid_bg": "#eaeef2",   "sid_fg": "#57606a",
        # diff badges
        "beg_bg": "#dafbe1",   "beg_fg": "#116329",
        "int_bg": "#fff8c5",   "int_fg": "#7d4e00",
        "adv_bg": "#ffd8d3",   "adv_fg": "#a0111f",
        # takeaway / mistake
        "take_bg":  "#dafbe1", "take_fg": "#116329", "take_br": "#2da44e",
        "mist_bg":  "#ffd8d3", "mist_fg": "#a0111f", "mist_br": "#cf222e",
        # plotly
        "plot_bg": "#ffffff",  "plot_grid": "#d0d7de", "plot_zero": "#0969da",
    },
}

# ── Theme state (must happen before sidebar is drawn) ──────────────────────
if "theme" not in st.session_state:
    st.session_state.theme = "Dark"

# ── Inject CSS for active theme ────────────────────────────────────────────
def _inject_css(t: dict) -> None:
    st.html(f"""
<style>
html, body, [data-testid="stAppViewContainer"] {{
    background-color: {t['bg']} !important;
    color: {t['text']} !important;
}}
[data-testid="stSidebar"] {{
    background-color: {t['sidebar_bg']} !important;
    border-right: 1px solid {t['border']};
}}
[data-testid="stHeader"] {{ background: transparent !important; }}
.aria-card {{
    background: {t['card_bg']};
    border: 1px solid {t['border']};
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 14px;
    color: {t['text']};
}}
.aria-card.bullish {{ border-left: 4px solid #2da44e; }}
.aria-card.bearish {{ border-left: 4px solid #cf222e; }}
.aria-card.neutral {{ border-left: 4px solid {t['text_muted']}; }}
.snap-card {{
    background: {t['card_bg']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 12px 16px;
    text-align: center;
    color: {t['text']};
}}
.snap-value  {{ font-size: 1.35rem; font-weight: 700; color: {t['text']}; }}
.snap-change.up   {{ color: #2da44e; }}
.snap-change.down {{ color: #cf222e; }}
.snap-label  {{ font-size: 0.75rem; color: {t['text_muted']}; margin-top: 2px; }}
.badge {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    margin-right: 5px;
    vertical-align: middle;
}}
.badge-buy      {{ background:{t['buy_bg']}; color:{t['buy_fg']}; border:1px solid {t['buy_fg']}; }}
.badge-sell     {{ background:{t['sel_bg']}; color:{t['sel_fg']}; border:1px solid {t['sel_fg']}; }}
.badge-hold     {{ background:{t['hld_bg']}; color:{t['hld_fg']}; border:1px solid {t['hld_fg']}; }}
.badge-watch    {{ background:{t['wch_bg']}; color:{t['wch_fg']}; border:1px solid {t['wch_fg']}; }}
.badge-bullish  {{ background:{t['buy_bg']}; color:{t['buy_fg']}; border:1px solid {t['buy_fg']}; }}
.badge-bearish  {{ background:{t['sel_bg']}; color:{t['sel_fg']}; border:1px solid {t['sel_fg']}; }}
.badge-sideways {{ background:{t['sid_bg']}; color:{t['sid_fg']}; border:1px solid {t['sid_fg']}; }}
.badge-cat      {{ background:{t['badge_cat_bg']}; color:{t['badge_cat_fg']}; border:1px solid {t['badge_cat_br']}; }}
.badge-diff-beginner     {{ background:{t['beg_bg']}; color:{t['beg_fg']}; }}
.badge-diff-intermediate {{ background:{t['int_bg']}; color:{t['int_fg']}; }}
.badge-diff-advanced     {{ background:{t['adv_bg']}; color:{t['adv_fg']}; }}
.aria-take {{
    background: {t['card_alt_bg']};
    border-left: 3px solid {t['accent']};
    border-radius: 6px;
    padding: 10px 14px;
    margin-top: 8px;
    font-style: italic;
    color: {t['text_body']};
}}
.takeaway-box {{
    background: {t['take_bg']};
    border: 1px solid {t['take_br']};
    border-radius: 8px;
    padding: 14px 18px;
    color: {t['take_fg']};
}}
.mistake-box {{
    background: {t['mist_bg']};
    border: 1px solid {t['mist_br']};
    border-radius: 8px;
    padding: 14px 18px;
    color: {t['mist_fg']};
}}
.example-card {{
    background: {t['card_alt_bg']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 14px 18px;
    color: {t['text']};
}}
.cross-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 10px;
}}
.cross-cell {{
    background: {t['card_alt_bg']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 10px 12px;
    font-size: 0.85rem;
    color: {t['text']};
}}
.cross-label {{ color: {t['text_muted']}; font-size: 0.72rem; font-weight:600; margin-bottom: 4px; }}
[data-testid="stTabs"] button {{
    color: {t['tab_inactive']} !important;
    font-weight: 600;
}}
[data-testid="stTabs"] button[aria-selected="true"] {{
    color: {t['tab_active']} !important;
    border-bottom: 2px solid {t['tab_active']} !important;
}}
[data-testid="stMetric"] {{ background: {t['metric_bg']}; border-radius:8px; padding:10px; }}
hr {{ border-color: {t['border']} !important; }}
.aria-logo {{
    font-size: 1.6rem;
    font-weight: 800;
    color: {t['logo_color']};
    letter-spacing: 2px;
}}
.aria-sub {{ font-size: 0.75rem; color: {t['text_muted']}; margin-top: -4px; }}
</style>
""")

_inject_css(_THEMES[st.session_state.theme])
T = _THEMES[st.session_state.theme]   # shorthand used throughout

# ── Imports (after path setup) ─────────────────────────────────────────────
from agents.news_agent     import NewsAgent
from agents.stock_agent    import StockAgent
from agents.learning_agent import LearningAgent
from fetchers.price_fetcher import PriceFetcher

# ── Spinner messages ───────────────────────────────────────────────────────
_SPINNERS = [
    "Consulting the oracle...",
    "Reading 10-K filings...",
    "Calling Warren Buffett...",
    "Scanning Bloomberg terminals...",
    "Bribing the Fed insider...",
    "Triangulating FII flows...",
    "Counting Rakesh Jhunjhunwala's stocks...",
    "Decoding RBI minutes...",
    "Asking Goldman's quant desk...",
    "Reverse-engineering the smart money...",
]

def _spin() -> str:
    return random.choice(_SPINNERS)

# ── Period map ─────────────────────────────────────────────────────────────
_PERIOD_MAP = {"Today": "today", "This Week": "week", "This Month": "month"}

# ── Cached agent calls ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_us_news(period: str) -> dict:
    return NewsAgent().analyse_us_news(period)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_global_news(period: str) -> dict:
    return NewsAgent().analyse_global_news(period)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_india_news(period: str) -> dict:
    return NewsAgent().analyse_india_news(period)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_us_watchlist(period: str) -> dict:
    return StockAgent().get_us_watchlist(period)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_india_watchlist(period: str) -> dict:
    return StockAgent().get_india_watchlist(period)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_lesson() -> dict:
    return LearningAgent().get_daily_lesson()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_snapshot() -> dict:
    return PriceFetcher().get_market_snapshot()

# ── Helper renderers ───────────────────────────────────────────────────────

def _badge(text: str, kind: str) -> str:
    return f'<span class="badge badge-{kind}">{text}</span>'

def _signal_badge(sig: str) -> str:
    s = sig.lower()
    return _badge(sig.upper(), s if s in ("buy","sell","hold","watch") else "hold")

def _cat_badge(cat: str) -> str:
    label = cat.replace("_", " ").title()
    return f'<span class="badge badge-cat">{label}</span>'

def _diff_badge(d: str) -> str:
    return f'<span class="badge badge-diff-{d}">{d.upper()}</span>'

def _chg_color(pct: float | None) -> str:
    if pct is None: return T["text_muted"]
    return "#2da44e" if pct >= 0 else "#cf222e"

def _story_border(story: dict) -> str:
    impacts = [i.get("signal","neutral") for i in story.get("impacted_stocks",[])]
    bulls = impacts.count("bullish")
    bears = impacts.count("bearish")
    if bulls > bears: return "bullish"
    if bears > bulls: return "bearish"
    return "neutral"

def _snap_card(label: str, data: dict) -> str:
    if "error" in data:
        return f'<div class="snap-card"><div class="snap-label">{label}</div><div class="snap-value" style="color:{T["text_muted"]}">N/A</div></div>'
    price = data.get("price", "—")
    chg   = data.get("change_pct")
    arrow = "▲" if (chg or 0) >= 0 else "▼"
    cls   = "up" if (chg or 0) >= 0 else "down"
    chg_s = f"{chg:+.2f}%" if chg is not None else "—"
    return (
        f'<div class="snap-card">'
        f'<div class="snap-label">{label}</div>'
        f'<div class="snap-value">{price:,}</div>'
        f'<div class="snap-change {cls}">{arrow} {chg_s}</div>'
        f'</div>'
    )

# ══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.html('<div class="aria-logo">🤖 ARIA</div>')
    st.html('<div class="aria-sub">Autonomous Research &amp; Investment Agent</div>')

    # ── Theme toggle ──
    new_theme = st.radio(
        "Theme",
        ["Dark", "Light"],
        index=0 if st.session_state.theme == "Dark" else 1,
        horizontal=True,
    )
    if new_theme != st.session_state.theme:
        st.session_state.theme = new_theme
        st.rerun()

    st.divider()

    period_label  = st.selectbox("Period", list(_PERIOD_MAP.keys()), index=0)
    period        = _PERIOD_MAP[period_label]
    source_filter = st.selectbox("Sources", ["All", "US Sources", "India Sources", "Global"])

    st.divider()
    run_all = st.button("🚀 Run Full Analysis", type="primary", width="stretch")

    if run_all:
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown("**Refresh individual tabs:**")
    ref_us     = st.button("🇺🇸 Refresh US News",     width="stretch")
    ref_global = st.button("🌍 Refresh Global News",   width="stretch")
    ref_india  = st.button("🇮🇳 Refresh India News",   width="stretch")
    ref_us_wl  = st.button("📈 Refresh US Stocks",     width="stretch")
    ref_in_wl  = st.button("📉 Refresh India Stocks",  width="stretch")
    ref_lesson = st.button("🎓 Refresh Lesson",        width="stretch")

    if ref_us:     fetch_us_news.clear();      st.rerun()
    if ref_global: fetch_global_news.clear();  st.rerun()
    if ref_india:  fetch_india_news.clear();   st.rerun()
    if ref_us_wl:  fetch_us_watchlist.clear(); st.rerun()
    if ref_in_wl:  fetch_india_watchlist.clear(); st.rerun()
    if ref_lesson: fetch_lesson.clear();       st.rerun()

    st.divider()
    # Provider status
    try:
        from agents.ai_engine import AIEngine
        _eng = AIEngine()
        _prov = _eng.active_provider or "none"
        _dot_color = "#2da44e" if _prov == "groq" else T["accent"] if _prov == "gemini" else T["text_muted"]
        st.html(
            f'<div style="font-size:0.8rem;color:{T["text_muted"]}">AI Provider &nbsp;'
            f'<span style="color:{_dot_color}">●</span> '
            f'<strong style="color:{T["text"]}">{_prov.upper()}</strong></div>',
        )
    except Exception:
        st.html('<div style="font-size:0.8rem;color:#da3633">● No provider configured</div>')

    st.html(
        f'<div style="font-size:0.75rem;color:{T["text_muted"]};margin-top:6px">'
        f'Last refreshed: {datetime.now().strftime("%H:%M:%S")}</div>',
    )

# ══════════════════════════════════════════════════════════════════════════
# TOP ROW — Market Snapshot
# ══════════════════════════════════════════════════════════════════════════

st.markdown("### Live Markets")

with st.spinner("Fetching market levels..."):
    snap = fetch_snapshot()

us_snap    = snap.get("us", {})
india_snap = snap.get("india", {})

cols = st.columns(6)
snap_items = [
    ("S&P 500",   us_snap.get("S&P 500", {})),
    ("NASDAQ",    us_snap.get("NASDAQ", {})),
    ("VIX",       us_snap.get("VIX", {})),
    ("NIFTY 50",  india_snap.get("NIFTY 50", {})),
    ("SENSEX",    india_snap.get("SENSEX", {})),
    ("INDIA VIX", india_snap.get("INDIA VIX", {})),
]
for col, (label, data) in zip(cols, snap_items):
    col.html(_snap_card(label, data))

st.divider()

# ══════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🇺🇸 US News & Stock Impact",
    "🌍 Global News",
    "🇮🇳 India News & Stock Impact",
    "📈 Top US Stocks",
    "📉 Top India Stocks",
    "🎓 Learning of the Day",
])

# ──────────────────────────────────────────────────────────────────────────
# TAB 1 — US News
# ──────────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("#### 🇺🇸 US Market News Analysis")
    with st.spinner(_spin()):
        try:
            us_data = fetch_us_news(period)
        except Exception as e:
            st.error(f"Failed to load US news: {e}")
            st.stop()

    mood = us_data.get("macro_mood", "mixed")
    mood_color = {"risk_on": "#2da44e", "risk_off": "#cf222e", "mixed": T["hld_fg"]}.get(mood, T["text_muted"])
    st.html(
        f'<div style="margin-bottom:14px">'
        f'Macro mood: <span style="color:{mood_color};font-weight:700">{mood.replace("_"," ").upper()}</span>'
        f'&nbsp;·&nbsp;<span style="color:{T["text_muted"]};font-size:0.85rem">{us_data.get("sector_rotation","")}</span>'
        f'</div>',
    )

    for story in us_data.get("stories", []):
        border = _story_border(story)
        impacts = story.get("impacted_stocks", [])
        with st.container():
            st.html(
                f'<div class="aria-card {border}">'
                f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">'
                f'<span style="font-size:1.05rem;font-weight:700">{story.get("headline","")}</span>'
                f'{_cat_badge(story.get("category",""))}'
                f'<span style="color:{T["text_muted"]};font-size:0.78rem">{story.get("source","")} · {story.get("date","")}</span>'
                f'</div>'
                f'<div style="color:{T["text_body"]};font-size:0.88rem;line-height:1.55">{story.get("summary","")}</div>'
                f'</div>',
            )
            if impacts:
                with st.expander(f"📊 Stock Impact ({len(impacts)} stocks)"):
                    i_cols = st.columns(min(len(impacts), 3))
                    for idx, imp in enumerate(impacts):
                        sig  = imp.get("signal","neutral")
                        clr  = {"bullish":"#2da44e","bearish":"#cf222e","neutral":T["text_muted"]}.get(sig, T["text_muted"])
                        pct  = imp.get("impact_pct", 0)
                        with i_cols[idx % len(i_cols)]:
                            st.html(
                                f'<div class="aria-card" style="padding:10px 14px">'
                                f'<div style="font-size:1.1rem;font-weight:800;color:{T["text"]}">{imp.get("ticker","")}</div>'
                                f'<div style="color:{T["text_muted"]};font-size:0.78rem;margin-bottom:6px">{imp.get("company","")}</div>'
                                f'<div>{_signal_badge(sig)} '
                                f'<span style="color:{clr};font-weight:700">{pct:+.1f}%</span></div>'
                                f'<div style="font-size:0.8rem;color:{T["text_body"]};margin-top:6px">{imp.get("why","")}</div>'
                                f'</div>',
                            )
            take = story.get("aria_take","")
            if take:
                st.html(f'<div class="aria-take">💡 <strong>ARIA:</strong> {take}</div>')

# ──────────────────────────────────────────────────────────────────────────
# TAB 2 — Global News
# ──────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("#### 🌍 Global Macro Analysis")
    with st.spinner(_spin()):
        try:
            gl_data = fetch_global_news(period)
        except Exception as e:
            st.error(f"Failed to load global news: {e}")
            st.stop()

    dom = gl_data.get("dominant_theme","")
    tail = gl_data.get("tail_risk","")
    if dom:
        st.info(f"**Dominant theme:** {dom}")
    if tail:
        st.warning(f"**Tail risk:** {tail}")

    for story in gl_data.get("stories", []):
        cmi = story.get("cross_market_impact", {})
        with st.container():
            st.html(
                f'<div class="aria-card neutral">'
                f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">'
                f'<span style="font-size:1.05rem;font-weight:700">{story.get("headline","")}</span>'
                f'{_cat_badge(story.get("category",""))}'
                f'<span style="color:{T["text_muted"]};font-size:0.78rem">{story.get("source","")} · {story.get("date","")}</span>'
                f'</div>'
                f'<div style="color:{T["text_body"]};font-size:0.88rem;line-height:1.55;margin-bottom:10px">{story.get("summary","")}</div>'
                f'<div class="cross-grid">'
                f'<div class="cross-cell"><div class="cross-label">🇺🇸 US EQUITIES</div>{cmi.get("us_equities","—")}</div>'
                f'<div class="cross-cell"><div class="cross-label">🇮🇳 INDIA EQUITIES</div>{cmi.get("india_equities","—")}</div>'
                f'<div class="cross-cell"><div class="cross-label">🛢 COMMODITIES</div>{cmi.get("commodities","—")}</div>'
                f'<div class="cross-cell"><div class="cross-label">💱 CURRENCIES</div>{cmi.get("currencies","—")}</div>'
                f'</div>'
                f'</div>',
            )
            take = story.get("aria_take","")
            if take:
                st.html(f'<div class="aria-take">💡 <strong>ARIA:</strong> {take}</div>')

# ──────────────────────────────────────────────────────────────────────────
# TAB 3 — India News
# ──────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("#### 🇮🇳 India Market Analysis")
    with st.spinner(_spin()):
        try:
            in_data = fetch_india_news(period)
        except Exception as e:
            st.error(f"Failed to load India news: {e}")
            st.stop()

    # FII/DII indicator
    fii = in_data.get("fii_dii_summary","")
    nifty_pulse = in_data.get("nifty_pulse","")
    if fii or nifty_pulse:
        fc1, fc2 = st.columns(2)
        if fii:
            st.html(
                f'<div class="aria-card" style="padding:10px 14px">'
                f'<div style="color:{T["text_muted"]};font-size:0.72rem;font-weight:600">FII/DII FLOW TREND</div>'
                f'<div style="font-size:0.88rem;margin-top:4px">{fii}</div>'
                f'</div>',
            )
        if nifty_pulse:
            st.html(
                f'<div class="aria-card" style="padding:10px 14px">'
                f'<div style="color:{T["text_muted"]};font-size:0.72rem;font-weight:600">NIFTY PULSE</div>'
                f'<div style="font-size:0.88rem;margin-top:4px">{nifty_pulse}</div>'
                f'</div>',
            )
        rupee = in_data.get("rupee_view","")
        if rupee:
            st.html(
                f'<div style="color:{T["text_muted"]};font-size:0.82rem;margin-bottom:14px">💱 Rupee: {rupee}</div>',
            )

    for story in in_data.get("stories", []):
        border = _story_border(story)
        impacts = story.get("impacted_stocks", [])
        with st.container():
            st.html(
                f'<div class="aria-card {border}">'
                f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">'
                f'<span style="font-size:1.05rem;font-weight:700">{story.get("headline","")}</span>'
                f'{_cat_badge(story.get("category",""))}'
                f'<span style="color:{T["text_muted"]};font-size:0.78rem">{story.get("source","")} · {story.get("date","")}</span>'
                f'</div>'
                f'<div style="color:{T["text_body"]};font-size:0.88rem;line-height:1.55">{story.get("summary","")}</div>'
                f'</div>',
            )
            if impacts:
                with st.expander(f"📊 Stock Impact ({len(impacts)} stocks)"):
                    i_cols = st.columns(min(len(impacts), 3))
                    for idx, imp in enumerate(impacts):
                        sig = imp.get("signal","neutral")
                        clr = {"bullish":"#2da44e","bearish":"#cf222e","neutral":T["text_muted"]}.get(sig, T["text_muted"])
                        pct = imp.get("impact_pct", 0)
                        with i_cols[idx % len(i_cols)]:
                            st.html(
                                f'<div class="aria-card" style="padding:10px 14px">'
                                f'<div style="font-size:1.1rem;font-weight:800;color:{T["text"]}">{imp.get("ticker","")}</div>'
                                f'<div style="color:{T["text_muted"]};font-size:0.78rem;margin-bottom:6px">{imp.get("company","")}</div>'
                                f'<div>{_signal_badge(sig)} '
                                f'<span style="color:{clr};font-weight:700">{pct:+.1f}%</span></div>'
                                f'<div style="font-size:0.8rem;color:{T["text_body"]};margin-top:6px">{imp.get("why","")}</div>'
                                f'</div>',
                            )
            take = story.get("aria_take","")
            if take:
                st.html(f'<div class="aria-take">💡 <strong>ARIA:</strong> {take}</div>')

# ──────────────────────────────────────────────────────────────────────────
# TAB 4 — US Watchlist
# ──────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown("#### 📈 US Stocks Watchlist — ARIA's Picks")
    with st.spinner(_spin()):
        try:
            us_wl = fetch_us_watchlist(period)
        except Exception as e:
            st.error(f"Failed to load US watchlist: {e}")
            st.stop()

    macro_ctx = us_wl.get("macro_context","")
    if macro_ctx:
        st.html(f'<div style="color:{T["text_muted"]};font-size:0.88rem;margin-bottom:16px">{macro_ctx}</div>')

    up_col, dn_col = st.columns(2)

    def _stock_card(s: dict, direction: str) -> str:
        is_up  = direction == "up"
        border = "bullish" if is_up else "bearish"
        sig    = s.get("signal","hold")
        chg    = s.get("est_change", 0)
        chg_c  = "#2da44e" if is_up else "#cf222e"
        cat    = s.get("catalyst","")
        reason = s.get("why_up") if is_up else s.get("why_down","")
        note   = s.get("risk") if is_up else s.get("recovery_watch","")
        note_lbl = "⚠ Risk" if is_up else "🔄 Recovery watch"
        tags   = s.get("tags",[])
        tag_html = " ".join(f'<span class="badge badge-cat">{t}</span>' for t in tags[:3])
        mom    = s.get("momentum","")
        return (
            f'<div class="aria-card {border}">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
            f'  <div>'
            f'    <span style="font-size:1.4rem;font-weight:800;color:{T["text"]}">{s.get("ticker","")}</span>'
            f'    <span style="color:{T["text_muted"]};font-size:0.8rem;margin-left:8px">{s.get("company","")}</span>'
            f'  </div>'
            f'  <span style="font-size:1.2rem;font-weight:700;color:{chg_c}">{chg:+.1f}%</span>'
            f'</div>'
            f'<div style="margin:6px 0">{_signal_badge(sig)}'
            f'  <span style="color:{T["text_muted"]};font-size:0.78rem">{s.get("sector","")} · {mom} momentum</span>'
            f'</div>'
            f'<div style="font-size:0.85rem;color:{T["text_body"]};margin-bottom:8px">{reason}</div>'
            f'<div style="margin-bottom:6px">'
            f'  <span style="color:{T["text_muted"]};font-size:0.72rem">CATALYST: </span>'
            f'  <span class="badge badge-cat">{cat}</span>'
            f'</div>'
            f'{tag_html}'
            f'<div style="font-size:0.78rem;color:{T["text_muted"]};margin-top:8px">'
            f'  <strong>{note_lbl}:</strong> {note}'
            f'</div>'
            f'</div>'
        )

    with up_col:
        st.html(f'<div style="color:#2da44e;font-weight:700;font-size:1rem;margin-bottom:10px">▲ TRENDING UP</div>')
        for s in us_wl.get("trending_up", []):
            st.html(_stock_card(s, "up"))

    with dn_col:
        st.html(f'<div style="color:#cf222e;font-weight:700;font-size:1rem;margin-bottom:10px">▼ TRENDING DOWN</div>')
        for s in us_wl.get("trending_down", []):
            st.html(_stock_card(s, "down"))

    # Bar chart
    st.divider()
    st.markdown("##### Estimated Move Summary")
    all_stocks = [
        {"Ticker": s["ticker"], "Est Change %": s.get("est_change",0), "Direction": "Up"}
        for s in us_wl.get("trending_up", [])
    ] + [
        {"Ticker": s["ticker"], "Est Change %": s.get("est_change",0), "Direction": "Down"}
        for s in us_wl.get("trending_down", [])
    ]
    if all_stocks:
        df_chart = pd.DataFrame(all_stocks).sort_values("Est Change %", ascending=False)
        colors   = ["#2da44e" if d == "Up" else "#cf222e" for d in df_chart["Direction"]]
        fig = go.Figure(go.Bar(
            x=df_chart["Ticker"],
            y=df_chart["Est Change %"],
            marker_color=colors,
            text=[f"{v:+.1f}%" for v in df_chart["Est Change %"]],
            textposition="outside",
        ))
        fig.update_layout(
            paper_bgcolor=T["plot_bg"], plot_bgcolor=T["plot_bg"],
            font_color=T["text"], height=320,
            margin=dict(t=20, b=20, l=10, r=10),
            xaxis=dict(gridcolor=T["plot_grid"]),
            yaxis=dict(gridcolor=T["plot_grid"], zeroline=True, zerolinecolor=T["plot_zero"]),
        )
        st.plotly_chart(fig, width="stretch")

    summary = us_wl.get("aria_summary","")
    if summary:
        st.html(f'<div class="aria-take">💡 <strong>ARIA:</strong> {summary}</div>')

# ──────────────────────────────────────────────────────────────────────────
# TAB 5 — India Watchlist
# ──────────────────────────────────────────────────────────────────────────
with tab5:
    st.markdown("#### 📉 India Stocks Watchlist — ARIA's Picks")
    with st.spinner(_spin()):
        try:
            in_wl = fetch_india_watchlist(period)
        except Exception as e:
            st.error(f"Failed to load India watchlist: {e}")
            st.stop()

    # Nifty view badge
    nv = in_wl.get("nifty_view","Sideways")
    nv_map = {"Bullish":"bullish","Bearish":"bearish","Sideways":"sideways"}
    nv_key = nv_map.get(nv,"sideways")
    nt  = in_wl.get("nifty_target_near","")
    ns  = in_wl.get("nifty_support","")
    fii_note = in_wl.get("fii_dii_note","")
    macro_ctx_in = in_wl.get("macro_context","")

    hc1, hc2, hc3 = st.columns(3)
    st.html(
        f'<div class="aria-card" style="padding:10px 14px;text-align:center">'
        f'<div style="color:{T["text_muted"]};font-size:0.72rem">NIFTY VIEW</div>'
        f'<div style="margin-top:4px">{_badge(nv, nv_key)}</div>'
        f'</div>',
    )
    st.html(
        f'<div class="aria-card" style="padding:10px 14px;text-align:center">'
        f'<div style="color:{T["text_muted"]};font-size:0.72rem">TARGET / SUPPORT</div>'
        f'<div style="color:#2ea043;font-weight:700">{nt}</div>'
        f'<div style="color:#da3633;font-size:0.8rem">{ns}</div>'
        f'</div>',
    )
    st.html(
        f'<div class="aria-card" style="padding:10px 14px">'
        f'<div style="color:{T["text_muted"]};font-size:0.72rem">FII/DII</div>'
        f'<div style="font-size:0.82rem;margin-top:4px">{fii_note}</div>'
        f'</div>',
    )
    if macro_ctx_in:
        st.html(f'<div style="color:{T["text_muted"]};font-size:0.88rem;margin:12px 0">{macro_ctx_in}</div>')

    up_col_i, dn_col_i = st.columns(2)

    def _india_card(s: dict, direction: str) -> str:
        is_up  = direction == "up"
        border = "bullish" if is_up else "bearish"
        sig    = s.get("signal","hold")
        chg    = s.get("est_change", 0)
        chg_c  = "#2da44e" if is_up else "#cf222e"
        cat    = s.get("catalyst","")
        reason = s.get("why_up") if is_up else s.get("why_down","")
        note   = s.get("risk") if is_up else s.get("recovery_watch","")
        note_lbl = "⚠ Risk" if is_up else "🔄 Recovery watch"
        idx_label = s.get("index","")
        tags   = s.get("tags",[])
        tag_html = " ".join(f'<span class="badge badge-cat">{t}</span>' for t in tags[:3])
        return (
            f'<div class="aria-card {border}">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
            f'  <div>'
            f'    <span style="font-size:1.3rem;font-weight:800;color:{T["text"]}">{s.get("ticker","")}</span>'
            f'    <span style="color:{T["text_muted"]};font-size:0.8rem;margin-left:8px">{s.get("company","")}</span>'
            f'  </div>'
            f'  <span style="font-size:1.2rem;font-weight:700;color:{chg_c}">{chg:+.1f}%</span>'
            f'</div>'
            f'<div style="margin:6px 0">{_signal_badge(sig)}'
            f'  <span style="color:{T["text_muted"]};font-size:0.78rem">{s.get("sector","")} · {idx_label}</span>'
            f'</div>'
            f'<div style="font-size:0.85rem;color:{T["text_body"]};margin-bottom:8px">{reason}</div>'
            f'<div style="margin-bottom:6px">'
            f'  <span style="color:{T["text_muted"]};font-size:0.72rem">CATALYST: </span>'
            f'  <span class="badge badge-cat">{cat}</span>'
            f'</div>'
            f'{tag_html}'
            f'<div style="font-size:0.78rem;color:{T["text_muted"]};margin-top:8px">'
            f'  <strong>{note_lbl}:</strong> {note}'
            f'</div>'
            f'</div>'
        )

    with up_col_i:
        st.html('<div style="color:#2ea043;font-weight:700;font-size:1rem;margin-bottom:10px">▲ TRENDING UP</div>')
        for s in in_wl.get("trending_up", []):
            st.html(_india_card(s, "up"))

    with dn_col_i:
        st.html('<div style="color:#da3633;font-weight:700;font-size:1rem;margin-bottom:10px">▼ TRENDING DOWN</div>')
        for s in in_wl.get("trending_down", []):
            st.html(_india_card(s, "down"))

    # Bar chart
    st.divider()
    st.markdown("##### Estimated Move Summary")
    all_india = [
        {"Ticker": s["ticker"].replace(".NS",""), "Est Change %": s.get("est_change",0), "Direction": "Up"}
        for s in in_wl.get("trending_up", [])
    ] + [
        {"Ticker": s["ticker"].replace(".NS",""), "Est Change %": s.get("est_change",0), "Direction": "Down"}
        for s in in_wl.get("trending_down", [])
    ]
    if all_india:
        df_in = pd.DataFrame(all_india).sort_values("Est Change %", ascending=False)
        colors_in = ["#2da44e" if d == "Up" else "#cf222e" for d in df_in["Direction"]]
        fig2 = go.Figure(go.Bar(
            x=df_in["Ticker"],
            y=df_in["Est Change %"],
            marker_color=colors_in,
            text=[f"{v:+.1f}%" for v in df_in["Est Change %"]],
            textposition="outside",
        ))
        fig2.update_layout(
            paper_bgcolor=T["plot_bg"], plot_bgcolor=T["plot_bg"],
            font_color=T["text"], height=320,
            margin=dict(t=20, b=20, l=10, r=10),
            xaxis=dict(gridcolor=T["plot_grid"]),
            yaxis=dict(gridcolor=T["plot_grid"], zeroline=True, zerolinecolor=T["plot_zero"]),
        )
        st.plotly_chart(fig2, width="stretch")

    summary_in = in_wl.get("aria_summary","")
    if summary_in:
        st.html(f'<div class="aria-take">💡 <strong>ARIA:</strong> {summary_in}</div>')

# ──────────────────────────────────────────────────────────────────────────
# TAB 6 — Learning of the Day
# ──────────────────────────────────────────────────────────────────────────
with tab6:
    st.markdown("#### 🎓 Learning of the Day")
    with st.spinner(_spin()):
        try:
            lesson = fetch_lesson()
        except Exception as e:
            st.error(f"Failed to load lesson: {e}")
            st.stop()

    diff = lesson.get("difficulty","intermediate")
    st.html(
        f'<div style="margin-bottom:18px">'
        f'<div style="font-size:1.8rem;font-weight:800;color:{T["accent"]};margin-bottom:6px">'
        f'{lesson.get("concept","")}</div>'
        f'<div style="font-size:1rem;color:#cdd9e5;margin-bottom:10px">'
        f'{lesson.get("tagline","")}</div>'
        f'{_diff_badge(diff)}'
        f'<span style="color:{T["text_muted"]};font-size:0.82rem;margin-left:8px">'
        f'via {lesson.get("_provider","AI")}</span>'
        f'</div>',
    )

    # Relevance
    relevance = lesson.get("relevance","")
    if relevance:
        st.info(f"**Why now?** {relevance}")

    # Explanation
    expl = lesson.get("explanation", {})
    if expl:
        st.html(
            f'<div class="aria-card" style="margin-bottom:14px">'
            f'<div style="color:{T["text_muted"]};font-size:0.72rem;font-weight:600;margin-bottom:8px">EXPLANATION</div>'
            f'<div style="margin-bottom:10px"><strong style="color:{T["accent"]}">Core idea</strong><br>'
            f'<span style="color:{T["text_body"]};font-size:0.9rem">{expl.get("core_idea","")}</span></div>'
            f'<div style="margin-bottom:10px"><strong style="color:{T["accent"]}">How it works</strong><br>'
            f'<span style="color:{T["text_body"]};font-size:0.9rem">{expl.get("mechanics","")}</span></div>'
            f'<div><strong style="color:{T["accent"]}">Why it matters right now</strong><br>'
            f'<span style="color:{T["text_body"]};font-size:0.9rem">{expl.get("why_it_matters_now","")}</span></div>'
            f'</div>',
        )

    # Real example
    ex = lesson.get("real_example", {})
    if ex:
        st.html(
            f'<div class="example-card" style="margin-bottom:14px">'
            f'<div style="color:{T["text_muted"]};font-size:0.72rem;font-weight:600;margin-bottom:6px">📰 REAL EXAMPLE</div>'
            f'<div style="font-weight:700;color:{T["text"]};margin-bottom:8px">{ex.get("title","")}</div>'
            f'<div style="color:{T["text_body"]};font-size:0.88rem;line-height:1.6">{ex.get("body","")}</div>'
            f'</div>',
        )

    # India / US angles
    a_col, b_col = st.columns(2)
    india_angle = lesson.get("india_angle","")
    us_angle    = lesson.get("us_angle","")
    if india_angle:
        st.html(
            f'<div class="aria-card" style="padding:12px 16px">'
            f'<div style="color:{T["text_muted"]};font-size:0.72rem;font-weight:600;margin-bottom:6px">🇮🇳 INDIA ANGLE</div>'
            f'<div style="color:{T["text_body"]};font-size:0.88rem">{india_angle}</div>'
            f'</div>',
        )
    if us_angle:
        st.html(
            f'<div class="aria-card" style="padding:12px 16px">'
            f'<div style="color:{T["text_muted"]};font-size:0.72rem;font-weight:600;margin-bottom:6px">🇺🇸 US ANGLE</div>'
            f'<div style="color:{T["text_body"]};font-size:0.88rem">{us_angle}</div>'
            f'</div>',
        )

    st.write("")

    # Takeaway + Mistake
    t_col, m_col = st.columns(2)
    takeaway = lesson.get("takeaway","")
    mistake  = lesson.get("common_mistake","")
    if takeaway:
        st.html(
            f'<div class="takeaway-box">'
            f'<strong>✅ Key Takeaway</strong><br><br>{takeaway}'
            f'</div>',
        )
    if mistake:
        st.html(
            f'<div class="mistake-box">'
            f'<strong>❌ Common Mistake</strong><br><br>{mistake}'
            f'</div>',
        )

    # Next steps
    steps = lesson.get("next_steps",[])
    if steps:
        st.write("")
        st.markdown("**Next steps:**")
        for step in steps:
            st.markdown(f"→ {step}")
