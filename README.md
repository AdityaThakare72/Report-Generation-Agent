# Report Drafting Agent — AI Compliance Monitoring

Automated Suspicious Activity Report (SAR) generation for financial services compliance (RBI/SEBI context), built on LangGraph, Google Gemini, and WeasyPrint.

---

## Architecture

```
INPUT (JSON)
  |
  v
[Field Mapper] -> [Missing Data Handler] -> [Aggregator] -> [Narrative Gen] -> [Report Gen]
  Pydantic          default imputation       Pandas          Gemini LLM        Jinja2 + PDF
  validation        + audit logging          metrics         (2-3 para)        WeasyPrint
                                                                                  |
                                                                                  v
                                                                            SAR PDF output
```

| Node | Responsibility | Tech |
|------|---------------|------|
| Field Mapper | Validate JSON input, map to regulatory field names | Pydantic v2 |
| Missing Data Handler | Impute gaps with conservative defaults, log each change | Pure Python |
| Aggregator | Compute volume, flag counts, risk distribution | Pandas |
| Narrative Generator | Draft compliance narrative from metrics | Gemini (langchain-google-genai) |
| Report Generator | Render styled PDF from HTML template | Jinja2 + WeasyPrint |

---

## Prerequisites

### System libraries (WeasyPrint)

WeasyPrint requires native rendering libraries. Install them for your OS:

```bash
# Arch Linux
sudo pacman -S pango cairo gdk-pixbuf2 libffi weasyprint

# Ubuntu / Debian
sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev

# macOS
brew install pango cairo libffi gdk-pixbuf
```

### Python

- Python 3.11+
- A Google Gemini API key — [obtain one here](https://aistudio.google.com/app/apikey)

---

## Setup

```bash
git clone https://github.com/AdityaThakare72/Report-Generation-Agent.git
cd Report-Generation-Agent

chmod +x setup.sh
./setup.sh
source venv/bin/activate

cp .env.example .env
# edit .env and set GOOGLE_API_KEY
```

---

## Usage

Generate sample data (50 synthetic transactions):

```bash
python -m src.data_generator
```

Run the pipeline:

```bash
python main.py
```

Output lands in `output/SAR-XXXXXXXX-001.pdf`.

A custom input file can be passed as an argument:

```bash
python main.py path/to/transactions.json
```

---

## Project structure

```
├── main.py                       # Entry point
├── setup.sh                      # venv + pip install
├── requirements.txt
├── .env.example
├── src/
│   ├── models.py                 # Pydantic schemas, field mappings
│   ├── data_generator.py         # Synthetic test data (50 rows)
│   ├── tools.py                  # Aggregation, imputation, PDF rendering
│   ├── agent.py                  # LangGraph StateGraph (5 nodes)
│   └── templates/
│       └── report_template.html  # Jinja2 SAR template
├── data/
│   └── sample_transactions.json
├── output/                       # Generated PDFs (gitignored)
├── WORKFLOW.md                   # Node-by-node lifecycle docs
└── README.md
```

---

## Dependencies

| Library | Role |
|---------|------|
| `langgraph` | StateGraph orchestration |
| `langchain-google-genai` | Gemini API integration |
| `pydantic` v2 | Input validation |
| `pandas` | Metric computation |
| `jinja2` | HTML templating |
| `weasyprint` | PDF rendering |
| `python-dotenv` | Environment variable loading |

---

## Report contents

The generated SAR PDF includes:

- Executive summary with key metric cards
- Risk distribution and KYC status breakdowns
- LLM-drafted compliance narrative (RBI/SEBI regulatory language)
- Detailed table of flagged transactions

---

## Regulatory context

Designed around the reporting requirements of:

- RBI Master Direction on KYC Norms
- SEBI AML/CFT Circular
- Prevention of Money Laundering Act (PMLA), 2002
- FATF Suspicious Transaction Reporting guidelines

---

## License

Built for educational and interview demonstration purposes.
