# Bill Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bill verification that cross-references CPFL bills with solar production data to verify energy balance and financial correctness.

**Architecture:** Extended `CpflPdfParser` with `BillDetails` dataclass, new `production_for_period()` in `SolarCsvParser`, new `verify_bill.py` usecase, new `md_writer.py` for markdown output, and `--verificar` flag in CLI.

**Tech Stack:** Python 3.12, pdfplumber, pandas, existing parsers.

**Spec:** `docs/superpowers/specs/2026-03-22-bill-verification-design.md`

---

### Task 1: Add BillDetails dataclass to cpfl_pdf.py

**Files:**
- Modify: `src/parsers/cpfl_pdf.py:1-6` (imports) and after line 26 (new dataclass)

- [ ] **Step 1: Add datetime import**

Add `import datetime as dt` to the imports at line 3:

```python
import datetime as dt
```

- [ ] **Step 2: Add BillDetails dataclass after BillRecord (after line 26)**

```python
@dataclass(frozen=True)
class BillDetails:
    month: str
    source_pdf: str
    reading_start: dt.date
    reading_end: dt.date
    reading_days: int
    consumption_kwh: int
    injected_kwh: int
    compensated_kwh: int
    minimum_charge_kwh: int
    energy_balance_kwh: float
    tariff_tusd: float
    tariff_te: float
    tariff_tusd2_inj: float
    tariff_tusd_with_tax: float
    tariff_te_with_tax: float
    tariff_tusd2_inj_with_tax: float
    tariff_te_inj_with_tax: float
    icms_rate: float
    pis_rate: float
    cofins_rate: float
    tusd_charge: float
    te_charge: float
    tusd_inj_credit: float
    te_inj_credit: float
    cip_charge: float
    other_charges: float
    total_billed: float
```

- [ ] **Step 3: Verify syntax**

Run: `cd /home/andrade/Desktop/electricity-account-manager-with-python && source .venv/bin/activate && python -c "from src.parsers.cpfl_pdf import BillDetails; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add src/parsers/cpfl_pdf.py
git commit -m "feat: add BillDetails dataclass to cpfl_pdf.py"
```

---

### Task 2: Add parse_bill_details() to CpflPdfParser

**Files:**
- Modify: `src/parsers/cpfl_pdf.py` (add new classmethods after line 118)

The pdfplumber raw text has this structure (confirmed by extraction):
- Reading dates line: `7940335 13/03/2026 11/02/2026 30`
- Tariff line: `Consumo Uso Sistema [KWh]-TUSD MAR/26 kWh 314,0000 0,38815000 0,49923567 156,76 ...`
- Tax rates: `0,91% 4,27%` and `ICMS ... 18,00`
- Total: `MAR/2026 06/04/2026 R$ 173,93`
- Saldo: `Saldo em Energia da Instalação: Convencional 532,0000000000 kWh`

- [ ] **Step 1: Add _parse_reading_dates classmethod**

Append after `parse_consumed_injected` (after line 102):

```python
@classmethod
def _parse_reading_dates(cls, text: str) -> tuple[dt.date, dt.date, int]:
    """Extract metering period: (reading_start, reading_end, days).

    Pattern in pdfplumber output: '7940335 13/03/2026 11/02/2026 30'
    Format: codigo_instalacao leitura_atual leitura_anterior num_dias
    """
    pat = re.compile(
        r"\d{7}\s+(?P<end>\d{2}/\d{2}/\d{4})\s+(?P<start>\d{2}/\d{2}/\d{4})\s+(?P<days>\d{1,3})"
    )
    m = pat.search(text)
    if not m:
        raise ValueError("Não consegui extrair datas de leitura do PDF.")
    end = dt.datetime.strptime(m.group("end"), "%d/%m/%Y").date()
    start = dt.datetime.strptime(m.group("start"), "%d/%m/%Y").date()
    days = int(m.group("days"))
    return start, end, days
```

