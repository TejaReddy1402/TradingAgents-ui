"""Streamlit UI for browsing TradingAgents reports and launching new runs.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import base64
import contextlib
import re
import traceback
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import streamlit as st


# Pre-warm the tradingagents package import once per server process.
# langchain_core (a transitive dep of langgraph) is slow to import cold;
# doing it here with cache_resource means the first page render doesn't block
# on it — subsequent reruns hit the cached no-op and return instantly.
@st.cache_resource(show_spinner=False)
def _warm_imports() -> None:
    with contextlib.suppress(Exception):
        import tradingagents  # noqa: F401

_warm_imports()

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).parent.resolve()
REPORTS_DIR = PROJECT_DIR / "reports"

# Section folder -> (label, ordered files with display name)
SECTION_LAYOUT = {
    "1_analysts": [
        ("market.md", "Market"),
        ("sentiment.md", "Sentiment"),
        ("news.md", "News"),
        ("fundamentals.md", "Fundamentals"),
    ],
    "2_research": [
        ("bull.md", "Bull Researcher"),
        ("bear.md", "Bear Researcher"),
        ("manager.md", "Research Manager"),
    ],
    "3_trading": [
        ("trader.md", "Trader"),
    ],
    "4_risk": [
        ("aggressive.md", "Aggressive"),
        ("conservative.md", "Conservative"),
        ("neutral.md", "Neutral"),
    ],
    "5_portfolio": [
        ("decision.md", "Portfolio Manager"),
    ],
}

DECISION_COLORS = {
    "BUY":          ("#16a34a", "#dcfce7"),  # green
    "STRONG BUY":   ("#15803d", "#bbf7d0"),
    "SELL":         ("#dc2626", "#fee2e2"),  # red
    "STRONG SELL":  ("#b91c1c", "#fecaca"),
    "HOLD":         ("#ca8a04", "#fef9c3"),  # amber
    "NEUTRAL":      ("#475569", "#e2e8f0"),  # slate
    "UNDERWEIGHT":  ("#ea580c", "#ffedd5"),
    "OVERWEIGHT":   ("#0891b2", "#cffafe"),
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Run:
    path: Path
    ticker: str
    timestamp: datetime

    @property
    def folder_name(self) -> str:
        return self.path.name

    @property
    def display_label(self) -> str:
        return f"{self.ticker} · {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


def parse_run_folder(folder: Path) -> Run | None:
    """Parse folders like NVDA_20260623_133154 into a Run."""
    m = re.match(r"^(.+)_(\d{8})_(\d{6})$", folder.name)
    if not m:
        return None
    ticker, ymd, hms = m.groups()
    try:
        ts = datetime.strptime(f"{ymd}{hms}", "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return Run(path=folder, ticker=ticker, timestamp=ts)


@st.cache_data(ttl=5)
def list_runs(reports_dir_str: str) -> list[Run]:
    """Rescan reports/ with a 5-second TTL cache so switching between reports
    doesn't trigger a directory walk on every interaction.
    """
    reports_dir = Path(reports_dir_str)
    if not reports_dir.exists():
        return []
    runs = []
    for p in reports_dir.iterdir():
        if not p.is_dir():
            continue
        run = parse_run_folder(p)
        if run is not None:
            runs.append(run)
    runs.sort(key=lambda r: r.timestamp, reverse=True)
    return runs


@st.cache_data(ttl=60)
def read_md(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Decision extraction
# ---------------------------------------------------------------------------

DECISION_KEYWORDS_PRIORITY = [
    "STRONG BUY", "STRONG SELL",
    "UNDERWEIGHT", "OVERWEIGHT",
    "BUY", "SELL", "HOLD", "NEUTRAL",
]


def extract_decision(run: Run) -> str | None:
    """Look at portfolio decision.md (then trader.md) for a BUY/HOLD/SELL signal."""
    candidates = [
        run.path / "5_portfolio" / "decision.md",
        run.path / "3_trading" / "trader.md",
    ]
    for candidate in candidates:
        text = read_md(candidate)
        if not text:
            continue
        upper = text.upper()
        for kw in DECISION_KEYWORDS_PRIORITY:
            if kw in upper:
                return kw
    return None


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
    /* Tighter top padding, wider container */
    .block-container { padding-top: 1.5rem; padding-bottom: 4rem; max-width: 1400px; }

    /* Decision badges */
    .decision-badge {
        display: inline-block;
        padding: 6px 18px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.95rem;
        letter-spacing: 0.04em;
    }
    .decision-badge-xl {
        display: inline-block;
        padding: 10px 28px;
        border-radius: 999px;
        font-weight: 800;
        font-size: 1.35rem;
        letter-spacing: 0.06em;
    }

    /* Hero card for the focused run */
    .hero-card {
        border: 1px solid rgba(125,125,125,0.18);
        border-radius: 16px;
        padding: 28px 32px;
        margin-bottom: 18px;
        background: linear-gradient(135deg,
            rgba(37,99,235,0.04) 0%,
            rgba(125,125,125,0.02) 100%);
    }
    .hero-card .ticker {
        font-size: 2.4rem;
        font-weight: 800;
        line-height: 1.1;
        margin: 0;
    }
    .hero-card .meta {
        color: rgba(100,100,100,0.95);
        font-size: 0.92rem;
        margin-top: 6px;
    }

    /* Section column headers in debates */
    .col-header {
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: rgba(125,125,125,0.9);
        margin-bottom: 6px;
    }

    /* History row cards */
    .hist-card {
        border: 1px solid rgba(125,125,125,0.15);
        border-radius: 10px;
        padding: 10px 14px;
        background: rgba(255,255,255,0.02);
    }
    .hist-card .ticker { font-weight: 700; font-size: 0.95rem; }
    .hist-card .meta { color: rgba(125,125,125,0.85); font-size: 0.78rem; }

    /* Section dialog button hint */
    .section-popout {
        text-align: right;
        font-size: 0.78rem;
        color: rgba(125,125,125,0.85);
        margin-bottom: 4px;
    }

    /* Hide Streamlit chrome */
    #MainMenu, footer { visibility: hidden; }

    /* Tab labels a bit roomier */
    button[data-baseweb="tab"] { padding-top: 0.5rem; padding-bottom: 0.5rem; }

    /* Fix dialog scroll — Streamlit caps dialog height but doesn't set
       overflow on the inner content div, so long reports get clipped. */
    div[data-testid="stDialog"] div[data-testid="stDialogContent"] {
        max-height: 78vh;
        overflow-y: auto !important;
    }

    /* Ensure tab panel content can scroll freely on the main page */
    div[data-testid="stTabPanel"] {
        overflow-y: visible !important;
        overflow-x: hidden;
    }

    /* Prevent any stray overflow:hidden on the main content area */
    section.main > div { overflow: visible !important; }

    /* Long markdown tables should scroll horizontally rather than overflow */
    div[data-testid="stMarkdownContainer"] table {
        display: block;
        overflow-x: auto;
    }
</style>
"""


