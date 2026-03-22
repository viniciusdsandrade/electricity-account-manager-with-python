# Gemini Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:
> executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Gemini AI to the electricity account manager for AI-powered PDF bill parsing and natural language energy
insights.

**Architecture:** A new `src/ai/gemini.py` module handles all Gemini interactions (parsing + insights). It imports
`BillRecord` and `CpflPdfParser` from the existing parser for fallback. The CLI, config, report orchestration, and PDF
writer are updated to thread `GeminiConfig` through the pipeline.

**Tech Stack:** Python 3.12, google-genai SDK, python-dotenv, existing pandas/pdfplumber/reportlab stack.

**Spec:** `docs/superpowers/specs/2026-03-22-gemini-integration-design.md`

---

### Task 1: Add dependencies

**Files:**

- Modify: `requirements.txt`

- [ ] **Step 1: Add google-genai and python-dotenv to requirements.txt**

Append to the end of `requirements.txt`:

```
google-genai
python-dotenv
```

- [ ] **Step 2: Install dependencies**

Run: `source .venv/bin/activate && pip install google-genai python-dotenv`
Expected: successful install, no errors.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add google-genai and python-dotenv dependencies"
```

---

### Task 2: Add GeminiConfig to config.py

**Files:**

- Modify: `config.py`

- [ ] **Step 1: Add GeminiConfig dataclass**

Add after the `EconomicConfig` class (line 24), before the DEFAULT_* constants:

```python
@dataclass(frozen=True)
class GeminiConfig:
    api_key: str | None = None
    model: str = "gemini-3-flash-preview"
```

- [ ] **Step 2: Verify config.py loads without error**

Run: `source .venv/bin/activate && python -c "from config import GeminiConfig; print(GeminiConfig())"`
Expected: `GeminiConfig(api_key=None, model='gemini-3-flash-preview')`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat: add GeminiConfig dataclass"
```

---

### Task 3: Create src/ai/gemini.py — parse_bill_text()

**Files:**

- Create: `src/ai/__init__.py`
- Create: `src/ai/gemini.py`

This is the core module. It imports `BillRecord` and `CpflPdfParser` from `parsers.cpfl_pdf` for the return type and
regex fallback.

- [ ] **Step 1: Create empty __init__.py**

Create `src/ai/__init__.py` as an empty file.

- [ ] **Step 2: Create gemini.py with parse_bill_text()**

Create `src/ai/gemini.py`:

```python
from __future__ import annotations

import json
import warnings

import pandas as pd

from config import GeminiConfig
from parsers.cpfl_pdf import BillRecord, CpflPdfParser


def _get_client(config: GeminiConfig):
    """Create a Gemini client. Returns None if api_key is missing."""
    if config.api_key is None:
        return None
    from google import genai
    return genai.Client(api_key=config.api_key)


def _regex_fallback(text: str, source_pdf: str) -> BillRecord:
    """Full regex parsing path — mirrors CpflPdfParser.parse_bill_pdf logic."""
    month = CpflPdfParser.parse_reference_month(text)
    cons, inj = CpflPdfParser.parse_consumed_injected(text, month)
    if cons is None:
        raise ValueError(f"Regex fallback: não conseguiu extrair consumo do PDF: {source_pdf}")
    return BillRecord(
        month=month,
        consumption_kwh=int(cons),
        injected_kwh=int(inj) if inj is not None else None,
        source_pdf=source_pdf,
    )


_PARSE_PROMPT = """\
Você é um assistente especializado em extrair dados de faturas de energia elétrica brasileiras (CPFL).

Extraia do texto abaixo:
1. O mês/ano de referência da fatura
2. O consumo total em kWh
3. A energia ativa injetada em kWh (se houver)

Responda APENAS com JSON válido neste formato exato:
{"month": "YYYY-MM", "consumption_kwh": <int>, "injected_kwh": <int ou null>}

Texto da fatura:
"""


def parse_bill_text(text: str, source_pdf: str, config: GeminiConfig) -> BillRecord:
    """Parse bill text using Gemini AI, with regex fallback on failure."""
    client = _get_client(config)
    if client is None:
        warnings.warn("GEMINI_API_KEY não configurada. Usando parser regex.")
        return _regex_fallback(text, source_pdf)

    try:
        response = client.models.generate_content(
            model=config.model,
            contents=_PARSE_PROMPT + text,
        )
        raw = response.text.strip()
        # Remove markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0].strip()
        data = json.loads(raw)

        month = str(data["month"])
        consumption_kwh = int(data["consumption_kwh"])
        injected_raw = data.get("injected_kwh")
        injected_kwh = int(injected_raw) if injected_raw is not None else None

        return BillRecord(
            month=month,
            consumption_kwh=consumption_kwh,
            injected_kwh=injected_kwh,
            source_pdf=source_pdf,
        )
    except Exception as e:
        warnings.warn(f"Gemini parse falhou ({e}). Usando fallback regex.")
        return _regex_fallback(text, source_pdf)
```