- [ ] **Step 2: Add _parse_tariff_line classmethod**

```python
@classmethod
def _parse_tariff_line(cls, text: str, label_pattern: str) -> tuple[float, float, float]:
    """Extract (quantity, tariff_aneel, tariff_with_tax, charge) from a tariff line.

    Returns (tariff_aneel, tariff_with_tax, total_charge).
    Sums if multiple lines match (e.g. December bill with meter swap).
    """
    pat = re.compile(
        label_pattern
        + r"\s+KWH\s+(?P<qty>\d+[.,]\d+)\s+(?P<taneel>\d+[.,]\d+)\s+(?P<ttax>\d+[.,]\d+)\s+(?P<charge>\d+[.,]\d+)-?",
        re.IGNORECASE,
    )
    matches = list(pat.finditer(text.upper()))
    if not matches:
        return 0.0, 0.0, 0.0
    taneel = cls._parse_ptbr_decimal(matches[0].group("taneel"))
    ttax = cls._parse_ptbr_decimal(matches[0].group("ttax"))
    total = sum(cls._parse_ptbr_decimal(m.group("charge")) for m in matches)
    return taneel, ttax, total
```

- [ ] **Step 3: Add _parse_tax_rates classmethod**

```python
@classmethod
def _parse_tax_rates(cls, text: str) -> tuple[float, float, float]:
    """Extract ICMS, PIS, COFINS rates from the PDF text."""
    t = text.upper()
    icms_m = re.search(r"ICMS\s+[\d.,]+\s+(?P<rate>\d+[.,]\d+)\s+[\d.,]+", t)
    icms = cls._parse_ptbr_decimal(icms_m.group("rate")) if icms_m else 18.0

    pis_m = re.search(r"(?P<rate>\d+[.,]\d+)%\s+\d+[.,]\d+%", t)
    cofins_m = re.search(r"\d+[.,]\d+%\s+(?P<rate>\d+[.,]\d+)%", t)
    pis = cls._parse_ptbr_decimal(pis_m.group("rate")) if pis_m else 0.0
    cofins = cls._parse_ptbr_decimal(cofins_m.group("rate")) if cofins_m else 0.0
    return icms, pis, cofins
```

- [ ] **Step 4: Add _parse_other_charges classmethod**

```python
@classmethod
def _parse_other_charges(cls, text: str) -> tuple[float, float]:
    """Extract CIP charge and sum of other charges (conta anterior, juros, multa, atualização).

    Returns (cip_charge, other_charges_sum).
    """
    t = text.upper()

    # CIP for the bill's own month (DÉBITOS DE OUTROS SERVIÇOS section)
    cip_pat = re.compile(
        r"CONTRIBUIÇÃO\s+CUSTEIO\s+IP-CIP\s+\w+/\d+\s+(?P<val>\d+[.,]\d+)"
    )
    cip_matches = cip_pat.findall(t)
    cip = cls._parse_ptbr_decimal(cip_matches[-1]) if cip_matches else 0.0

    other = 0.0
    for label in [r"CONTA\s+MÊS\s+ANTERIOR", r"JUROS\s+DE\s+MORA",
                  r"MULTA\s+POR\s+ATRASO\s+PGTO", r"ATUALIZAÇÃO\s+MONETÁRIA"]:
        m = re.search(label + r"\s+\w+/\d+\s+(?P<val>\d+[.,]\d+)", t)
        if m:
            other += cls._parse_ptbr_decimal(m.group("val"))

    return cip, other
```

- [ ] **Step 5: Add _parse_total_billed classmethod**

```python
@classmethod
def _parse_total_billed(cls, text: str) -> float:
    """Extract total billed amount (R$)."""
    m = re.search(r"R\$\s*(?P<val>\d+[.,]\d+)", text)
    if not m:
        raise ValueError("Não consegui extrair o valor total da fatura.")
    return cls._parse_ptbr_decimal(m.group("val"))
```

