from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


_MONTH_MAP = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}
_MONTH_ABBR_BY_NUM = {v: k for k, v in _MONTH_MAP.items()}

_REF_MONTH_RE = re.compile(
    r"\b(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s*/\s*(\d{4})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BillRecord:
    month: str  # YYYY-MM
    consumption_kwh: int
    injected_kwh: Optional[int]
    source_pdf: str


@dataclass(frozen=True)
class BillDetails:
    month: str                    # "YYYY-MM"
    source_pdf: str
    reading_start: dt.date        # leitura anterior
    reading_end: dt.date          # leitura atual
    reading_days: int
    consumption_kwh: int          # Energia Ativa consumida
    injected_kwh: int             # Energia Injetada total (medidor)
    compensated_kwh: int          # Energia compensada na fatura
    minimum_charge_kwh: int       # Taxa mínima (bifásico=50)
    energy_balance_kwh: float     # Saldo de energia da instalação
    tariff_tusd: float
    tariff_te: float
    tariff_tusd2_inj: float       # TUSD2 for injected energy
    tariff_tusd_with_tax: float
    tariff_te_with_tax: float
    tariff_tusd2_inj_with_tax: float
    tariff_te_inj_with_tax: float
    icms_rate: float
    pis_rate: float
    cofins_rate: float
    tusd_charge: float            # Consumo TUSD
    te_charge: float              # Consumo TE
    tusd_inj_credit: float        # Crédito TUSD injetada
    te_inj_credit: float          # Crédito TE injetada
    cip_charge: float             # Contribuição CIP
    other_charges: float          # Conta anterior + juros + multa + atualização
    total_billed: float           # Total cobrado


class CpflPdfParser:
    @staticmethod
    def extract_text(pdf_path: Path) -> str:
        try:
            import pdfplumber  # type: ignore

            parts: list[str] = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
            return "\n".join(parts)
        except Exception:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(pdf_path))
            parts: list[str] = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
            return "\n".join(parts)

    @staticmethod
    def parse_reference_month(text: str) -> str:
        t = text.upper()
        m = _REF_MONTH_RE.search(t)
        if not m:
            raise ValueError("Não consegui encontrar o mês/ano de referência no PDF (ex.: DEZ/2025).")

        mon_abbr = m.group(1).upper()
        year = int(m.group(2))
        month = _MONTH_MAP[mon_abbr]
        return f"{year:04d}-{month:02d}"

    @staticmethod
    def _parse_ptbr_decimal(num_str: str) -> float:
        s = num_str.strip().replace(".", "").replace(",", ".")
        return float(s)

    @staticmethod
    def _month_token(ref_month: str) -> tuple[str, str, int]:
        year_s, month_s = ref_month.split("-")
        year = int(year_s)
        month = int(month_s)
        mon_abbr = _MONTH_ABBR_BY_NUM[month]
        yy = year % 100
        return mon_abbr, f"{mon_abbr}/{yy:02d}", yy

    @classmethod
    def parse_consumed_injected(cls, text: str, ref_month: str) -> Tuple[Optional[int], Optional[int]]:
        t = text.upper()
        mon_abbr, mon_token, yy = cls._month_token(ref_month)

        cons_pat = re.compile(
            rf"\bCONSUMO\s+USO\s+SISTEMA\s*\[KWH\]-TUSD\s+{re.escape(mon_token)}\s*KWH\s+(?P<q>\d+(?:[.,]\d+)?)",
            re.IGNORECASE,
        )
        cons_vals = [cls._parse_ptbr_decimal(v) for v in cons_pat.findall(t)]
        if cons_vals:
            consumption_kwh = int(round(sum(cons_vals)))
        else:
            hist_pat = re.compile(
                rf"\b{mon_abbr}\s+{yy:02d}\b[\s\S]{{0,300}}?(?P<kwh>\d{{1,4}})\s+(?P<dias>\d{{1,3}})\b",
                re.IGNORECASE,
            )
            hm = hist_pat.search(t)
            consumption_kwh = int(hm.group("kwh")) if hm else None

        inj_pat = re.compile(
            rf"\bENERGIA\s+ATIVA\s+INJETADA\s+TUSD2\s+{re.escape(mon_token)}\s*KWH\s+(?P<q>\d+(?:[.,]\d+)?)",
            re.IGNORECASE,
        )
        inj_vals = [cls._parse_ptbr_decimal(v) for v in inj_pat.findall(t)]
        injected_kwh = int(round(sum(inj_vals))) if inj_vals else None

        return consumption_kwh, injected_kwh

    @classmethod
    def parse_bill_pdf(cls, pdf_path: Path) -> BillRecord:
        text = cls.extract_text(pdf_path)
        month = cls.parse_reference_month(text)

        cons, inj = cls.parse_consumed_injected(text, month)
        if cons is None:
            raise ValueError(f"Não consegui extrair consumo (kWh) do PDF: {pdf_path}")

        return BillRecord(
            month=month,
            consumption_kwh=int(cons),
            injected_kwh=int(inj) if inj is not None else None,
            source_pdf=pdf_path.name,
        )