- [ ] **Step 3: Verify module imports**

Run: `source .venv/bin/activate && PYTHONPATH=src python -c "from ai.gemini import parse_bill_text; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/ai/__init__.py src/ai/gemini.py
git commit -m "feat: add gemini.py with parse_bill_text and regex fallback"
```

---

### Task 4: Add generate_insights() to gemini.py

**Files:**

- Modify: `src/ai/gemini.py`

- [ ] **Step 1: Add generate_insights function**

Append to the end of `src/ai/gemini.py`:

```python
_INSIGHTS_SHORT_PROMPT = """\
Você é um consultor de energia solar. Analise os dados abaixo e escreva um resumo curto \
(2-3 frases) em português do Brasil, destacando: economia obtida, saldo energético \
e se a produção solar foi suficiente para cobrir o consumo.
Use formato monetário brasileiro (R$ X.XXX,XX) e separador decimal com vírgula.

Dados do relatório:
"""

_INSIGHTS_DETAILED_PROMPT = """\
Você é um consultor de energia solar. Analise os dados abaixo e escreva uma análise \
detalhada em português do Brasil (1-2 parágrafos) contendo:
- Comparação entre produção e consumo
- Economia obtida e projeção de créditos
- Recomendações práticas para o consumidor
- Tendências observadas (se houver múltiplos meses)
Use formato monetário brasileiro (R$ X.XXX,XX) e separador decimal com vírgula.

Dados do relatório:
"""


def generate_insights(df: pd.DataFrame, config: GeminiConfig, detailed: bool = False) -> str:
    """Generate energy insights using Gemini AI. Returns empty string on failure."""
    client = _get_client(config)
    if client is None:
        warnings.warn("GEMINI_API_KEY não configurada. Insights indisponíveis.")
        return ""

    prompt = _INSIGHTS_DETAILED_PROMPT if detailed else _INSIGHTS_SHORT_PROMPT
    df_text = df.to_string(index=False)

    try:
        response = client.models.generate_content(
            model=config.model,
            contents=prompt + df_text,
        )
        return response.text.strip()
    except Exception as e:
        warnings.warn(f"Gemini insights falhou ({e}). Relatório gerado sem análise.")
        return ""
```

- [ ] **Step 2: Verify import**

Run: `source .venv/bin/activate && PYTHONPATH=src python -c "from ai.gemini import generate_insights; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/ai/gemini.py
git commit -m "feat: add generate_insights to gemini.py"
```

---

### Task 5: Update generate_report.py to use Gemini parsing

**Files:**

- Modify: `src/usecases/generate_report.py`

- [ ] **Step 1: Update imports and _read_all_bills_monthly**

Replace the entire content of `src/usecases/generate_report.py` with:

