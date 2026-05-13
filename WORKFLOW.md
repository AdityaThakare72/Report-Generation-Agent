# WORKFLOW.md — LangGraph Node Lifecycle

> Step-by-step explanation of the 5-node Suspicious Activity Report pipeline.

---

## Pipeline Overview

```
INPUT (JSON) → [Node 1] → [Node 2] → [Node 3] → [Node 4] → [Node 5] → OUTPUT (PDF)
               Validate    Impute     Aggregate   Narrate     Render
```

The pipeline uses a **LangGraph `StateGraph`** with a shared `AgentState` (TypedDict). Each node reads from the state, performs its operation, and writes back a partial state update. The graph is compiled into a single runnable object.

---

## Shared State

```python
class AgentState(TypedDict):
    raw_data: dict[str, Any]               # Original JSON payload
    cleaned_data: list[dict[str, Any]]      # Transactions after imputation
    aggregated_metrics: dict[str, Any]      # Pandas-computed summary
    narrative: str                          # LLM-generated compliance text
    final_report_path: str                  # Path to output PDF
```

---

## Node 1 — Field Mapper

**File:** `src/agent.py` → `map_fields_node()`

**Purpose:** Ingest and validate raw JSON data against Pydantic schemas.

**Process:**
1. Receives `raw_data` (loaded JSON dict) from the initial state.
2. Passes the entire payload through `TransactionBatch(**raw_data)` — Pydantic v2 validates every field, type, and constraint.
3. If validation fails, a `ValidationError` is raised with detailed field-level errors.
4. On success, serializes validated `Transaction` objects back to dicts using `model_dump(mode="json")`.
5. Logs the regulatory field mapping (`REGULATORY_FIELD_MAP`) for audit purposes.

**State Update:**
```python
{"cleaned_data": [list of validated transaction dicts]}
```

**Key Design Decision:** Pydantic validation at the boundary ensures that all downstream nodes can trust the data shape. The `REGULATORY_FIELD_MAP` dict translates internal names (e.g., `transaction_id`) to regulatory names (e.g., `STR Reference Number`).

---

## Node 2 — Missing Data Handler

**File:** `src/tools.py` → `handle_missing_data()` (called by `handle_missing_node()`)

**Purpose:** Identify and impute missing fields with conservative regulatory defaults.

**Imputation Rules:**

| Field | Default | Rationale |
|-------|---------|-----------|
| `risk_score` | `50.0` | Mid-range triggers "Medium" classification |
| `risk_level` | `"Medium"` | Conservative assumption per RBI guidelines |
| `kyc_status` | `"Pending"` | Must be flagged for compliance follow-up |
| `counterparty_name` | `"UNKNOWN"` | Preserves record integrity |

**Process:**
1. Iterates through each transaction dict.
2. Checks for `None` values in critical fields.
3. Applies default values and logs each imputation with the transaction ID.
4. Returns the fully cleaned list.

**State Update:**
```python
{"cleaned_data": [list of imputed transaction dicts]}
```

**Key Design Decision:** Missing data is logged as warnings (not silently filled) to maintain an audit trail. The compliance team can review exactly which defaults were applied.

---

## Node 3 — Aggregator

**File:** `src/tools.py` → `aggregate_metrics()` (called by `aggregate_node()`)

**Purpose:** Compute summary statistics using Pandas — **no LLM involved**.

**Computed Metrics:**

| Metric | Method |
|--------|--------|
| `total_transactions` | `len(df)` |
| `flagged_count` | `df["is_flagged"].sum()` |
| `flagged_percentage` | `flagged / total × 100` |
| `pep_count` | `df["is_pep"].sum()` |
| `total_volume` | `df["amount"].sum()` |
| `avg_transaction` | `df["amount"].mean()` |
| `max_transaction` | `df["amount"].max()` |
| `flagged_volume` | Volume of flagged transactions only |
| `risk_distribution` | `value_counts()` on `risk_level` |
| `txn_type_breakdown` | `value_counts()` on `transaction_type` |
| `kyc_breakdown` | `value_counts()` on `kyc_status` |
| `top_flag_reasons` | Top 5 flag reasons by frequency |

**State Update:**
```python
{"aggregated_metrics": {dict of computed metrics}}
```

**Key Design Decision:** Using Pandas for math (not the LLM) ensures deterministic, reproducible results. The LLM is only used for narrative generation, never for computation.

---

## Node 4 — LLM Narrative Generator

**File:** `src/agent.py` → `generate_narrative_node()`

**Purpose:** Use Google Gemini to generate a 2–3 paragraph compliance narrative.

**Process:**
1. Serializes `aggregated_metrics` to formatted JSON.
2. Injects the metrics into a carefully crafted prompt that instructs the LLM to:
   - Use formal regulatory language (RBI/SEBI context)
   - Reference specific frameworks (PMLA, KYC Master Direction)
   - Highlight key risk indicators
   - Recommend next steps (EDD, STR filing, monitoring)
   - Stay within 250–350 words
   - **Never fabricate numbers**
3. Calls `ChatGoogleGenerativeAI(model="gemini-2.5-flash")` with `temperature=0.3` for controlled output.
4. Extracts the text response.

**State Update:**
```python
{"narrative": "The compliance review of the analysed..."}
```

**Key Design Decision:** Temperature 0.3 balances professionalism with slight variation. The prompt explicitly forbids number fabrication — the LLM should only reference metrics from the JSON.

---

## Node 5 — Report Generator

**File:** `src/tools.py` → `generate_pdf()` (called by `generate_report_node()`)

**Purpose:** Render the final SAR as a professionally styled PDF.

**Process:**
1. Loads the Jinja2 HTML template from `src/templates/report_template.html`.
2. Injects template variables:
   - `report_id`, `generated_at` — Header metadata
   - `metrics` — All aggregated values for the summary cards
   - `narrative` — LLM-generated text
   - `flagged_transactions` — Filtered list for the detail table
3. Renders HTML string via Jinja2.
4. Passes HTML to WeasyPrint for PDF conversion (A4 format with headers/footers).
5. Saves to `output/{report_id}.pdf`.

**State Update:**
```python
{"final_report_path": "/absolute/path/to/output/SAR-20260513-001.pdf"}
```

**Key Design Decision:** HTML → PDF (via WeasyPrint) allows full CSS styling control. The template uses CSS Grid for metric cards and proper `@page` rules for print layout.

---

## Error Handling

| Error | Node | Behaviour |
|-------|------|-----------|
| Invalid JSON schema | Node 1 | `pydantic.ValidationError` with field-level details |
| Missing system libraries | Node 5 | `RuntimeError` with OS-specific install instructions |
| Gemini API failure | Node 4 | LangChain exception propagated to caller |
| Empty transaction list | Node 1 | Pydantic `min_length=1` constraint rejects it |

---

## Running the Pipeline

```bash
# 1. Generate test data
python -m src.data_generator

# 2. Run the full pipeline
python main.py

# 3. Check the output
ls -la output/
```
