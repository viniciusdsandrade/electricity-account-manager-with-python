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
