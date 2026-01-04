from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


@dataclass(frozen=True)
class PathsConfig:
    bill_pdfs: Tuple[Path, ...]
    solar_csvs: Tuple[Path, ...]
    out_csv: Path
    out_pdf: Path


@dataclass(frozen=True)
class EconomicConfig:
    ratio_kwh: float = 1068.3
    ratio_reais: float = 726.4

    @property
    def reais_per_kwh(self) -> float:
        return self.ratio_reais / self.ratio_kwh


DEFAULT_BILL_PDF = Path(
    "/home/andrade/Desktop/electricity-account-manager-with-python/energy-bill/fatura-dezembro-2025.pdf"
)
DEFAULT_SOLAR_CSV = Path(
    "/home/andrade/Desktop/electricity-account-manager-with-python/energy-production/rendimento-painel-solar-dezembro.csv"
)
DEFAULT_OUT_DIR = Path(
    "/home/andrade/Desktop/electricity-account-manager-with-python/report"
)
DEFAULT_OUT_CSV = DEFAULT_OUT_DIR / "relatorio_energia.csv"
DEFAULT_OUT_PDF = DEFAULT_OUT_DIR / "relatorio_energia.pdf"