- [ ] **Step 6: Add _parse_energy_balance classmethod**

```python
@classmethod
def _parse_energy_balance(cls, text: str) -> float:
    """Extract saldo em energia da instalação (kWh)."""
    m = re.search(
        r"SALDO\s+EM\s+ENERGIA\s+DA\s+INSTALA[CÇ][AÃ]O.*?(?P<val>\d+[.,]\d+)\s*KWH",
        text.upper(),
    )
    return cls._parse_ptbr_decimal(m.group("val")) if m else 0.0
```

- [ ] **Step 7: Add parse_bill_details classmethod (main orchestrator)**

```python
@classmethod
def parse_bill_details(cls, pdf_path: Path) -> BillDetails:
    """Full extraction of bill details for verification."""
    text = cls.extract_text(pdf_path)
    month = cls.parse_reference_month(text)
    mon_abbr, mon_token, yy = cls._month_token(month)

    reading_start, reading_end, reading_days = cls._parse_reading_dates(text)

    cons, inj_compensated = cls.parse_consumed_injected(text, month)
    if cons is None:
        raise ValueError(f"Não consegui extrair consumo do PDF: {pdf_path}")

    # Injected total from meter readings
    inj_meter_pat = re.compile(
        r"ENERGIA\s+INJETADA\s+ÚNICO\s+\d+\s+\d+\s+[\d.,]+\s+(?P<val>\d+)",
        re.IGNORECASE,
    )
    inj_meter_m = inj_meter_pat.search(text.upper())
    injected_total = int(inj_meter_m.group("val")) if inj_meter_m else (inj_compensated or 0)

    compensated = inj_compensated or 0
    minimum_charge = cons - compensated if compensated > 0 else cons

    tusd_aneel, tusd_tax, tusd_charge = cls._parse_tariff_line(
        text, rf"CONSUMO\s+USO\s+SISTEMA\s*\[KWH\]-TUSD\s+{re.escape(mon_token)}"
    )
    te_aneel, te_tax, te_charge = cls._parse_tariff_line(
        text, rf"CONSUMO\s+-\s+TE\s+{re.escape(mon_token)}"
    )
    tusd2_aneel, tusd2_tax, tusd_inj_credit = cls._parse_tariff_line(
        text, rf"ENERGIA\s+ATIVA\s+INJETADA\s+TUSD2\s+{re.escape(mon_token)}"
    )
    _, te_inj_tax, te_inj_credit = cls._parse_tariff_line(
        text, rf"ENERGIA\s+ATIVA\s+INJETADA\s+TE\s+{re.escape(mon_token)}"
    )

    icms, pis, cofins = cls._parse_tax_rates(text)
    cip, other = cls._parse_other_charges(text)
    total = cls._parse_total_billed(text)
    balance = cls._parse_energy_balance(text)

    return BillDetails(
        month=month,
        source_pdf=pdf_path.name,
        reading_start=reading_start,
        reading_end=reading_end,
        reading_days=reading_days,
        consumption_kwh=cons,
        injected_kwh=injected_total,
        compensated_kwh=compensated,
        minimum_charge_kwh=minimum_charge,
        energy_balance_kwh=balance,
        tariff_tusd=tusd_aneel,
        tariff_te=te_aneel,
        tariff_tusd2_inj=tusd2_aneel,
        tariff_tusd_with_tax=tusd_tax,
        tariff_te_with_tax=te_tax,
        tariff_tusd2_inj_with_tax=tusd2_tax,
        tariff_te_inj_with_tax=te_inj_tax,
        icms_rate=icms,
        pis_rate=pis,
        cofins_rate=cofins,
        tusd_charge=tusd_charge,
        te_charge=te_charge,
        tusd_inj_credit=tusd_inj_credit,
        te_inj_credit=te_inj_credit,
        cip_charge=cip,
        other_charges=other,
        total_billed=total,
    )
```

