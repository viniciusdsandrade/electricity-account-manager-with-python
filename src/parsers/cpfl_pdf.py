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

    # ------------------------------------------------------------------
    # Bill detail extraction helpers
    # ------------------------------------------------------------------

    @classmethod
    def _parse_reading_dates(cls, text: str) -> tuple[dt.date, dt.date, int]:
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

    @classmethod
    def _parse_tariff_line(cls, text: str, label_pattern: str) -> tuple[float, float, float]:
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

    @classmethod
    def _parse_tax_rates(cls, text: str) -> tuple[float, float, float]:
        t = text.upper()
        icms_m = re.search(r"ICMS\s+[\d.,]+\s+(?P<rate>\d+[.,]\d+)\s+[\d.,]+", t)
        icms = cls._parse_ptbr_decimal(icms_m.group("rate")) if icms_m else 18.0

        pis_m = re.search(r"(?P<rate>\d+[.,]\d+)%\s+\d+[.,]\d+%", t)
        cofins_m = re.search(r"\d+[.,]\d+%\s+(?P<rate>\d+[.,]\d+)%", t)
        pis = cls._parse_ptbr_decimal(pis_m.group("rate")) if pis_m else 0.0
        cofins = cls._parse_ptbr_decimal(cofins_m.group("rate")) if cofins_m else 0.0
        return icms, pis, cofins

    @classmethod
    def _parse_other_charges(cls, text: str) -> tuple[float, float]:
        t = text.upper()
        cip_pat = re.compile(
            r"CONTRIBUIÇÃO\s+CUSTEIO\s+IP-CIP\s+\w+/\d+\s+(?P<val>\d+[.,]\d+)"
        )
        cip_matches = cip_pat.findall(t)
        cip = cls._parse_ptbr_decimal(cip_matches[-1]) if cip_matches else 0.0

        other = 0.0
        # Prior-month CIP entries (all except the last one) count as other charges
        for val_str in cip_matches[:-1]:
            other += cls._parse_ptbr_decimal(val_str)
        for label in [r"CONTA\s+MÊS\s+ANTERIOR", r"JUROS\s+DE\s+MORA",
                      r"MULTA\s+POR\s+ATRASO\s+PGTO", r"ATUALIZAÇÃO\s+MONETÁRIA"]:
            m = re.search(label + r"\s+\w+/\d+\s+(?P<val>\d+[.,]\d+)", t)
            if m:
                other += cls._parse_ptbr_decimal(m.group("val"))
        return cip, other

    @classmethod
    def _parse_total_billed(cls, text: str) -> float:
        m = re.search(r"R\$\s*(?P<val>\d+[.,]\d+)", text)
        if not m:
            raise ValueError("Não consegui extrair o valor total da fatura.")
        return cls._parse_ptbr_decimal(m.group("val"))

    @classmethod
    def _parse_energy_balance(cls, text: str) -> float:
        m = re.search(
            r"SALDO\s+EM\s+ENERGIA\s+DA\s+INSTALA[CÇ][AÃ]O.*?(?P<val>\d+[.,]\d+)\s*KWH",
            text.upper(),
        )
        return cls._parse_ptbr_decimal(m.group("val")) if m else 0.0

    @classmethod
    def parse_bill_details(cls, pdf_path: Path) -> BillDetails:
        text = cls.extract_text(pdf_path)
        month = cls.parse_reference_month(text)
        mon_abbr, mon_token, yy = cls._month_token(month)

        reading_start, reading_end, reading_days = cls._parse_reading_dates(text)

        cons, inj_compensated = cls.parse_consumed_injected(text, month)
        if cons is None:
            raise ValueError(f"Não consegui extrair consumo do PDF: {pdf_path}")

        # Injected total from meter readings line
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
