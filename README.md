# TradingAgents UI
### Multi-Agent LLM Financial Trading Framework with Streamlit Dashboard

A multi-agent LLM research workflow for equity and crypto markets. Rather than asking a single model "should I buy NVDA?", this project orchestrates a team of specialised agents — analysts, researchers, a trader, and risk managers — that debate the trade before a final portfolio decision is rendered.

> This project is built on top of the open-source [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) framework, extended with a Streamlit UI and cloud deployment support.

---

## How It Works

```
┌──────────────────────────────┐
│ 1. Analyst Team              │   Market · Sentiment · News · Fundamentals
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│ 2. Research Debate           │   Bull ⇄ Bear  →  Research Manager verdict
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│ 3. Trader                    │   Entry / stop / position size
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│ 4. Risk Debate               │   Aggressive · Neutral · Conservative
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│ 5. Portfolio Manager         │   Final BUY / HOLD / SELL
└──────────────────────────────┘
```

Built with **LangGraph** for orchestration, **yfinance / FRED / Polymarket** for data, and a **Streamlit** dashboard for the UI.

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/TejaReddy1402/TradingAgents-ui.git
cd TradingAgents-ui
pip install -e .
pip install streamlit
```

### 2. Set an API Key

The recommended free option is **Google Gemini**:

```bash
# Get a free key at https://aistudio.google.com/apikey
export GOOGLE_API_KEY=your-key-here
```

Or use any other supported provider:

```bash
export OPENAI_API_KEY=...
export GROQ_API_KEY=...          # free tier, limited TPM
export ANTHROPIC_API_KEY=...
export XAI_API_KEY=...
export DEEPSEEK_API_KEY=...
export OPENROUTER_API_KEY=...
```

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

### 3. Launch the UI

```bash
streamlit run app.py
```

Open `http://localhost:8501`, pick a ticker, choose **Google** as provider with **Gemini 2.5 Flash**, and click **Run analysis**.

---

## Streamlit UI

Two pages:

**Run Analysis** — mirrors every CLI option as form fields: ticker, analyst team, debate depth, LLM provider, models, output language. Validates the provider connection before allowing a run.

**Dashboard** — browses all past runs with a pill toggle bar, colour-coded BUY/HOLD/SELL badge, six section tabs (Decision · Analysts · Research · Trading · Risk · Full Report), and a collapsible history panel.

---

## Supported LLM Providers

| Provider | Free Tier | Notes |
|---|---|---|
| Google Gemini | Yes (1M TPM) | Recommended default |
| Groq | Yes (12K TPM) | Too low for multi-agent use |
| OpenAI | No | Most capable |
| Anthropic | No | Claude models |
| xAI | No | Grok models |
| DeepSeek | Cheap | Strong reasoning |
| Ollama | Free (local) | No cloud needed |
| OpenRouter | Varies | Access to many models |

---

## Cloud Deployment (Streamlit Community Cloud)

1. Fork this repo and push to GitHub
2. Deploy at [share.streamlit.io](https://share.streamlit.io) — pick `app.py` as the main file
3. In **Settings → Secrets**, add your API key:
   ```toml
   GOOGLE_API_KEY = "your-key-here"
   ```
4. Deploy — the app auto-detects the key and defaults to Google

---

## Report Structure

Each run produces a self-contained Markdown folder:

```
reports/TSLA_20260707_143022/
├── 1_analysts/
│   ├── market.md          Technical indicators, support/resistance
│   ├── sentiment.md       Reddit, StockTwits mood
│   ├── news.md            Headlines + macro context
│   └── fundamentals.md    Valuation, growth, balance sheet
├── 2_research/
│   ├── bull.md            Long thesis
│   ├── bear.md            Short thesis
│   └── manager.md         Debate verdict
├── 3_trading/
│   └── trader.md          Entry / stop / target
├── 4_risk/
│   ├── aggressive.md
│   ├── neutral.md
│   └── conservative.md
├── 5_portfolio/
│   └── decision.md        Final BUY / HOLD / SELL
└── complete_report.md     Full stitched report
```

---

## Markets & Tickers

Works with any market Yahoo Finance covers:

- US: `AAPL`, `TSLA`, `SPY`
- Hong Kong: `0700.HK` · Tokyo: `7203.T` · London: `AZN.L`
- India: `RELIANCE.NS` · Canada: `.TO` · Australia: `.AX`
- Crypto: `BTC-USD`, `ETH-USD`

---

## Python Usage

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"
config["deep_think_llm"] = "gemini-2.5-flash"
config["quick_think_llm"] = "gemini-2.5-flash"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("TSLA", "2026-07-07")
print(decision)
```

---

## Disclaimer

This project is for research and education only. Output is not financial advice. LLM agents can be confidently wrong — treat each report as one input among many and never trade beyond what you can afford to lose.