```python
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from config import EconomicConfig, GeminiConfig, PathsConfig
from parsers.cpfl_pdf import CpflPdfParser
from parsers.solar_csv import SolarCsvParser
from report.builder import MonthlyReportBuilder
from ai.gemini import parse_bill_text


def _read_all_solar_monthly(csv_paths: Sequence[Path]) -> pd.DataFrame:
    daily_dfs = [SolarCsvParser.read_daily(p) for p in csv_paths]
    daily = pd.concat(daily_dfs, ignore_index=True)
    return SolarCsvParser.monthly_production(daily)


def _read_all_bills_monthly(pdf_paths: Sequence[Path], gemini: GeminiConfig) -> pd.DataFrame:
    records = []
    for p in pdf_paths:
        text = CpflPdfParser.extract_text(p)
        record = parse_bill_text(text, source_pdf=p.name, config=gemini)
        records.append(record)
    df = pd.DataFrame([r.__dict__ for r in records])
    return df.groupby("month", as_index=False).agg(
        consumption_kwh=("consumption_kwh", "sum"),
        injected_kwh=("injected_kwh", "sum"),
    )


def generate_monthly_report(
        paths: PathsConfig, economic: EconomicConfig, gemini: GeminiConfig,
) -> pd.DataFrame:
    solar_monthly = _read_all_solar_monthly(paths.solar_csvs)
    bills_monthly = _read_all_bills_monthly(paths.bill_pdfs, gemini)
    return MonthlyReportBuilder.build(solar_monthly, bills_monthly, economic)
```

- [ ] **Step 2: Verify module loads**

Run:
`source .venv/bin/activate && PYTHONPATH=src python -c "from usecases.generate_report import generate_monthly_report; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/usecases/generate_report.py
git commit -m "feat: update generate_report to use Gemini parsing"
```

---

### Task 6: Update pdf_writer.py with insights section

**Files:**

- Modify: `src/report/pdf_writer.py`

- [ ] **Step 1: Add insights_text parameter to write()**

In `src/report/pdf_writer.py`, change the method signature on line 10:

From:

```python
def write(report_df: pd.DataFrame, out_pdf: Path, title: str) -> None:
```

To:

```python
def write(report_df: pd.DataFrame, out_pdf: Path, title: str, insights_text: str = "") -> None:
```

- [ ] **Step 2: Add insights section after the summary table**

In `src/report/pdf_writer.py`, after `story.append(t)` (line 222) and before `doc.build(story)` (line 224), add:

```python
        if insights_text:
story.append(Spacer(1, 14))
story.append(Paragraph("Análise Inteligente", styles["Heading2"]))
story.append(Spacer(1, 6))
for paragraph in insights_text.split("\n\n"):
    paragraph = paragraph.strip()
    if paragraph:
        story.append(Paragraph(paragraph, styles["Normal"]))
        story.append(Spacer(1, 4))
```

- [ ] **Step 3: Verify module loads**

Run:
`source .venv/bin/activate && PYTHONPATH=src python -c "from report.pdf_writer import PdfReportWriter; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/report/pdf_writer.py
git commit -m "feat: add insights section to PDF report"
```

---

### Task 7: Update cli.py with Gemini integration

**Files:**

- Modify: `cli.py`

This is the final integration point. Loads `.env`, adds `--gemini-api-key` argument, threads `GeminiConfig` through the
pipeline, and prints/embeds insights.

- [ ] **Step 1: Replace cli.py content**

Replace the entire content of `cli.py` with:

