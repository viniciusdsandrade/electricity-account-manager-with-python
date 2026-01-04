from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from config import (
    DEFAULT_BILL_PDF,
    DEFAULT_OUT_CSV,
    DEFAULT_OUT_PDF,
    DEFAULT_SOLAR_CSV,
    EconomicConfig,
    PathsConfig,
)

# Garante que ./src esteja no sys.path para importar módulos internos.
# Isso evita precisar rodar com PYTHONPATH=src.
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from usecases.generate_report import generate_monthly_report  # noqa: E402
from report.pdf_writer import PdfReportWriter  # noqa: E402


def parse_args() -> tuple[PathsConfig, EconomicConfig]:
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

    args = parser.parse_args()

    paths = PathsConfig(
        bill_pdfs=tuple(Path(p) for p in args.bill_pdf),
        solar_csvs=tuple(Path(p) for p in args.solar_csv),
        out_csv=Path(args.out),
        out_pdf=Path(args.out_pdf),
    )
    economic = EconomicConfig(ratio_kwh=float(args.ratio_kwh), ratio_reais=float(args.ratio_reais))

    return paths, economic


def main() -> None:
    paths, economic = parse_args()

    report = generate_monthly_report(paths, economic)

    paths.out_csv.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(paths.out_csv, index=False, encoding="utf-8-sig")

    PdfReportWriter.write(report, paths.out_pdf, title="Relatório Mensal de Energia (Produção vs Consumo)")

    print(report.to_string(index=False))
    print(f"\nOK: CSV salvo em {paths.out_csv}")
    print(f"OK: PDF salvo em {paths.out_pdf}")


if __name__ == "__main__":
    main()
