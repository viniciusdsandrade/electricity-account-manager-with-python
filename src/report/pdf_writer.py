from __future__ import annotations

from pathlib import Path

import pandas as pd


class PdfReportWriter:
    @staticmethod
    def write(report_df: pd.DataFrame, out_pdf: Path, title: str, insights_text: str = "") -> None:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            Flowable,
        )
        from reportlab.graphics.shapes import Drawing, String
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.charts.lineplots import LinePlot
        from reportlab.graphics import renderPDF

        out_pdf.parent.mkdir(parents=True, exist_ok=True)

        def fmt_num_ptbr(v: float, decimals: int = 2) -> str:
            s = f"{v:,.{decimals}f}"
            return s.replace(",", "X").replace(".", ",").replace("X", ".")

        def fmt_kwh(v) -> str:
            try:
                return fmt_num_ptbr(float(v), 2)
            except Exception:
                return str(v)

        def fmt_currency(v) -> str:
            try:
                return f"R$ {fmt_num_ptbr(float(v), 2)}"
            except Exception:
                return str(v)

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=9, leading=11))
        styles.add(ParagraphStyle(name="Kpi", parent=styles["Normal"], fontSize=11, leading=14))
        styles.add(ParagraphStyle(name="KpiValue", parent=styles["Normal"], fontSize=14, leading=16))

        doc = SimpleDocTemplate(
            str(out_pdf),
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
        )

        story = []
        story.append(Paragraph(title, styles["Title"]))

        df = report_df.copy()
        if not df.empty:
            first_month = str(df["month"].iloc[0])
            last_month = str(df["month"].iloc[-1])
            period = f"Período: {first_month} → {last_month}"
        else:
            period = "Período: (sem dados)"

        r_por_kwh = float(df["r_por_kwh"].iloc[0]) if (not df.empty and "r_por_kwh" in df.columns) else 0.0
        story.append(Paragraph(period, styles["Small"]))
        story.append(Paragraph(f"Taxa usada no cálculo: {fmt_currency(r_por_kwh)} por kWh", styles["Small"]))
        story.append(Spacer(1, 10))

        total_prod = float(df["production_kwh"].sum()) if "production_kwh" in df.columns else 0.0
        total_cons = float(df["consumption_kwh"].sum()) if "consumption_kwh" in df.columns else 0.0
        total_saldo_kwh = float(df["saldo_kwh"].sum()) if "saldo_kwh" in df.columns else 0.0
        total_saldo_r = float(df["saldo_financeiro_r$"].sum()) if "saldo_financeiro_r$" in df.columns else 0.0

        kpi_data = [
            [
                Paragraph("Produção total", styles["Kpi"]),
                Paragraph("Consumo total", styles["Kpi"]),
                Paragraph("Saldo (kWh)", styles["Kpi"]),
                Paragraph("Saldo (R$)", styles["Kpi"]),
            ],
            [
                Paragraph(fmt_kwh(total_prod) + " kWh", styles["KpiValue"]),
                Paragraph(fmt_kwh(total_cons) + " kWh", styles["KpiValue"]),
                Paragraph(fmt_kwh(total_saldo_kwh) + " kWh", styles["KpiValue"]),
                Paragraph(fmt_currency(total_saldo_r), styles["KpiValue"]),
            ],
        ]

        kpi_table = Table(kpi_data, colWidths=[(doc.width / 4.0)] * 4)
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(kpi_table)
        story.append(Spacer(1, 12))

        class DrawingFlowable(Flowable):
            def __init__(self, drawing: Drawing):
                super().__init__()
                self.drawing = drawing
                self.width = drawing.width
                self.height = drawing.height

            def wrap(self, availWidth, availHeight):
                return self.width, self.height

            def draw(self):
                renderPDF.draw(self.drawing, self.canv, 0, 0)

        def build_chart(df_: pd.DataFrame) -> Drawing:
            w = doc.width
            h = 90 * mm

            months = [str(m) for m in df_["month"].tolist()]
            prod = [float(x) for x in df_["production_kwh"].tolist()]
            cons = [float(x) for x in df_["consumption_kwh"].tolist()]
            saldo = [float(x) for x in df_["saldo_kwh"].tolist()]

            d = Drawing(w, h)

            bc = VerticalBarChart()
            bc.x = 40
            bc.y = 25
            bc.width = w - 60
            bc.height = h - 45
            bc.data = [prod, cons]
            bc.categoryAxis.categoryNames = months
            bc.categoryAxis.labels.angle = 35
            bc.categoryAxis.labels.dy = -12
            bc.categoryAxis.labels.fontSize = 7

            bc.valueAxis.valueMin = 0
            max_y = max(prod + cons + [0.0])
            bc.valueAxis.valueMax = max(1.0, max_y * 1.15)
            bc.valueAxis.valueStep = max(10.0, bc.valueAxis.valueMax / 5.0)

            bc.bars[0].fillColor = colors.lightgrey
            bc.bars[1].fillColor = colors.darkgrey
            d.add(bc)

            lp = LinePlot()
            lp.x = bc.x
            lp.y = bc.y
            lp.width = bc.width
            lp.height = bc.height
            lp.data = [list(enumerate(saldo))]
            lp.xValueAxis.valueMin = -0.5
            lp.xValueAxis.valueMax = len(months) - 0.5 if months else 0.5
            lp.yValueAxis.valueMin = min(0.0, min(saldo + [0.0]))
            lp.yValueAxis.valueMax = max(1.0, max(saldo + [0.0]) * 1.15)
            lp.lines[0].strokeColor = colors.black
            lp.lines[0].strokeWidth = 1
            d.add(lp)

            d.add(String(0, h - 12, "Produção vs Consumo (barras) e Saldo kWh (linha)", fontSize=9))
            return d

        if not df.empty:
            story.append(DrawingFlowable(build_chart(df)))
            story.append(Spacer(1, 10))

        cols = [
            "month",
            "production_kwh",
            "consumption_kwh",
            "saldo_kwh",
            "economia_imediata_r$",
            "saldo_financeiro_r$",
        ]
        table_df = df[cols].copy() if all(c in df.columns for c in cols) else df.copy()

        header = ["Mês", "Produção (kWh)", "Consumo (kWh)", "Saldo (kWh)", "Economia (R$)", "Saldo (R$)"]
        data = [header]

        for _, row in table_df.iterrows():
            data.append(
                [
                    str(row["month"]),
                    fmt_kwh(row["production_kwh"]),
                    fmt_kwh(row["consumption_kwh"]),
                    fmt_kwh(row["saldo_kwh"]),
                    fmt_currency(row["economia_imediata_r$"]),
                    fmt_currency(row["saldo_financeiro_r$"]),
                ]
            )

        col_widths = [22 * mm, 30 * mm, 30 * mm, 28 * mm, 32 * mm, 32 * mm]
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.black),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(t)

        if insights_text:
            story.append(Spacer(1, 14))
            story.append(Paragraph("Análise Inteligente", styles["Heading2"]))
            story.append(Spacer(1, 6))
            for paragraph in insights_text.split("\n\n"):
                paragraph = paragraph.strip()
                if paragraph:
                    story.append(Paragraph(paragraph, styles["Normal"]))
                    story.append(Spacer(1, 4))

        doc.build(story)
