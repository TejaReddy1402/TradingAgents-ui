# Trading Agents

A multi-agent LLM research workflow for equity and crypto markets, with a Streamlit dashboard for browsing the generated analysis.

Rather than asking a single language model "should I buy NVDA?", this project orchestrates a small team of specialised LLM agents — analysts, researchers, a trader, and risk managers — that debate the trade before a final portfolio decision is rendered. Every step of the chain is written to disk as Markdown so the reasoning is fully auditable.

---

## Why this matters

Single-shot LLM stock picks have well-known failure modes:

- **No specialisation.** One prompt is asked to handle technicals, news sentiment, fundamentals, and macro at once — none of them deeply.
- **No friction.** A confident-sounding answer is generated without anything pushing back on it, even when the underlying data is thin.
- **Opaque reasoning.** You get a recommendation but rarely the supporting data, the trade-offs, or the dissenting view.

This project addresses all three:

1. **Specialised analysts** — each focuses on one data domain (market technicals, sentiment, news, fundamentals).
2. **Structured debate** — a Bull researcher and a Bear researcher argue the case; a Research Manager picks the winner. Three Risk analysts (Aggressive / Neutral / Conservative) re-debate before the Portfolio Manager signs off.
3. **Transparent artefacts** — every agent's reasoning is saved under `reports/<TICKER>_<TIMESTAMP>/` so you can review and disagree with the chain rather than trusting a single number.

---

## How it works

The pipeline runs in five stages. Each agent has its own prompt, tool set, and output file.

```
 ┌──────────────────────────────┐
 │ 1. Analyst Team              │   Market • Sentiment • News • Fundamentals
 └──────────────┬───────────────┘
                │
 ┌──────────────▼───────────────┐
 │ 2. Research Debate           │   Bull  ⇄  Bear   →   Research Manager verdict
 └──────────────┬───────────────┘
                │
 ┌──────────────▼───────────────┐
 │ 3. Trader                    │   Concrete trade plan with entry / stop / size
 └──────────────┬───────────────┘
                │
 ┌──────────────▼───────────────┐
 │ 4. Risk Debate               │   Aggressive • Neutral • Conservative
 └──────────────┬───────────────┘
                │
 ┌──────────────▼───────────────┐
 │ 5. Portfolio Manager         │   Final BUY / HOLD / SELL recommendation
 └──────────────────────────────┘
```

Implementation notes:

