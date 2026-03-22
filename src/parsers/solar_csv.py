from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import pandas as pd


_DATE_LINE_RE = re.compile(
    r"^(?P<date>\d{4}\.\d{1,2}\.\d{1,2}),(?P<prod>-?\d+(?:\.\d+)?),(?P<cons>-?\d+(?:\.\d+)?),?\s*$"
)


@dataclass(frozen=True)
class PeriodProduction:
    total_kwh: float
    days: int
    daily_breakdown: tuple[tuple[dt.date, float], ...]


class SolarCsvParser:
    @staticmethod
    def read_daily(csv_path: Path) -> pd.DataFrame:
        rows: List[Tuple[dt.date, float]] = []

        with csv_path.open("r", encoding="utf-8-sig", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()
                m = _DATE_LINE_RE.match(line)
                if not m:
                    continue

                y, mo, d = (int(x) for x in m.group("date").split("."))
                day = dt.date(y, mo, d)
                prod = float(m.group("prod"))
                rows.append((day, prod))

        if not rows:
            raise ValueError(f"Nenhuma linha diária de produção foi encontrada em: {csv_path}")

        return pd.DataFrame(rows, columns=["date", "production_kwh"])

    @staticmethod
    def monthly_production(daily_df: pd.DataFrame) -> pd.DataFrame:
        df = daily_df.copy()
        df["month"] = df["date"].apply(lambda d: f"{d.year:04d}-{d.month:02d}")
        return df.groupby("month", as_index=False)["production_kwh"].sum()

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