- [ ] **Step 8: Verify with actual PDF**

Run:
```bash
cd /home/andrade/Desktop/electricity-account-manager-with-python
source .venv/bin/activate
python -c "
import sys; sys.path.insert(0, 'src')
from pathlib import Path
from parsers.cpfl_pdf import CpflPdfParser
d = CpflPdfParser.parse_bill_details(Path('relatorio/CPFL/boleto_02_00_03.pdf'))
print(f'Mês: {d.month}')
print(f'Período: {d.reading_start} → {d.reading_end} ({d.reading_days} dias)')
print(f'Consumo: {d.consumption_kwh} kWh | Injetado: {d.injected_kwh} kWh | Compensado: {d.compensated_kwh} kWh')
print(f'Tarifas TUSD: {d.tariff_tusd} / TE: {d.tariff_te}')
print(f'ICMS: {d.icms_rate}% | PIS: {d.pis_rate}% | COFINS: {d.cofins_rate}%')
print(f'Total: R\$ {d.total_billed}')
print(f'Saldo energia: {d.energy_balance_kwh} kWh')
"
```

Expected:
```
Mês: 2026-03
Período: 2026-02-11 → 2026-03-13 (30 dias)
Consumo: 314 kWh | Injetado: 471 kWh | Compensado: 264 kWh
Tarifas TUSD: 0.38815 / TE: 0.28738
ICMS: 18.0% | PIS: 0.91% | COFINS: 4.27%
Total: R$ 173.93
Saldo energia: 532.0 kWh
```

- [ ] **Step 9: Commit**

```bash
git add src/parsers/cpfl_pdf.py
git commit -m "feat: add parse_bill_details with full tariff/date extraction"
```

---

### Task 3: Add PeriodProduction + production_for_period() to solar_csv.py

**Files:**
- Modify: `src/parsers/solar_csv.py` (add dataclass and new staticmethod)

- [ ] **Step 1: Add PeriodProduction dataclass (after imports, before SolarCsvParser)**

```python
@dataclass(frozen=True)
class PeriodProduction:
    total_kwh: float
    days: int
    daily_breakdown: tuple[tuple[dt.date, float], ...]
```

Add `from dataclasses import dataclass` to imports.

- [ ] **Step 2: Add production_for_period staticmethod to SolarCsvParser**

```python
@staticmethod
def production_for_period(
    daily_df: pd.DataFrame, start: dt.date, end: dt.date,
) -> PeriodProduction:
    mask = (daily_df["date"] >= start) & (daily_df["date"] <= end)
    filtered = daily_df[mask].sort_values("date")
    breakdown = tuple(
        (row["date"], float(row["production_kwh"]))
        for _, row in filtered.iterrows()
    )
    return PeriodProduction(
        total_kwh=round(float(filtered["production_kwh"].sum()), 2),
        days=len(filtered),
        daily_breakdown=breakdown,
    )
```

- [ ] **Step 3: Verify with actual CSVs**

Run:
```bash
cd /home/andrade/Desktop/electricity-account-manager-with-python
source .venv/bin/activate
python -c "
import sys, datetime as dt; sys.path.insert(0, 'src')
from pathlib import Path
from parsers.solar_csv import SolarCsvParser
import pandas as pd

csvs = [
    Path('relatorio/report/ENERGY_REPORT_TABLE_6a737afb-b116-4b00-9d56-9d8ff4b3a87a_07.csv'),
    Path('relatorio/report/ENERGY_REPORT_TABLE_6a737afb-b116-4b00-9d56-9d8ff4b3a87a_41.csv'),
]
daily = pd.concat([SolarCsvParser.read_daily(p) for p in csvs], ignore_index=True)
result = SolarCsvParser.production_for_period(daily, dt.date(2026, 2, 11), dt.date(2026, 3, 13))
print(f'Total: {result.total_kwh} kWh em {result.days} dias')
print(f'Primeiros 3 dias: {result.daily_breakdown[:3]}')
"
```