- **Graph orchestration** — [LangGraph](https://github.com/langchain-ai/langgraph) defines the agent topology and routes state between stages.
- **Data sources** — yfinance, FRED, Polymarket, with optional Alpha Vantage; vendors are pluggable per category in `default_config.py`.
- **Memory** — a persistent log lets the system reflect on past trades so it can learn from prior mistakes on the same ticker.
- **Checkpointing** — an optional SQLite checkpointer lets a crashed run resume from the last completed node.

---

## What you get for each run

The output is a self-contained Markdown tree, one folder per run:

```
reports/NVDA_20260628_223455/
├── 1_analysts/
│   ├── market.md          Technical indicators, support/resistance, ATR, MACD
│   ├── sentiment.md       Reddit, StockTwits, retail mood
│   ├── news.md            Recent headlines + macro context
│   └── fundamentals.md    Valuation, growth, balance sheet
├── 2_research/
│   ├── bull.md            Long thesis with evidence
│   ├── bear.md            Short thesis with evidence
│   └── manager.md         Who won the debate and why
├── 3_trading/
│   └── trader.md          Position sizing, entry / stop / target
├── 4_risk/
│   ├── aggressive.md      "Lean in — the asymmetry is worth it"
│   ├── neutral.md         Balanced view
│   └── conservative.md    Capital-preservation perspective
├── 5_portfolio/
│   └── decision.md        Final BUY / HOLD / SELL with rationale
└── complete_report.md     Everything stitched into one document
```

---

## The Streamlit UI

Two pages, designed for fast iteration:

**Run Analysis** mirrors every CLI selection (ticker, analysts, debate depth, LLM provider, models, output language) as form fields. It live-probes your Ollama install on launch so the model picker only shows tool-capable models that are actually pulled — you cannot accidentally start a run on a model that will fail mid-flight.

**Dashboard** is a unified view with:

- A pill toggle bar of all past runs (newest first), each showing ticker, timestamp, and decision.
- A hero card with the focused run's final decision in a large colour-coded badge.
- Six section tabs — Decision · Analysts · Research · Trading · Risk · Full Report.
- A pop-out button on every section that opens the content in a floating dialog for focused reading.
- A collapsible history panel with per-ticker filtering.

---

## Quick start

### 1. Install

```bash
git clone https://github.com/<your-username>/TradingAgents-ui
cd TradingAgents-ui
pip install -e .
pip install streamlit
```

### 2. Pick a model provider

Seventeen LLM providers are supported, including OpenAI, Google, xAI, DeepSeek, Groq, OpenRouter, Azure, Bedrock, and **Ollama for fully-local free inference**.

**Free option — Ollama (local, no API key, no usage cost):**

```bash
# Install Ollama from https://ollama.com, then pull a tool-capable model:
ollama pull qwen3        # 8B, balanced default
# or
ollama pull llama3.1     # 8B
ollama pull gpt-oss      # 20B, stronger reasoning

# Keep the server running in its own terminal:
ollama serve
```

**Paid option — hosted API:** add the relevant key to `.env`:

```env
OPENAI_API_KEY=sk-...
# or any of: GOOGLE_API_KEY, XAI_API_KEY, DEEPSEEK_API_KEY, GROQ_API_KEY, ...
```

The Streamlit UI also offers a one-click "save key to .env" prompt if you'd rather not edit the file by hand.

### 3. Launch the UI

```bash
streamlit run app.py
```

Open <http://localhost:8501>, switch to **Run Analysis**, fill the form, and click **▶ Run analysis**. A Shallow-depth run on a local 8B model takes roughly 2–5 minutes; Deep-depth runs against frontier hosted models can take 15–30.

### 4. (Optional) Original CLI

The original terminal interface is still available:

```bash
tradingagents
```

It walks you through the same selections interactively.

---

## Deployment

The Streamlit UI deploys to [Streamlit Community Cloud](https://share.streamlit.io) with no code changes — point it at your repo and pick `app.py` as the entry. Two caveats to be aware of:

- **Ollama does not work in the cloud** because it runs on your local machine. For cloud-deployed instances, use a hosted API provider.
- **API keys go in the Streamlit Cloud secrets manager**, never in `.env` or committed to the repo.

---

## Architecture

```
tradingagents/
├── agents/              Each agent's prompt + tool wiring
│   ├── analysts/        market • sentiment • news • fundamentals
│   ├── researchers/     bull • bear
│   ├── managers/        research manager • portfolio manager
│   ├── trader/
│   └── risk_mgmt/       aggressive • neutral • conservative
├── graph/               LangGraph topology and node wiring
├── dataflows/           Vendor adapters (yfinance, FRED, Polymarket, …)
├── llm_clients/         Provider abstractions and model catalogue
└── reporting.py         Writes the per-run Markdown tree

cli/                     Terminal interface (Typer + Rich + Questionary)
app.py                   Streamlit UI (Run Analysis + Dashboard)
reports/                 Generated analyses, one folder per run
```

---

## Limitations and disclaimer

This project is built for **research and education**. Its output is not financial advice and the agents — like all LLM systems — can be confidently wrong. Treat each report as one input among many, validate the underlying data, and never trade beyond what you can afford to lose.

The framework deliberately surfaces a structured chain of reasoning so a human can spot where it went wrong — not so you can hand it the keys to a brokerage account.

---

## License

Apache 2.0. See `LICENSE`.