```python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from config import (
    DEFAULT_BILL_PDF,
    DEFAULT_OUT_CSV,
    DEFAULT_OUT_PDF,
    DEFAULT_SOLAR_CSV,
    EconomicConfig,
    GeminiConfig,
    PathsConfig,
)

# Garante que ./src esteja no sys.path para importar módulos internos.
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from usecases.generate_report import generate_monthly_report  # noqa: E402
from report.pdf_writer import PdfReportWriter  # noqa: E402
from ai.gemini import generate_insights  # noqa: E402


def parse_args() -> tuple[PathsConfig, EconomicConfig, GeminiConfig]:
    parser = argparse.ArgumentParser(
        description="Compara produção solar (CSV) vs consumo (PDF CPFL) e gera relatório mensal (kWh e R$) em CSV e PDF."
    )

    parser.add_argument(
        "--solar-csv",
        nargs="+",
        default=[str(DEFAULT_SOLAR_CSV)],
        help=f"Caminho(s) do(s) CSV(s) do inversor. Default: {DEFAULT_SOLAR_CSV}",
    )
    parser.add_argument(
        "--bill-pdf",
        nargs="+",
        default=[str(DEFAULT_BILL_PDF)],
        help=f"Caminho(s) do(s) PDF(s) da conta CPFL. Default: {DEFAULT_BILL_PDF}",
    )
    parser.add_argument(
        "--ratio-kwh",
        type=float,
        default=EconomicConfig().ratio_kwh,
        help="kWh de referência para proporção.",
    )
    parser.add_argument(
        "--ratio-reais",
        type=float,
        default=EconomicConfig().ratio_reais,
        help="R$ de referência para proporção.",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT_CSV),
        help=f"Arquivo de saída CSV. Default: {DEFAULT_OUT_CSV}",
    )
    parser.add_argument(
        "--out-pdf",
        default=str(DEFAULT_OUT_PDF),
        help=f"Arquivo de saída PDF. Default: {DEFAULT_OUT_PDF}",
    )
    parser.add_argument(
        "--gemini-api-key",
        default=None,
        help="API key do Gemini. Fallback: variável de ambiente GEMINI_API_KEY.",
    )

    args = parser.parse_args()

    paths = PathsConfig(
        bill_pdfs=tuple(Path(p) for p in args.bill_pdf),
        solar_csvs=tuple(Path(p) for p in args.solar_csv),
        out_csv=Path(args.out),
        out_pdf=Path(args.out_pdf),
    )
    economic = EconomicConfig(ratio_kwh=float(args.ratio_kwh), ratio_reais=float(args.ratio_reais))

    api_key = args.gemini_api_key or os.environ.get("GEMINI_API_KEY")
    gemini = GeminiConfig(api_key=api_key)

    return paths, economic, gemini


def main() -> None:
    load_dotenv()
    paths, economic, gemini = parse_args()

    report = generate_monthly_report(paths, economic, gemini)

    # Insights
    short_insights = generate_insights(report, gemini, detailed=False)
    detailed_insights = generate_insights(report, gemini, detailed=True)

    if short_insights:
        print("\n--- Análise Inteligente ---")
        print(short_insights)
        print("---\n")

    paths.out_csv.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(paths.out_csv, index=False, encoding="utf-8-sig")

    PdfReportWriter.write(
        report, paths.out_pdf,
        title="Relatório Mensal de Energia (Produção vs Consumo)",
        insights_text=detailed_insights,
    )

    print(report.to_string(index=False))
    print(f"\nOK: CSV salvo em {paths.out_csv}")
    print(f"OK: PDF salvo em {paths.out_pdf}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify parse_args loads**

Run: `source .venv/bin/activate && python -c "from cli import parse_args; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cli.py
git commit -m "feat: integrate Gemini into CLI with insights and dotenv"
```

---

### Task 8: Integration test — full run

- [ ] **Step 1: Run with Gemini (using .env API key)**

Run: `source .venv/bin/activate && python cli.py`

Expected:

- Terminal shows "--- Análise Inteligente ---" with a short summary
- DataFrame table printed
- CSV saved to `report/relatorio_energia.csv`
- PDF saved to `report/relatorio_energia.pdf`

- [ ] **Step 2: Verify PDF contains insights section**

Open `report/relatorio_energia.pdf` and confirm the "Análise Inteligente" section appears after the summary table.

- [ ] **Step 3: Test fallback without API key**

Run: `source .venv/bin/activate && GEMINI_API_KEY= python cli.py --gemini-api-key ""`

Expected:

- Warning messages about missing API key
- Report still generates using regex parser
- No insights section in output
- No crash

- [ ] **Step 4: Commit any adjustments if needed**

If adjustments were needed, commit only the specific changed files:

```bash
git add <specific-files>
git commit -m "fix: adjustments from integration testing"
```