def decision_badge_html(decision: str | None, size: str = "md") -> str:
    cls = "decision-badge-xl" if size == "xl" else "decision-badge"
    if not decision:
        return f'<span class="{cls}" style="background:#e2e8f0;color:#475569;">NO DECISION</span>'
    fg, bg = DECISION_COLORS.get(decision, ("#475569", "#e2e8f0"))
    return f'<span class="{cls}" style="background:{bg};color:{fg};">{decision}</span>'


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

_LONG_DASH_CELL = re.compile(r"(?<=\|)([ \t]*)[-:]{20,}([ \t]*)(?=\|)")


def _normalize_md(text: str) -> str:
    """Normalize LLM table artifacts before rendering.

    LLMs sometimes generate table separator rows with thousands of dashes
    instead of the standard '---', causing blank oversized tables.
    Replace any pipe-delimited cell that is purely dashes/colons (>= 20 chars)
    with the minimal '---' so the table renders correctly at a sensible size.
    """
    return _LONG_DASH_CELL.sub(r"\1---\2", text)


def render_markdown(text: str) -> None:
    """Render markdown content. Streamlit handles LaTeX via $...$ natively."""
    st.markdown(_normalize_md(text), unsafe_allow_html=False)


def _section_files(run: Run, section_folder: str) -> list[tuple[Path, str]]:
    """Return (file_path, display_label) tuples for files that exist in this section."""
    section_dir = run.path / section_folder
    if not section_dir.exists():
        return []
    found = []
    for fname, label in SECTION_LAYOUT[section_folder]:
        p = section_dir / fname
        if p.exists():
            found.append((p, label))
    return found


# Floating modal that pops out a section in a larger view. Streamlit registers
# this dialog and any call from anywhere on the page opens it as a modal.
@st.dialog("Section detail", width="large")
def _section_dialog(title: str, body_md: str) -> None:
    st.subheader(title)
    st.markdown(body_md or "_Empty section._", unsafe_allow_html=False)


def _popout_button(label: str, title: str, body: str, key: str) -> None:
    """A small 'pop out' button that opens the section content in a floating dialog."""
    if st.button(label, key=key, help="Open this section in a floating window"):
        _section_dialog(title, body)


def _render_section_portfolio(run: Run) -> None:
    files = _section_files(run, "5_portfolio")
    if not files:
        st.info("No portfolio decision available.")
        return
    body = "\n\n".join(read_md(p) or "" for p, _ in files)
    cols = st.columns([8, 1])
    with cols[1]:
        _popout_button("↗ Pop out", "Portfolio Decision", body, key=f"pop_pm_{run.folder_name}")
    render_markdown(body)


def _render_section_analysts(run: Run) -> None:
    files = _section_files(run, "1_analysts")
    if not files:
        st.info("No analyst reports.")
        return
    sub = st.tabs([lbl for _, lbl in files])
    for tab, (path, label) in zip(sub, files, strict=False):
        with tab:
            body = read_md(path) or ""
            cols = st.columns([8, 1])
            with cols[1]:
                _popout_button(
                    "↗ Pop out", f"{label} Analyst",
                    body, key=f"pop_an_{run.folder_name}_{label}",
                )
            render_markdown(body)


