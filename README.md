# AI Compliance Monitoring — Report Drafting Agent

> An AI-powered agent that generates **Suspicious Activity Reports (SAR)** for financial services compliance, built with **LangGraph**, **Google Gemini**, and **WeasyPrint**.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                     │
│                                                             │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│   │  Node 1  │───▶│  Node 2  │───▶│  Node 3  │             │
│   │  Field   │    │  Missing  │    │  Aggre-  │             │
│   │  Mapper  │    │  Data     │    │  gator   │             │
│   │ (Pydantic│    │  Handler  │    │ (Pandas) │             │
│   │  Valid.) │    │           │    │          │             │
│   └──────────┘    └──────────┘    └──────────┘             │
│                                        │                    │
│                                        ▼                    │
│                   ┌──────────┐    ┌──────────┐             │
│                   │  Node 5  │◀───│  Node 4  │             │
│                   │  Report  │    │  LLM     │             │
│                   │  Gen     │    │  Narrat. │             │
│                   │(WeasyPr.)│    │ (Gemini) │             │
│                   └──────────┘    └──────────┘             │
│                        │                                    │
│                        ▼                                    │
│                   📄 SAR PDF                                │
└─────────────────────────────────────────────────────────────┘
```

| Node | Role | Technology |
|------|------|-----------|
| **1 — Field Mapper** | Validates JSON input via Pydantic, maps fields to regulatory names | `pydantic` |
| **2 — Missing Data Handler** | Imputes missing `risk_score`, `kyc_status` with conservative defaults | Pure Python |
| **3 — Aggregator** | Computes summary metrics (volume, flagged count, risk distribution) | `pandas` |
| **4 — LLM Narrative** | Generates a compliance narrative from aggregated metrics | `langchain-google-genai` (Gemini) |
| **5 — Report Generator** | Renders final SAR as a styled PDF | `jinja2` + `weasyprint` |

---

## 📋 Prerequisites

### System Libraries (WeasyPrint dependency)

WeasyPrint requires native libraries for PDF rendering:

**Arch Linux:**
```bash
sudo pacman -S pango cairo gdk-pixbuf2 libffi weasyprint
```

**Ubuntu / Debian:**
```bash
sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev
```

**macOS:**
```bash
brew install pango cairo libffi gdk-pixbuf
```

### Python

- Python **3.11+** required
- A **Google Gemini API Key** ([get one here](https://aistudio.google.com/app/apikey))

---

## 🚀 Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/AdityaThakare72/Report-Generation-Agent.git
cd Report-Generation-Agent

# Run the automated setup script
chmod +x setup.sh
./setup.sh

# Activate the virtual environment
source venv/bin/activate
```

### 2. Configure API Key

```bash
cp .env.example .env
# Edit .env and add your Gemini API key
```

### 3. Generate Sample Data

```bash
python -m src.data_generator
```

This creates `data/sample_transactions.json` with 50 realistic transactions.

### 4. Run the Agent

```bash
python main.py
```

The pipeline executes all 5 nodes and outputs a PDF to `output/SAR-XXXXXXXX-001.pdf`.

---

## 📂 Project Structure

```
report-gen-agent/
├── main.py                          # Entry point
├── setup.sh                         # Environment bootstrap
├── requirements.txt                 # Python dependencies
├── .env.example                     # API key template
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── models.py                    # Pydantic schemas & field mappings
│   ├── data_generator.py            # Synthetic data fabricator (50 rows)
│   ├── tools.py                     # Business logic (aggregation, imputation, PDF)
│   ├── agent.py                     # LangGraph StateGraph (5 nodes)
│   └── templates/
│       └── report_template.html     # Jinja2 SAR template
│
├── data/
│   └── sample_transactions.json     # Generated test data
│
├── output/                          # Generated PDF reports (gitignored)
│
├── README.md
└── WORKFLOW.md                      # Detailed node lifecycle docs
```

---

## 🔧 Tech Stack

| Component | Library | Purpose |
|-----------|---------|---------|
| Orchestration | `langgraph` | StateGraph with TypedDict |
| LLM | `langchain-google-genai` | Gemini API integration |
| Validation | `pydantic` v2 | Input schema enforcement |
| Data Processing | `pandas` | Metric aggregation |
| Templating | `jinja2` | HTML report template |
| PDF Rendering | `weasyprint` | HTML → PDF conversion |
| Secrets | `python-dotenv` | Environment variable management |

---

## 📊 Sample Output

The generated SAR PDF includes:
- **Executive Summary** — Key metrics in a card layout
- **Risk & KYC Analysis** — Distribution breakdown tables
- **Compliance Narrative** — AI-generated regulatory summary
- **Flagged Transaction Details** — Full table of suspicious activities

---

## 📜 Regulatory Context

This agent is designed for compliance with:
- **RBI Master Direction** — Know Your Customer (KYC) Norms
- **SEBI Circular** — Anti-Money Laundering / Combating Financing of Terrorism
- **PMLA 2002** — Prevention of Money Laundering Act
- **FATF Recommendations** — Suspicious Transaction Reporting

---

## 📄 License

This project is created for educational / interview demonstration purposes.
