from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


class InvoicePdfRenderer:
    """Renders a compact invoice PDF. Font configuration can be supplied by deployment."""

    def __init__(self, font_path: str | None = None):
        self.font_name = "Helvetica"
        if font_path:
            pdfmetrics.registerFont(TTFont("InvoiceArabic", font_path))
            self.font_name = "InvoiceArabic"

    def render(self, *, invoice_number: str, tenant_name: str, unit_name: str,
               period: str, electricity_usage: Decimal, electricity_amount: Decimal,
               water_usage: Decimal, water_amount: Decimal, shared_expenses: Decimal,
               arrears: Decimal, total: Decimal) -> bytes:
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        pdf.setFont(self.font_name, 16)
        pdf.drawCentredString(width / 2, height - 55, "فاتورة خدمات المبنى")
        pdf.setFont(self.font_name, 10)
        y = height - 90
        rows = [
            ("رقم الفاتورة", invoice_number),
            ("المستأجر", tenant_name),
            ("الوحدة", unit_name),
            ("الفترة", period),
            ("استهلاك الكهرباء", str(electricity_usage)),
            ("قيمة الكهرباء", str(electricity_amount)),
            ("استهلاك الماء", str(water_usage)),
            ("قيمة الماء", str(water_amount)),
            ("المصاريف المشتركة", str(shared_expenses)),
            ("المتأخرات", str(arrears)),
            ("الإجمالي", str(total)),
        ]
        for label, value in rows:
            pdf.drawString(60, y, f"{label}: {value}")
            y -= 24
        pdf.showPage()
        pdf.save()
        return buffer.getvalue()