def _render_section_research(run: Run) -> None:
    files_map = {lbl: path for path, lbl in _section_files(run, "2_research")}
    if not files_map:
        st.info("No research debate available.")
        return

    bull = read_md(files_map["Bull Researcher"]) if files_map.get("Bull Researcher") else ""
    bear = read_md(files_map["Bear Researcher"]) if files_map.get("Bear Researcher") else ""
    manager = read_md(files_map["Research Manager"]) if files_map.get("Research Manager") else ""

    pop_cols = st.columns([6, 1, 1, 1])
    with pop_cols[1]:
        _popout_button("🐂 Bull", "Bull Researcher", bull or "_No bull research._", f"pop_bull_{run.folder_name}")
    with pop_cols[2]:
        _popout_button("🐻 Bear", "Bear Researcher", bear or "_No bear research._", f"pop_bear_{run.folder_name}")
    with pop_cols[3]:
        _popout_button("⚖️ Verdict", "Research Manager", manager or "_No verdict._", f"pop_mgr_{run.folder_name}")

    cols = st.columns(2)
    with cols[0]:
        st.markdown('<div class="col-header">🐂 Bull</div>', unsafe_allow_html=True)
        render_markdown(bull or "_No bull research._")
    with cols[1]:
        st.markdown('<div class="col-header">🐻 Bear</div>', unsafe_allow_html=True)
        render_markdown(bear or "_No bear research._")
    if manager:
        st.divider()
        st.markdown('<div class="col-header">⚖️ Research Manager Verdict</div>', unsafe_allow_html=True)
        render_markdown(manager)


def _render_section_trading(run: Run) -> None:
    files = _section_files(run, "3_trading")
    if not files:
        st.info("No trading plan.")
        return
    body = "\n\n".join(read_md(p) or "" for p, _ in files)
    cols = st.columns([8, 1])
    with cols[1]:
        _popout_button("↗ Pop out", "Trading Plan", body, key=f"pop_tr_{run.folder_name}")
    render_markdown(body)


def _render_section_risk(run: Run) -> None:
    files_map = {lbl: path for path, lbl in _section_files(run, "4_risk")}
    if not files_map:
        st.info("No risk debate available.")
        return

    order = [("Aggressive", "🔥"), ("Neutral", "⚖️"), ("Conservative", "🛡️")]
    pop_cols = st.columns([5, 1, 1, 1])
    for col, (label, icon) in zip(pop_cols[1:], order, strict=False):
        with col:
            body = read_md(files_map.get(label)) if files_map.get(label) else f"_No {label.lower()} analysis._"
            _popout_button(
                f"{icon} {label[:4]}", f"{icon} {label} Analyst", body,
                key=f"pop_risk_{run.folder_name}_{label}",
            )

    cols = st.columns(3)
    for col, (label, icon) in zip(cols, order, strict=False):
        with col:
            st.markdown(f'<div class="col-header">{icon} {label}</div>', unsafe_allow_html=True)
            p = files_map.get(label)
            render_markdown(read_md(p) if p else f"_No {label.lower()} analysis._")


def _render_section_full(run: Run) -> None:
    full = run.path / "complete_report.md"
    if not full.exists():
        st.info("complete_report.md not found.")
        return
    body = read_md(full) or ""
    cols = st.columns([7, 1, 1])
    with cols[1]:
        _popout_button("↗ Pop out", f"{run.ticker} — Full Report", body, key=f"pop_full_{run.folder_name}")
    with cols[2]:
        b64 = base64.b64encode(body.encode("utf-8")).decode()
        fname = f"{run.ticker}_{run.timestamp.strftime('%Y%m%d_%H%M%S')}.md"
        st.markdown(
            f'<a href="data:text/markdown;base64,{b64}" download="{fname}"'
            f' style="display:block;text-align:center;padding:0.4rem 0.5rem;'
            f'border:1px solid rgba(49,51,63,0.2);border-radius:0.5rem;'
            f'text-decoration:none;font-size:0.85rem;color:inherit;">⬇ MD</a>',
            unsafe_allow_html=True,
        )
    render_markdown(body)


