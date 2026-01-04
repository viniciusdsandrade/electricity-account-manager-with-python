from __future__ import annotations

import pandas as pd

from config import EconomicConfig


REPORT_COLUMNS = [
    "month",
    "production_kwh",
    "consumption_kwh",
    "injected_kwh",
    "saldo_kwh",
    "kwh_compensados",
    "kwh_excedente",
    "kwh_deficit",
    "r_por_kwh",
    "economia_imediata_r$",
    "credito_equivalente_r$",
    "prejuizo_equivalente_r$",
    "saldo_financeiro_r$",
]


class MonthlyReportBuilder:
    @staticmethod
    def build(
        solar_monthly_df: pd.DataFrame,
        bills_monthly_df: pd.DataFrame,
        economic: EconomicConfig,
    ) -> pd.DataFrame:
        value_per_kwh = economic.reais_per_kwh

        merged = pd.merge(
            solar_monthly_df,
            bills_monthly_df,
            on="month",
            how="outer",
        ).fillna({"production_kwh": 0.0, "consumption_kwh": 0, "injected_kwh": 0})

        merged["consumption_kwh"] = merged["consumption_kwh"].astype(int)
        merged["injected_kwh"] = merged["injected_kwh"].astype(int)

        merged["saldo_kwh"] = merged["production_kwh"] - merged["consumption_kwh"]

        merged["kwh_compensados"] = merged.apply(
            lambda r: min(float(r["production_kwh"]), float(r["consumption_kwh"])),
            axis=1,
        )
        merged["kwh_excedente"] = merged["saldo_kwh"].apply(lambda x: max(float(x), 0.0))
        merged["kwh_deficit"] = merged["saldo_kwh"].apply(lambda x: max(float(-x), 0.0))

        merged["r_por_kwh"] = value_per_kwh
        merged["economia_imediata_r$"] = merged["kwh_compensados"] * value_per_kwh
        merged["credito_equivalente_r$"] = merged["kwh_excedente"] * value_per_kwh
        merged["prejuizo_equivalente_r$"] = merged["kwh_deficit"] * value_per_kwh
        merged["saldo_financeiro_r$"] = merged["saldo_kwh"] * value_per_kwh

        merged = merged.sort_values("month").reset_index(drop=True)

        float_cols = [
            "production_kwh",
            "saldo_kwh",
            "kwh_compensados",
            "kwh_excedente",
            "kwh_deficit",
            "r_por_kwh",
            "economia_imediata_r$",
            "credito_equivalente_r$",
            "prejuizo_equivalente_r$",
            "saldo_financeiro_r$",
        ]
        for col in float_cols:
            merged[col] = merged[col].astype(float).round(2)

        return merged.reindex(columns=REPORT_COLUMNS)