Expected: ~756.5 kWh em 30 dias.

- [ ] **Step 4: Commit**

```bash
git add src/parsers/solar_csv.py
git commit -m "feat: add PeriodProduction and production_for_period to solar_csv.py"
```

---

### Task 4: Create verification engine (src/usecases/verify_bill.py)

**Files:**
- Create: `src/usecases/verify_bill.py`

- [ ] **Step 1: Create verify_bill.py with VerificationReport and verify_bill()**

```python
from __future__ import annotations

from dataclasses import dataclass

from parsers.cpfl_pdf import BillDetails
from parsers.solar_csv import PeriodProduction


@dataclass(frozen=True)
class VerificationReport:
    bill: BillDetails
    solar: PeriodProduction
    self_consumption_kwh: float
    real_consumption_kwh: float
    expected_compensation_kwh: int
    credits_generated_kwh: int
    energy_status: str
    calc_tusd_charge: float
    calc_te_charge: float
    calc_tusd_inj_credit: float
    calc_te_inj_credit: float
    calc_subtotal_energy: float
    calc_total: float
    total_divergence: float
    is_correct: bool


_TOLERANCE = 0.05


def verify_bill(bill: BillDetails, solar: PeriodProduction) -> VerificationReport:
    # --- Energy verification ---
    self_consumption = round(solar.total_kwh - bill.injected_kwh, 2)
    real_consumption = round(self_consumption + bill.consumption_kwh, 2)
    expected_comp = min(bill.consumption_kwh, bill.injected_kwh)
    expected_comp = min(expected_comp, bill.consumption_kwh - bill.minimum_charge_kwh)
    credits = bill.injected_kwh - bill.compensated_kwh

    net = solar.total_kwh - real_consumption
    if net > 10:
        status = "SUPERAVIT"
    elif net < -10:
        status = "DEFICIT"
    else:
        status = "EQUILIBRIO"

    # --- Financial verification ---
    calc_tusd = round(bill.consumption_kwh * bill.tariff_tusd_with_tax, 2)
    calc_te = round(bill.consumption_kwh * bill.tariff_te_with_tax, 2)
    calc_tusd_inj = round(bill.compensated_kwh * bill.tariff_tusd2_inj_with_tax, 2)
    calc_te_inj = round(bill.compensated_kwh * bill.tariff_te_inj_with_tax, 2)

    calc_subtotal = round(calc_tusd + calc_te - calc_tusd_inj - calc_te_inj, 2)
    calc_total = round(calc_subtotal + bill.cip_charge + bill.other_charges, 2)

    divergence = round(bill.total_billed - calc_total, 2)

    return VerificationReport(
        bill=bill,
        solar=solar,
        self_consumption_kwh=self_consumption,
        real_consumption_kwh=real_consumption,
        expected_compensation_kwh=expected_comp,
        credits_generated_kwh=credits,
        energy_status=status,
        calc_tusd_charge=calc_tusd,
        calc_te_charge=calc_te,
        calc_tusd_inj_credit=calc_tusd_inj,
        calc_te_inj_credit=calc_te_inj,
        calc_subtotal_energy=calc_subtotal,
        calc_total=calc_total,
        total_divergence=divergence,
        is_correct=abs(divergence) <= _TOLERANCE,
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/usecases/verify_bill.py
git commit -m "feat: add verify_bill engine with energy and financial verification"
```

---

### Task 5: Create markdown + terminal writer (src/report/md_writer.py)

**Files:**
- Create: `src/report/md_writer.py`

- [ ] **Step 1: Create md_writer.py with format_terminal() and write_markdown()**

