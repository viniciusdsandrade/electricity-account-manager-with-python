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