def page_dashboard(runs: list[Run]) -> None:
    """Unified dashboard: run toggle bar on top + focused report below + history."""
    st.markdown("### 📈 Trading Agents — Dashboard")

    if not runs:
        st.info("No runs yet. Switch to **Run Analysis** in the sidebar to generate your first report.")
        return

    # --- Run toggle bar (pills, newest first) ---
    folder_to_run = {r.folder_name: r for r in runs}
    folder_order = list(folder_to_run.keys())

    def _pill_label(folder: str) -> str:
        r = folder_to_run[folder]
        d = extract_decision(r) or "—"
        return f"{r.ticker} · {r.timestamp.strftime('%b %d %H:%M')}  ({d})"

    selected_folder = st.session_state.get("selected_run") or folder_order[0]
    if selected_folder not in folder_to_run:
        selected_folder = folder_order[0]

    pill_choice = st.pills(
        "Switch run",
        options=folder_order,
        format_func=_pill_label,
        default=selected_folder,
        selection_mode="single",
        label_visibility="collapsed",
        key="run_pills",
    )
    # Use pill_choice directly — no extra st.rerun() needed since pill
    # interaction already triggers a rerun via Streamlit's widget cycle.
    selected_folder = pill_choice or selected_folder
    st.session_state["selected_run"] = selected_folder

    run = folder_to_run[selected_folder]
    decision = extract_decision(run)

    # --- Hero card ---
    hero_cols = st.columns([5, 3])
    with hero_cols[0]:
        st.markdown(
            f'<div class="hero-card">'
            f'<div class="ticker">{run.ticker}</div>'
            f'<div class="meta">Generated {run.timestamp.strftime("%A, %B %d, %Y · %H:%M:%S")}</div>'
            f'<div class="meta"><code style="font-size:0.75rem;">{run.folder_name}</code></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with hero_cols[1]:
        st.markdown(
            f'<div class="hero-card" style="text-align:center; padding-top:34px;">'
            f'{decision_badge_html(decision, size="xl")}'
            f'<div class="meta" style="margin-top:14px;">Final recommendation</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # --- Section tabs ---
    # Track active tab in session state so we only render the selected tab's
    # content — avoids loading complete_report.md and all other sections on
    # every report switch.
    TAB_LABELS = ["📋 Decision", "🔬 Analysts", "🐂🐻 Research", "💼 Trading", "⚖️ Risk", "📄 Full Report"]
    TAB_RENDERERS = [
        _render_section_portfolio,
        _render_section_analysts,
        _render_section_research,
        _render_section_trading,
        _render_section_risk,
        _render_section_full,
    ]
    section_tabs = st.tabs(TAB_LABELS)
    for tab, renderer in zip(section_tabs, TAB_RENDERERS, strict=True):
        with tab:
            renderer(run)

    # --- History (collapsible toggle bar at the bottom) ---
    st.write("")
    with st.expander(f"🗂️  History — all {len(runs)} run{'s' if len(runs) != 1 else ''}", expanded=False):
        tickers = sorted({r.ticker for r in runs})
        ticker_filter = st.selectbox(
            "Filter by ticker",
            options=["All tickers"] + tickers,
            index=0,
            key="history_filter",
        )
        filtered = [
            r for r in runs
            if ticker_filter == "All tickers" or r.ticker == ticker_filter
        ]
        for r in filtered:
            d = extract_decision(r)
            row = st.columns([3, 4, 2, 2])
            with row[0]:
                st.markdown(
                    f'<div class="hist-card"><span class="ticker">{r.ticker}</span></div>',
                    unsafe_allow_html=True,
                )
            with row[1]:
                st.markdown(
                    f'<div class="hist-card"><span class="meta">'
                    f'{r.timestamp.strftime("%Y-%m-%d %H:%M:%S")}</span></div>',
                    unsafe_allow_html=True,
                )
            with row[2]:
                st.markdown(
                    f'<div class="hist-card" style="text-align:center;">{decision_badge_html(d)}</div>',
                    unsafe_allow_html=True,
                )
            with row[3]:
                is_current = r.folder_name == selected_folder
                if st.button(
                    "● Current" if is_current else "View →",
                    key=f"hist_view_{r.folder_name}",
                    use_container_width=True,
                    disabled=is_current,
                ):
                    st.session_state["selected_run"] = r.folder_name
                    st.rerun()


# ---------------------------------------------------------------------------
# CLI-mirrored option sources
# ---------------------------------------------------------------------------

# Same depth tiers as `cli/utils.py::select_research_depth`.
DEPTH_OPTIONS = [
    ("Shallow — quick research, 1 debate round", 1),
    ("Medium — moderate debate and discussion (3 rounds)", 3),
    ("Deep — comprehensive, 5 rounds of debate", 5),
]

# Same analyst order as `cli/utils.py::ANALYST_ORDER`. Internal value matches
# the AnalystType string the graph expects.
ANALYST_OPTIONS = [
    ("Market Analyst", "market"),
    ("Sentiment Analyst", "social"),
    ("News Analyst", "news"),
    ("Fundamentals Analyst", "fundamentals"),
]

OUTPUT_LANGUAGES = [
    "English", "Chinese", "Japanese", "Korean", "Hindi", "Spanish",
    "Portuguese", "French", "German", "Arabic", "Russian",
]


# Mirrors cli/utils.py::_llm_provider_table(). Kept here so the UI does not
# depend on `cli.utils` (which imports questionary, a TUI-only dependency).
def _load_provider_table() -> list[tuple[str, str, str | None]]:
    """(display, provider_key, default_url) for every supported provider."""
    import os as _os
    ollama_url = _os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434/v1"
    return [
        ("OpenAI", "openai", "https://api.openai.com/v1"),
        ("Google", "google", None),
        ("Anthropic", "anthropic", "https://api.anthropic.com/"),
        ("xAI", "xai", "https://api.x.ai/v1"),
        ("DeepSeek", "deepseek", "https://api.deepseek.com"),
        ("Qwen", "qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        ("GLM", "glm", "https://open.bigmodel.cn/api/paas/v4/"),
        ("MiniMax", "minimax", "https://api.minimax.io/v1"),
        ("OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
        ("Mistral", "mistral", "https://api.mistral.ai/v1"),
        ("Kimi (Moonshot)", "kimi", "https://api.moonshot.ai/v1"),
        ("Groq", "groq", "https://api.groq.com/openai/v1"),
        ("NVIDIA NIM", "nvidia", "https://integrate.api.nvidia.com/v1"),
        ("Azure OpenAI", "azure", None),
        ("Amazon Bedrock", "bedrock", None),
        ("Ollama", "ollama", ollama_url),
        ("OpenAI-compatible (vLLM, LM Studio, llama.cpp, custom relay)", "openai_compatible", None),
    ]


@st.cache_data(show_spinner=False)
def _load_model_options(provider: str, mode: str) -> list[tuple[str, str]]:
    """(display, model_id) for a provider+mode. Empty list if catalog is missing."""
    try:
        from tradingagents.llm_clients.model_catalog import get_model_options
        return get_model_options(provider, mode)
    except Exception:
        return []


@st.cache_data(show_spinner=False)
def _api_key_env(provider: str) -> str | None:
    try:
        from tradingagents.llm_clients.api_key_env import get_api_key_env
        return get_api_key_env(provider)
    except Exception:
        return None


def _save_api_key(env_var: str, value: str) -> Path:
    """Persist an API key to project .env and the running process environment."""
    import os as _os

    from dotenv import find_dotenv, set_key
    env_path = find_dotenv(usecwd=True) or str(PROJECT_DIR / ".env")
    Path(env_path).touch(exist_ok=True)
    set_key(env_path, env_var, value)
    _os.environ[env_var] = value
    return Path(env_path)


def _is_valid_ticker(value: str) -> bool:
    v = value.strip()
    return bool(v) and all(ch.isalnum() or ch in "._-^=" for ch in v) and len(v) <= 32


def _normalize_ticker(ticker: str) -> str:
    try:
        from tradingagents.dataflows.symbol_utils import normalize_symbol
        return normalize_symbol(ticker)
    except Exception:
        return ticker.strip().upper()


def _detect_asset_type(ticker: str) -> str:
    canonical = _normalize_ticker(ticker)
    if canonical.endswith(("-USD", "-USDT", "-USDC", "-BTC", "-ETH")):
        return "crypto"
    return "stock"


# ---------------------------------------------------------------------------
# Run page
# ---------------------------------------------------------------------------

def page_run() -> None:
    st.title("Run Analysis")
    st.caption("Same selections as the CLI: ticker, analysts, depth, provider, and models.")

    providers = _load_provider_table()
    provider_displays = [d for d, _, _ in providers]
    provider_keys = [k for _, k, _ in providers]

    # --- Ticker & date ---
    c1, c2 = st.columns([3, 2])
    with c1:
        ticker_raw = st.text_input(
            "Ticker symbol",
            value=st.session_state.get("run_ticker", "SPY"),
            help="e.g. NVDA, AAPL, 0700.HK, BTC-USD, GC=F",
            key="run_ticker",
        )
    with c2:
        trade_date = st.date_input(
            "Analysis date",
            value=st.session_state.get("run_date", date.today()),
            max_value=date.today(),
            key="run_date",
        )

    ticker = ticker_raw.strip().upper() if ticker_raw else ""
    if ticker and not _is_valid_ticker(ticker):
        st.error("Invalid ticker — use letters, digits, and `. _ - ^ =` only.")
        return

    asset_type = _detect_asset_type(ticker) if ticker else "stock"
    if ticker:
        canonical = _normalize_ticker(ticker)
        st.caption(
            f"→ Resolved: **{canonical}** · Type: **{asset_type}**"
            + (" · _fundamentals analyst disabled for crypto_" if asset_type == "crypto" else "")
        )

    st.divider()

    # --- Analysts ---
    st.markdown("##### Analyst team")
    available_analysts = [
        (lbl, val) for lbl, val in ANALYST_OPTIONS
        if not (asset_type == "crypto" and val == "fundamentals")
    ]
    default_selected = [lbl for lbl, _ in available_analysts]
    analyst_labels = st.multiselect(
        "Pick which analysts to include",
        options=[lbl for lbl, _ in available_analysts],
        default=default_selected,
        label_visibility="collapsed",
    )
    label_to_value = dict(available_analysts)
    selected_analysts = [label_to_value[lbl] for lbl in analyst_labels]

    # --- Research depth ---
    st.markdown("##### Research depth")
    depth_label = st.radio(
        "Research depth",
        options=[lbl for lbl, _ in DEPTH_OPTIONS],
        index=0,
        label_visibility="collapsed",
        horizontal=False,
    )
    depth_value = dict(DEPTH_OPTIONS)[depth_label]

    st.divider()

    # --- LLM Provider & Models ---
    st.markdown("##### LLM provider & models")
    st.caption(
        "💡 **Free option:** pick **Ollama** to run models locally — no API key required. "
        "You'll need [ollama.com](https://ollama.com) installed and a model pulled "
        "(e.g. `ollama pull qwen3`)."
    )

    # Respect TRADINGAGENTS_LLM_PROVIDER when set (e.g. "ollama" in .env),
    # then fall back to Ollama when OPENAI_API_KEY is absent, else OpenAI.
    import os as _os
    _env_provider = (_os.environ.get("TRADINGAGENTS_LLM_PROVIDER") or "").strip().lower()
    default_provider = _env_provider if _env_provider in provider_keys else (
        "google" if _os.environ.get("GOOGLE_API_KEY") else
        "groq" if _os.environ.get("GROQ_API_KEY") else
        "openai" if _os.environ.get("OPENAI_API_KEY") else "ollama"
    )
    default_idx = provider_keys.index(default_provider) if default_provider in provider_keys else 0

    pc1, pc2 = st.columns([2, 3])
    with pc1:
        provider_display = st.selectbox(
            "Provider",
            options=provider_displays,
            index=default_idx,
        )
        provider_key = provider_keys[provider_displays.index(provider_display)]
        default_url = providers[provider_displays.index(provider_display)][2]

    with pc2:
        # Use a provider-scoped key so switching providers gives Streamlit a
        # NEW widget with the new default URL, instead of retaining the
        # previous provider's value (e.g. Ollama's localhost URL sticking
        # around after the user picks Groq).
        backend_url_key = f"backend_url_{provider_key}"

        # Cloudflare quick tunnels (*.trycloudflare.com) expire within hours.
        # If session state still holds one, auto-heal back to the env default
        # so the UI never opens to a dead URL.
        if default_url and "trycloudflare.com" in (st.session_state.get(backend_url_key) or ""):
            st.session_state[backend_url_key] = default_url

        # Some providers (Google, Azure, Bedrock) use SDK-managed endpoints, so
        # there's nothing to type. Show a placeholder so the empty field reads
        # as intentional rather than broken.
        if default_url is None:
            backend_url = st.text_input(
                "Backend URL",
                value="",
                placeholder=f"(not used — {provider_display} uses its SDK's built-in endpoint)",
                help=f"{provider_display} doesn't use a configurable base URL. Leave this blank.",
                disabled=True,
                key=backend_url_key,
            )
        else:
            backend_url = st.text_input(
                "Backend URL",
                value=default_url,
                help="Leave default unless using a custom relay / self-hosted endpoint.",
                key=backend_url_key,
            )

    # Ollama-specific helper: ping the server + list installed models, then
    # probe each model's capabilities so we only offer tool-calling models in
    # the picker. TradingAgents agents call data tools — a non-tool model will
    # fail at run time with HTTP 400 "<model> does not support tools".
    ollama_tool_models: list[str] = []
    ollama_non_tool_models: list[str] = []
    if provider_key.lower() == "ollama":
        import requests as _requests
        # OpenAI-compatible endpoint is at /v1; capabilities live on the native
        # API at /api/show, so derive the native root by stripping a trailing /v1.
        probe_url = (backend_url or default_url or "http://localhost:11434/v1").rstrip("/")
        native_root = probe_url[:-3].rstrip("/") if probe_url.endswith("/v1") else probe_url
        try:
            r = _requests.get(f"{probe_url}/models", timeout=2)
            if r.status_code == 200:
                installed = [
                    m.get("id", "")
                    for m in r.json().get("data", [])
                    if m.get("id") and "embed" not in m.get("id", "").lower()
                ]
                # Probe capabilities for each model (tools/vision/etc.)
                for name in installed:
                    try:
                        cap_resp = _requests.post(
                            f"{native_root}/api/show", json={"name": name}, timeout=3
                        )
                        caps = cap_resp.json().get("capabilities", []) if cap_resp.status_code == 200 else []
                        if "tools" in caps:
                            ollama_tool_models.append(name)
                        else:
                            ollama_non_tool_models.append(name)
                    except Exception:
                        ollama_non_tool_models.append(name)

                if ollama_tool_models:
                    st.success(
                        f"✓ Ollama reachable at `{probe_url}` — "
                        f"**{len(ollama_tool_models)} tool-capable model(s)**: "
                        + ", ".join(f"`{m}`" for m in ollama_tool_models)
                    )
                    if ollama_non_tool_models:
                        st.caption(
                            "Hidden (no tool-calling support — required by the agents): "
                            + ", ".join(f"`{m}`" for m in ollama_non_tool_models)
                        )
                elif installed:
                    st.error(
                        "⚠ None of your installed Ollama models support tool calling, which the "
                        "trading agents require.\n\nYou have: "
                        + ", ".join(f"`{m}`" for m in installed)
                        + "\n\nPull a tool-capable model — recommended:\n"
                        "```bash\nollama pull qwen3        # 8B, great default\n"
                        "ollama pull llama3.1      # 8B, Meta's tool-capable Llama\n"
                        "ollama pull gpt-oss       # 20B, larger reasoning\n```"
                    )
                else:
                    st.warning(
                        f"✓ Ollama is running at `{probe_url}` but **no chat models are installed**. "
                        "Run `ollama pull qwen3` in a terminal, then refresh."
                    )
            else:
                st.error(f"Ollama responded with HTTP {r.status_code} at `{probe_url}`.")
        except Exception:
            st.error(
                f"✗ Could not reach Ollama at `{probe_url}`. "
                "Install from [ollama.com](https://ollama.com), then run `ollama serve` in a terminal."
            )

    # Model dropdowns. For Ollama, pick from tool-capable installed models so
    # the run can't fail on a tool-incompatible model. For other providers, use
    # the catalog.
    mc1, mc2 = st.columns(2)
    if provider_key.lower() == "ollama":
        if ollama_tool_models:
            ollama_opts = [(m, m) for m in ollama_tool_models] + [("Custom model ID", "custom")]
        else:
            ollama_opts = [("Custom model ID", "custom")]
        quick_options = ollama_opts
        deep_options = ollama_opts
    else:
        quick_options = _load_model_options(provider_key, "quick")
        deep_options = _load_model_options(provider_key, "deep")

    def _model_picker(col, mode_label: str, options: list[tuple[str, str]], key: str, default_model: str = "") -> str:
        with col:
            st.markdown(f"**{mode_label}**")
            if not options:
                # Provider has no catalog (e.g. azure / mistral / kimi) — free-text
                return st.text_input(f"{mode_label} model ID", value=default_model, key=key).strip()
            labels = [d for d, _ in options]
            ids = [v for _, v in options]
            # Pre-select if the env-var model is in the fetched list; fall to
            # "Custom model ID" (last entry) when it's set but not yet pulled.
            if default_model and default_model in ids:
                default_sel_idx = ids.index(default_model)
            elif default_model:
                default_sel_idx = len(labels) - 1  # "Custom model ID" sentinel
            else:
                default_sel_idx = 0
            choice = st.selectbox(mode_label, options=labels, index=default_sel_idx, label_visibility="collapsed", key=f"{key}_sel")
            model_id = dict(options)[choice]
            if model_id == "custom":
                prefill = default_model if default_model not in ids else ""
                model_id = st.text_input(f"Custom {mode_label.lower()} model ID", value=prefill, key=f"{key}_custom").strip()
            return model_id

    # Read env-var defaults so the UI pre-selects the right model on every
    # fresh load — set TRADINGAGENTS_QUICK_THINK_LLM / TRADINGAGENTS_DEEP_THINK_LLM
    # in .env once and never touch the dropdown again.
    _env_quick = (_os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM") or "").strip()
    _env_deep  = (_os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM")  or "").strip()

    # Provider-scoped keys so switching provider resets the model picker
    # (otherwise Streamlit keeps the previous provider's model text in the
    # widget, which would then be sent as the model ID for the new provider).
    quick_model = _model_picker(mc1, "Quick-thinking model", quick_options, f"quick_model_{provider_key}", default_model=_env_quick)
    deep_model = _model_picker(mc2, "Deep-thinking model", deep_options, f"deep_model_{provider_key}", default_model=_env_deep)

    # --- Provider-specific reasoning effort ---
    reasoning_effort = None
    thinking_level = None
    anthropic_effort = None
    plower = provider_key.lower()
    if plower == "openai":
        reasoning_effort = st.select_slider(
            "OpenAI reasoning effort",
            options=["low", "medium", "high"],
            value="medium",
        )
    elif plower == "google":
        thinking_level = st.selectbox(
            "Gemini thinking level",
            options=["minimal", "low", "medium", "high"],
            index=2,
        )
    elif plower == "anthropic":
        anthropic_effort = st.selectbox(
            "Claude effort level",
            options=["low", "medium", "high"],
            index=1,
        )

    # --- Output language ---
    output_language = st.selectbox("Output language", OUTPUT_LANGUAGES, index=0)

    st.divider()

    # --- API key check ---
    env_var = _api_key_env(provider_key)
    api_key_ready = True
    if env_var:
        import os as _os
        existing = _os.environ.get(env_var)
        if existing:
            st.success(f"✓ `{env_var}` is set ({len(existing)} chars).")
        else:
            st.warning(f"⚠ `{env_var}` is not set. Paste it below to save to `.env` and use this run.")
            new_key = st.text_input(
                f"{env_var}",
                value="",
                type="password",
                key=f"key_{env_var}",
            )
            if st.button(f"Save {env_var} to .env", disabled=not new_key):
                path = _save_api_key(env_var, new_key.strip())
                st.success(f"Saved to `{path}`. Re-run the run button below.")
                st.rerun()
            api_key_ready = bool(_os.environ.get(env_var))
    else:
        if provider_key.lower() == "ollama":
            st.info("🆓 Ollama runs locally — no API key required, no usage cost.")
        else:
            st.caption(f"ℹ Provider `{provider_key}` does not require an API key env var.")

    # --- Validate & launch ---
    st.divider()

    can_run = bool(
        ticker
        and selected_analysts
        and quick_model
        and deep_model
        and api_key_ready
    )
    missing = []
    if not ticker:
        missing.append("ticker")
    if not selected_analysts:
        missing.append("at least one analyst")
    if not quick_model:
        missing.append("quick-thinking model")
    if not deep_model:
        missing.append("deep-thinking model")
    if not api_key_ready:
        missing.append(f"{env_var}")

    launch_label = "▶ Run analysis" if can_run else f"Missing: {', '.join(missing)}"
    launched = st.button(launch_label, type="primary", use_container_width=True, disabled=not can_run)

    if not launched:
        with st.expander("What will run"):
            st.write({
                "ticker": ticker,
                "asset_type": asset_type,
                "analysis_date": trade_date.isoformat() if trade_date else None,
                "analysts": selected_analysts,
                "research_depth": depth_value,
                "provider": provider_key,
                "backend_url": backend_url or None,
                "quick_model": quick_model,
                "deep_model": deep_model,
                "output_language": output_language,
                **({"openai_reasoning_effort": reasoning_effort} if reasoning_effort else {}),
                **({"google_thinking_level": thinking_level} if thinking_level else {}),
                **({"anthropic_effort": anthropic_effort} if anthropic_effort else {}),
            })
        return

    # --- Execute ---
    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except ModuleNotFoundError as e:
        st.error(
            f"❌ A required Python package is missing: **`{e.name}`**.\n\n"
            "Install the project's dependencies once with:\n\n"
            "```bash\npip install -e .\n```\n"
            "(run from the project root, then refresh this page)."
        )
        return
    except Exception as e:
        # Streamlit can wrap real ImportErrors as KeyError due to its module-graph
        # hot-reload. Walk the cause chain so the underlying error is visible.
        root = e
        while root.__cause__ or root.__context__:
            root = root.__cause__ or root.__context__
            if isinstance(root, ModuleNotFoundError):
                st.error(
                    f"❌ Missing Python package: **`{root.name}`**. Run `pip install -e .` from the project root."
                )
                return
        st.error(f"Could not import TradingAgents: {type(e).__name__}: {e}")
        st.code(traceback.format_exc())
        return

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = provider_key.lower()
    config["backend_url"] = backend_url.strip() or None
    config["quick_think_llm"] = quick_model
    config["deep_think_llm"] = deep_model
    config["max_debate_rounds"] = int(depth_value)
    config["max_risk_discuss_rounds"] = int(depth_value)
    config["output_language"] = output_language
    if reasoning_effort:
        config["openai_reasoning_effort"] = reasoning_effort
    if thinking_level:
        config["google_thinking_level"] = thinking_level
    if anthropic_effort:
        config["anthropic_effort"] = anthropic_effort

    canonical_ticker = _normalize_ticker(ticker)
    save_path = REPORTS_DIR / f"{canonical_ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    with st.status(
        f"Running {canonical_ticker} on {trade_date.isoformat()}…",
        expanded=True,
    ) as status:
        st.write(
            f"Provider: `{provider_key}` · Deep: `{deep_model}` · Quick: `{quick_model}` · Depth: `{depth_value}`"
        )
        st.write(f"Analysts: {', '.join(selected_analysts)}")
        st.write("Initializing graph…")
        try:
            ta = TradingAgentsGraph(
                selected_analysts=tuple(selected_analysts),
                debug=False,
                config=config,
            )
            _AGENT_LABELS = {
                "market_analyst": "\U0001f4ca Market Analyst",
                "sentiment_analyst": "\U0001f4ac Sentiment Analyst",
                "news_analyst": "\U0001f4f0 News Analyst",
                "fundamentals_analyst": "\U0001f4c8 Fundamentals Analyst",
                "bull_researcher": "\U0001f402 Bull Researcher",
                "bear_researcher": "\U0001f43b Bear Researcher",
                "research_manager": "\U0001f52c Research Manager",
                "trader": "\U0001f4bc Trader",
                "aggressive_risk": "\U0001f525 Aggressive Risk",
                "neutral_risk": "⚖️ Neutral Risk",
                "conservative_risk": "\U0001f6e1️ Conservative Risk",
                "portfolio_manager": "\U0001f3e6 Portfolio Manager",
            }
            _progress_box = st.empty()
            _completed: list[str] = []

            def _on_agent_step(node: str) -> None:
                label = _AGENT_LABELS.get(node, f"⚙️ {node.replace('_', ' ').title()}")
                _completed.append(f"✓ {label}")
                _progress_box.markdown("  \n".join(_completed))

            st.write("Running agents — live progress below:")
            final_state, decision = ta.propagate(
                canonical_ticker,
                trade_date.isoformat(),
                asset_type=asset_type,
                progress_callback=_on_agent_step,
            )
            st.write("Writing report tree…")
            ta.save_reports(final_state, canonical_ticker, save_path=save_path)
            status.update(label=f"✓ Done — {canonical_ticker} → {decision}", state="complete", expanded=False)
        except Exception as e:
            status.update(label=f"✗ Run failed: {e}", state="error")
            st.exception(e)
            return

    st.success(f"Run complete. Final decision: **{decision}**")
    if st.button("View report on Dashboard →", type="primary"):
        st.session_state["selected_run"] = save_path.name
        st.session_state["page"] = "Dashboard"
        st.rerun()


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Trading Agents",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # Sidebar navigation
    with st.sidebar:
        st.markdown("### 📈 Trading Agents")
        st.caption("Multi-agent research")
        st.write("")

        # Two-tab layout: Run Analysis (launch) and Dashboard (browse all results).
        page = st.session_state.get("page", "Run Analysis")
        pages = ["Run Analysis", "Dashboard"]
        try:
            idx = pages.index(page)
        except ValueError:
            idx = 0
        choice = st.radio("Navigate", pages, index=idx, label_visibility="collapsed")
        st.session_state["page"] = choice

        st.write("")
        st.divider()
        runs = list_runs(str(REPORTS_DIR))
        st.caption(f"📂 `{REPORTS_DIR.relative_to(PROJECT_DIR) if REPORTS_DIR.is_relative_to(PROJECT_DIR) else REPORTS_DIR}`")
        st.caption(f"{len(runs)} run{'s' if len(runs) != 1 else ''} on disk")
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    runs = list_runs(str(REPORTS_DIR))

    if choice == "Dashboard":
        page_dashboard(runs)
    elif choice == "Run Analysis":
        page_run()


if __name__ == "__main__":
    main()