```python
from __future__ import annotations

from pathlib import Path

from usecases.verify_bill import VerificationReport


def _fmt_ptbr(v: float, decimals: int = 2) -> str:
    s = f"{v:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_r(v: float) -> str:
    return f"R$ {_fmt_ptbr(v)}"


def _fmt_date(d) -> str:
    return d.strftime("%d/%m/%Y")


def format_terminal(r: VerificationReport) -> str:
    b = r.bill
    s = r.solar
    lines = [
        f"=== VERIFICAÇÃO DA FATURA {b.month.replace('-', '/')} ===",
        "",
        "--- Período de Medição ---",
        f"Leitura anterior: {_fmt_date(b.reading_start)}",
        f"Leitura atual:    {_fmt_date(b.reading_end)} ({b.reading_days} dias)",
        "",
        "--- Balanço Energético ---",
        f"Produção solar (período):    {_fmt_ptbr(s.total_kwh)} kWh",
        f"Consumo da rede (medidor):   {b.consumption_kwh} kWh",
        f"Injeção na rede (medidor):   {b.injected_kwh} kWh",
        f"Auto-consumo solar:          {_fmt_ptbr(r.self_consumption_kwh)} kWh",
        f"Consumo real da casa:        {_fmt_ptbr(r.real_consumption_kwh)} kWh",
        f"Compensado na fatura:        {b.compensated_kwh} kWh",
        f"Taxa mínima (bifásico):      {b.minimum_charge_kwh} kWh",
        f"Créditos gerados:            {r.credits_generated_kwh} kWh",
        f"Saldo acumulado:             {_fmt_ptbr(b.energy_balance_kwh)} kWh",
        f"Status: {r.energy_status} ({_fmt_ptbr(s.total_kwh - r.real_consumption_kwh)} kWh líquido)",
        "",
        "--- Verificação Financeira ---",
        f"{'':30s} {'Fatura':>10s} {'Recalculado':>12s} {'Diff':>8s}",
        f"{'TUSD consumo':30s} {_fmt_ptbr(b.tusd_charge):>10s} {_fmt_ptbr(r.calc_tusd_charge):>12s} {_fmt_ptbr(b.tusd_charge - r.calc_tusd_charge):>8s}",
        f"{'TE consumo':30s} {_fmt_ptbr(b.te_charge):>10s} {_fmt_ptbr(r.calc_te_charge):>12s} {_fmt_ptbr(b.te_charge - r.calc_te_charge):>8s}",
        f"{'TUSD injetada (crédito)':30s} {_fmt_ptbr(-b.tusd_inj_credit):>10s} {_fmt_ptbr(-r.calc_tusd_inj_credit):>12s} {_fmt_ptbr(b.tusd_inj_credit - r.calc_tusd_inj_credit):>8s}",
        f"{'TE injetada (crédito)':30s} {_fmt_ptbr(-b.te_inj_credit):>10s} {_fmt_ptbr(-r.calc_te_inj_credit):>12s} {_fmt_ptbr(b.te_inj_credit - r.calc_te_inj_credit):>8s}",
        f"{'CIP':30s} {_fmt_ptbr(b.cip_charge):>10s} {_fmt_ptbr(b.cip_charge):>12s} {'0,00':>8s}",
        f"{'Outros (ant/juros/multa)':30s} {_fmt_ptbr(b.other_charges):>10s} {_fmt_ptbr(b.other_charges):>12s} {'0,00':>8s}",
        f"{'─' * 62}",
        f"{'TOTAL':30s} {_fmt_r(b.total_billed):>10s} {_fmt_r(r.calc_total):>12s} {_fmt_ptbr(r.total_divergence):>8s}",
        "",
    ]

    if r.is_correct:
        lines.append("OK Fatura confere (divergência dentro da tolerância de R$ 0,05)")
    else:
        lines.append(f"ATENÇÃO Divergência de {_fmt_r(r.total_divergence)} detectada!")

    return "\n".join(lines)


def write_markdown(r: VerificationReport, out_path: Path) -> None:
    b = r.bill
    s = r.solar

    status_symbol = "OK" if r.is_correct else "DIVERGENCIA"

    md = f"""# Verificação da Fatura {b.month}

**Arquivo:** {b.source_pdf}
**Status:** {status_symbol}

## Período de Medição

| Campo            | Valor                         |
|------------------|-------------------------------|
| Leitura anterior | {_fmt_date(b.reading_start)}  |
| Leitura atual    | {_fmt_date(b.reading_end)}    |
| Nº de dias       | {b.reading_days}              |

## Balanço Energético

| Métrica                    | Valor                 |
|----------------------------|-----------------------|
| Produção solar (período)   | {_fmt_ptbr(s.total_kwh)} kWh |
| Consumo da rede (medidor)  | {b.consumption_kwh} kWh      |
| Injeção na rede (medidor)  | {b.injected_kwh} kWh         |
| Auto-consumo solar         | {_fmt_ptbr(r.self_consumption_kwh)} kWh |
| Consumo real da casa       | {_fmt_ptbr(r.real_consumption_kwh)} kWh |
| Compensado na fatura       | {b.compensated_kwh} kWh      |
| Taxa mínima (bifásico)     | {b.minimum_charge_kwh} kWh   |
| Créditos gerados           | {r.credits_generated_kwh} kWh |
| Saldo acumulado            | {_fmt_ptbr(b.energy_balance_kwh)} kWh |
| **Status**                 | **{r.energy_status}** ({_fmt_ptbr(s.total_kwh - r.real_consumption_kwh)} kWh líquido) |

## Verificação Financeira

| Componente              | Fatura         | Recalculado    | Diferença    |
|-------------------------|----------------|----------------|--------------|
| TUSD consumo            | {_fmt_ptbr(b.tusd_charge)} | {_fmt_ptbr(r.calc_tusd_charge)} | {_fmt_ptbr(b.tusd_charge - r.calc_tusd_charge)} |
| TE consumo              | {_fmt_ptbr(b.te_charge)} | {_fmt_ptbr(r.calc_te_charge)} | {_fmt_ptbr(b.te_charge - r.calc_te_charge)} |
| TUSD injetada (crédito) | -{_fmt_ptbr(b.tusd_inj_credit)} | -{_fmt_ptbr(r.calc_tusd_inj_credit)} | {_fmt_ptbr(b.tusd_inj_credit - r.calc_tusd_inj_credit)} |
| TE injetada (crédito)   | -{_fmt_ptbr(b.te_inj_credit)} | -{_fmt_ptbr(r.calc_te_inj_credit)} | {_fmt_ptbr(b.te_inj_credit - r.calc_te_inj_credit)} |
| CIP                     | {_fmt_ptbr(b.cip_charge)} | {_fmt_ptbr(b.cip_charge)} | 0,00 |
| Outros                  | {_fmt_ptbr(b.other_charges)} | {_fmt_ptbr(b.other_charges)} | 0,00 |
| **TOTAL**               | **{_fmt_r(b.total_billed)}** | **{_fmt_r(r.calc_total)}** | **{_fmt_ptbr(r.total_divergence)}** |

## Tarifas Utilizadas

| Tarifa           | ANEEL (R$/kWh) | Com tributos (R$/kWh) |
|------------------|----------------|-----------------------|
| TUSD consumo     | {_fmt_ptbr(b.tariff_tusd, 5)} | {_fmt_ptbr(b.tariff_tusd_with_tax, 5)} |
| TE consumo       | {_fmt_ptbr(b.tariff_te, 5)} | {_fmt_ptbr(b.tariff_te_with_tax, 5)} |
| TUSD2 injetada   | {_fmt_ptbr(b.tariff_tusd2_inj, 5)} | {_fmt_ptbr(b.tariff_tusd2_inj_with_tax, 5)} |

## Tributos

| Tributo   | Alíquota |
|-----------|----------|
| ICMS      | {_fmt_ptbr(b.icms_rate)}%  |
| PIS/PASEP | {_fmt_ptbr(b.pis_rate)}%   |
| COFINS    | {_fmt_ptbr(b.cofins_rate)}% |

## Produção Solar Diária (Período de Medição)

| Data       | Produção (kWh) |
|------------|----------------|
"""
    for day, kwh in s.daily_breakdown:
        md += f"| {day.strftime('%d/%m/%Y')} | {_fmt_ptbr(kwh)} |\n"

    md += f"\n**Total período:** {_fmt_ptbr(s.total_kwh)} kWh em {s.days} dias\n"
    md += f"**Média diária:** {_fmt_ptbr(s.total_kwh / s.days if s.days else 0)} kWh/dia\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
```

