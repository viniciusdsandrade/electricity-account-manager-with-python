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
    net = s.total_kwh - r.real_consumption_kwh
    lines = [
        f"=== VERIFICAÇÃO DA FATURA {b.month} ===",
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
        f"Status: {r.energy_status} ({_fmt_ptbr(net)} kWh líquido)",
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
    net = s.total_kwh - r.real_consumption_kwh

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
| **Status**                 | **{r.energy_status}** ({_fmt_ptbr(net)} kWh líquido) |

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

    avg = s.total_kwh / s.days if s.days else 0
    md += f"\n**Total período:** {_fmt_ptbr(s.total_kwh)} kWh em {s.days} dias\n"
    md += f"**Média diária:** {_fmt_ptbr(avg)} kWh/dia\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
