# Bill Verification Design

## Summary

Add a bill verification feature to the Electricity Account Manager that cross-references CPFL electricity bills with solar production data to verify both energy balance and financial correctness.

## Decisions

| Decision                  | Choice                                                            |
|---------------------------|-------------------------------------------------------------------|
| Architecture              | New usecase `verify_bill.py` + extended parser + new solar filter |
| Output format             | Terminal (formatted blocks) + Markdown file                       |
| CLI integration           | `--verificar` flag on existing `cli.py`                           |
| Solar period matching     | Exact metering period dates (not calendar month)                  |
| Financial tolerance       | R$ 0,05 for rounding divergences                                  |
| Minimum charge (bifásico) | 50 kWh hardcoded (configurable later if needed)                   |
| Existing code impact      | Additive only — BillRecord and current flow unchanged             |

## Architecture

### New/modified files

```
src/parsers/cpfl_pdf.py      # Add BillDetails dataclass + parse_bill_details()
src/parsers/solar_csv.py     # Add PeriodProduction dataclass + production_for_period()
src/usecases/verify_bill.py  # New — verification engine
src/report/md_writer.py      # New — markdown report writer for verification
cli.py                       # Add --verificar flag
```

### Data flow

```
cli.py --verificar
  │
  ├── CpflPdfParser.parse_bill_details(pdf)
  │     → BillDetails (period dates, consumption, injection, tariffs, taxes, charges)
  │
  ├── SolarCsvParser.read_daily(csv) → daily_df
  │     → SolarCsvParser.production_for_period(daily_df, start, end)
  │           → PeriodProduction (total_kwh, days, daily_breakdown)
  │
  └── verify_bill(BillDetails, PeriodProduction)
        → VerificationReport
              ├── print to terminal (formatted blocks)
              └── save to relatorio/verificacao/YYYY-MM.md
```

## New dataclasses

### BillDetails (src/parsers/cpfl_pdf.py)

```python
@dataclass(frozen=True)
class BillDetails:
    # Reference
    month: str                    # "YYYY-MM"
    source_pdf: str

    # Metering period
    reading_start: date           # leitura anterior
    reading_end: date             # leitura atual
    reading_days: int

    # Energy (kWh)
    consumption_kwh: int          # Energia Ativa consumida
    injected_kwh: int             # Energia Injetada total (medidor)
    compensated_kwh: int          # Energia compensada na fatura
    minimum_charge_kwh: int       # Taxa mínima (bifásico=50)
    energy_balance_kwh: float     # Saldo de energia da instalação

    # Tariffs (R$/kWh, ANEEL without taxes)
    tariff_tusd: float
    tariff_te: float
    tariff_tusd2_inj: float       # TUSD2 for injected energy

    # Tariffs with taxes (R$/kWh)
    tariff_tusd_with_tax: float
    tariff_te_with_tax: float
    tariff_tusd2_inj_with_tax: float
    tariff_te_inj_with_tax: float

    # Tax rates (%)
    icms_rate: float
    pis_rate: float
    cofins_rate: float

    # Billed amounts (R$)
    tusd_charge: float            # Consumo TUSD
    te_charge: float              # Consumo TE
    tusd_inj_credit: float        # Crédito TUSD injetada
    te_inj_credit: float          # Crédito TE injetada
    cip_charge: float             # Contribuição CIP
    other_charges: float          # Conta anterior + juros + multa + atualização
    total_billed: float           # Total cobrado
```

### PeriodProduction (src/parsers/solar_csv.py)

```python
@dataclass(frozen=True)
class PeriodProduction:
    total_kwh: float
    days: int
    daily_breakdown: tuple[tuple[date, float], ...]  # (date, kwh) pairs
```

### VerificationReport (src/usecases/verify_bill.py)

```python
@dataclass(frozen=True)
class VerificationReport:
    bill: BillDetails
    solar: PeriodProduction

    # Energy verification
    self_consumption_kwh: float     # production - injected
    real_consumption_kwh: float     # self_consumption + grid_consumption
    expected_compensation_kwh: int  # min(consumption, injected) capped by (consumption - minimum)
    credits_generated_kwh: int      # injected - compensated
    energy_status: str              # SUPERAVIT | DEFICIT | EQUILIBRIO

    # Financial verification (recalculated)
    calc_tusd_charge: float
    calc_te_charge: float
    calc_tusd_inj_credit: float
    calc_te_inj_credit: float
    calc_total: float

    # Divergence
    total_divergence: float         # billed - recalculated
    is_correct: bool                # abs(divergence) <= 0.05
```

## Parser extraction strategy

All new fields extracted via regex from the PDF text (same approach as existing `parse_consumed_injected`):

| Field           | Regex pattern target                                                                                              |
|-----------------|-------------------------------------------------------------------------------------------------------------------|
| Reading dates   | `Leitura atual DD/MM/YYYY` and `Leitura anterior DD/MM/YYYY` or the date fields near `13/03/2026  11/02/2026  30` |
| Tariffs         | Table rows: `Consumo Uso Sistema...TUSD...kWh...314,0000...0,38815000...0,49923567...156,76`                      |
| Compensated kWh | `Energia Ativa Injetada TUSD2...kWh...264,0000`                                                                   |
| Tax rates       | `ICMS...18,00`, `PIS...0,91%`, `COFINS...4,27%`                                                                   |
| CIP             | `Contribuição Custeio IP-CIP MAR/26...20,94`                                                                      |
| Other charges   | Sum of: Conta Mês Anterior + Juros + Multa + Atualização                                                          |
| Total           | `Total a pagar R$ 173,93` or total consolidado row                                                                |
| Energy balance  | `Saldo em Energia da Instalação: Convencional 532,0000000000 kWh`                                                 |

## CLI integration

```
python cli.py --verificar                          # uses defaults
python cli.py --verificar --bill-pdf X --solar-csv Y Z
```

When `--verificar` is passed:
1. Parse bill details (not just BillRecord)
2. Read all solar CSVs into daily DataFrame
3. Filter solar by metering period from bill
4. Run verification engine
5. Print formatted result to terminal
6. Save markdown to `relatorio/verificacao/YYYY-MM.md`

Normal mode (without `--verificar`) works exactly as before.

## Output format

### Terminal

Formatted blocks with sections: Período de Medição, Balanço Energético, Verificação Financeira, Diagnóstico.

### Markdown

Same content structured with tables, saved to `relatorio/verificacao/YYYY-MM.md`.