- [ ] **Step 2: Commit**

```bash
git add src/report/md_writer.py
git commit -m "feat: add markdown and terminal writer for bill verification"
```

---

### Task 6: Integrate --verificar flag into CLI

**Files:**
- Modify: `cli.py:27-28` (add import), `cli.py:69-73` (add arg), `cli.py:91-121` (add verification flow)

- [ ] **Step 1: Add imports (after line 27)**

```python
from usecases.verify_bill import verify_bill  # noqa: E402
from report.md_writer import format_terminal, write_markdown  # noqa: E402
```

- [ ] **Step 2: Add --verificar argument (after line 73, the gemini-api-key arg)**

```python
parser.add_argument(
    "--verificar",
    action="store_true",
    default=False,
    help="Modo verificação: cruza fatura com produção solar e verifica valores.",
)
```

- [ ] **Step 3: Pass verificar flag in parse_args return**

Change `parse_args` to return a 4-tuple, adding `args.verificar` as the last element:

```python
def parse_args() -> tuple[PathsConfig, EconomicConfig, GeminiConfig, bool]:
```

At end of function:
```python
return paths, economic, gemini, args.verificar
```

- [ ] **Step 4: Add verification flow to main()**

Update `main()`:

```python
def main() -> None:
    load_dotenv()
    paths, economic, gemini, verificar = parse_args()

    if verificar:
        import datetime as dt
        from parsers.cpfl_pdf import CpflPdfParser
        from parsers.solar_csv import SolarCsvParser
        import pandas as pd

        bill = CpflPdfParser.parse_bill_details(paths.bill_pdfs[0])

        daily_dfs = [SolarCsvParser.read_daily(p) for p in paths.solar_csvs]
        daily = pd.concat(daily_dfs, ignore_index=True)
        solar = SolarCsvParser.production_for_period(
            daily, bill.reading_start, bill.reading_end,
        )

        report = verify_bill(bill, solar)
        print(format_terminal(report))

        out_md = Path("relatorio/verificacao") / f"{bill.month}.md"
        write_markdown(report, out_md)
        print(f"\nOK: Markdown salvo em {out_md}")
        return

    # ... existing report flow unchanged ...
```

- [ ] **Step 5: Full integration test with real data**

Run:
```bash
cd /home/andrade/Desktop/electricity-account-manager-with-python
source .venv/bin/activate
python cli.py --verificar \
  --bill-pdf relatorio/CPFL/boleto_02_00_03.pdf \
  --solar-csv relatorio/report/ENERGY_REPORT_TABLE_6a737afb-b116-4b00-9d56-9d8ff4b3a87a_07.csv \
              relatorio/report/ENERGY_REPORT_TABLE_6a737afb-b116-4b00-9d56-9d8ff4b3a87a_41.csv
```

Expected: Terminal output showing energy balance and financial verification for MAR/2026.
Verify: `relatorio/verificacao/2026-03.md` was created with full report.

- [ ] **Step 6: Commit**

```bash
git add cli.py
git commit -m "feat: add --verificar flag to CLI for bill verification"
```
