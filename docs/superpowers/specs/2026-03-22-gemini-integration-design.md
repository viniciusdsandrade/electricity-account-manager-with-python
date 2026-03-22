# Gemini Integration Design

## Summary

Add Gemini AI (`gemini-3-flash-preview`) to the electricity account manager for two purposes:

1. **PDF parsing** — replace regex-based bill parsing with AI-powered extraction
2. **Insights generation** — produce natural language analysis of energy data

## Decisions

| Decision                | Choice                                                               |
|-------------------------|----------------------------------------------------------------------|
| Gemini role for parsing | Primary parser (not fallback)                                        |
| Fallback on API failure | Regex fallback for parsing; skip insights with warning               |
| Insights on terminal    | Short summary (2-3 sentences)                                        |
| Insights on PDF         | Detailed analysis (full paragraph)                                   |
| API key config          | CLI arg `--gemini-api-key` with fallback to `GEMINI_API_KEY` env var |
| API key missing         | Graceful degradation — regex parsing + no insights + warning         |
| Architecture            | Single module `src/ai/gemini.py` (no abstraction layer)              |

## Architecture

### New files

```
src/ai/
├── __init__.py          # empty
└── gemini.py            # parse_bill_text() + generate_insights()
```

### Modified files

| File                              | Changes                                                                    |
|-----------------------------------|----------------------------------------------------------------------------|
| `cli.py`                          | Add `--gemini-api-key` arg, load `.env`, call insights, pass to PDF writer |
| `config.py`                       | Add `GeminiConfig` dataclass                                               |
| `src/parsers/cpfl_pdf.py`         | Keep `extract_text()`, regex parsing stays as fallback inside `gemini.py`  |
| `src/report/pdf_writer.py`        | Add "Analise Inteligente" section, new `insights_text` param               |
| `src/usecases/generate_report.py` | Use `gemini.parse_bill_text()` instead of `CpflPdfParser.parse_bill_pdf()` |
| `requirements.txt`                | Add `google-genai`, `python-dotenv`                                        |
| `.gitignore`                      | `.env` already added                                                       |

### Flow

```
PDF da fatura
    |
    v
cpfl_pdf.extract_text()        <- pdfplumber extracts raw text
    |
    v
gemini.parse_bill_text(text)   <- Gemini interprets -> BillRecord
    |                              (on failure -> regex fallback)
    v
generate_report.py             <- merge solar + bill -> DataFrame
    |
    v
gemini.generate_insights(df)   <- Gemini generates analysis
    |                              (on failure -> skip with warning)
    v
Output: terminal (short summary) + PDF (detailed analysis)
```

## Module: `src/ai/gemini.py`

Imports `BillRecord` and `CpflPdfParser` from `src.parsers.cpfl_pdf`.

### `parse_bill_text(text: str, source_pdf: str, config: GeminiConfig) -> BillRecord`

- Sends extracted PDF text to Gemini with a prompt requesting structured JSON:
  `{"month": "YYYY-MM", "consumption_kwh": int, "injected_kwh": int}`
- Parses JSON response into a `BillRecord(month, consumption_kwh, injected_kwh, source_pdf)`
- On failure (API error, invalid JSON, no API key): falls back to full regex path:
    1. `CpflPdfParser.parse_reference_month(text)` to get `ref_month`
    2. `CpflPdfParser.parse_consumed_injected(text, ref_month)` to get values
    3. Constructs `BillRecord` from regex results
    4. Emits `warnings.warn()` with failure reason

### `generate_insights(df: DataFrame, config: GeminiConfig, detailed: bool = False) -> str`

- Receives the full report DataFrame (columns: `month`, `production_kwh`, `consumption_kwh`,
  `injected_kwh`, `saldo_kwh`, `kwh_compensados`, `kwh_excedente`, `kwh_deficit`,
  `r_por_kwh`, `economia_imediata_r$`, `credito_equivalente_r$`, `prejuizo_equivalente_r$`,
  `saldo_financeiro_r$`)
- Converts DataFrame to string representation and sends to Gemini with context prompt
- `detailed=False`: short summary (2-3 sentences) for terminal
- `detailed=True`: full analysis with comparisons and recommendations for PDF
- On failure (API error, no API key): returns empty string and emits `warnings.warn()`

## Orchestration in `generate_report.py`

Current `_read_all_bills_monthly()` calls `CpflPdfParser.parse_bill_pdf(p)` directly.

New flow:

```python
for p in bill_pdfs:
    text = CpflPdfParser.extract_text(p)
    record = parse_bill_text(text, source_pdf=p.name, config=gemini_config)
    records.append(record)
```

`generate_monthly_report()` receives `GeminiConfig` as a new parameter.

## CLI integration (`cli.py`)

### Arguments

New arg: `--gemini-api-key` (optional string)

### Config plumbing

`parse_args()` returns `tuple[PathsConfig, EconomicConfig, GeminiConfig]`.

`GeminiConfig.api_key` resolved as: CLI arg > `os.environ["GEMINI_API_KEY"]` > `None`.
When `api_key is None`, the tool runs in regex-only mode with a warning.

### Output flow

1. Generate report DataFrame (existing)
2. Call `generate_insights(df, config, detailed=False)` → print short summary to terminal
3. Call `generate_insights(df, config, detailed=True)` → pass to PDF writer
4. Print DataFrame table (existing)
5. Save CSV + PDF (existing)

## PDF writer changes

`PdfReportWriter.write()` gains a new optional parameter:

```python
def write(self, report_df, out_pdf, title, insights_text: str = "") -> None:
```

When `insights_text` is non-empty, renders a new section **"Analise Inteligente"** after the
summary table, using reportlab `Paragraph` with the existing document style.

## Config: `GeminiConfig`

```python
@dataclass(frozen=True)
class GeminiConfig:
    api_key: str | None = None
    model: str = "gemini-3-flash-preview"
```

Note: `api_key` is `None` by default — allows graceful degradation when unconfigured.

## Error handling

| Scenario                 | Behavior                                                          |
|--------------------------|-------------------------------------------------------------------|
| API key missing          | Warning + regex-only parsing + no insights (graceful degradation) |
| AI parsing failure       | Warning on terminal + regex fallback from `cpfl_pdf.py`           |
| Insights failure         | Warning on terminal + report generated without analysis section   |
| Invalid JSON from Gemini | Treated as parsing failure -> regex fallback                      |

## Dependencies

```
google-genai
python-dotenv
```
