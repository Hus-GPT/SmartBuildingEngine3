from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def _rtl(text: str) -> str:
    return get_display(arabic_reshaper.reshape(str(text)))


class InvoicePdfRenderer:
    """Render a readable Arabic utility invoice using a supplied Unicode font."""

    def __init__(self, font_path: str | Path):
        path = Path(font_path)
        if not path.exists():
            raise FileNotFoundError(f"Arabic invoice font not found: {path}")
        self.font_name = "InvoiceArabic"
        pdfmetrics.registerFont(TTFont(self.font_name, str(path)))

    def render(self, *, invoice_number: str, tenant_name: str, unit_name: str, period: str,
               electricity_usage: Decimal, electricity_amount: Decimal, water_usage: Decimal,
               water_amount: Decimal, shared_expenses: Decimal, arrears: Decimal,
               total: Decimal, currency: str = "YER") -> bytes:
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        pdf.setFont(self.font_name, 16)
        pdf.drawCentredString(width / 2, height - 55, _rtl("فاتورة خدمات المبنى"))
        pdf.setFont(self.font_name, 10)
        y = height - 90
        rows = [
            ("رقم الفاتورة", invoice_number), ("المستأجر", tenant_name), ("الوحدة", unit_name),
            ("الفترة", period), ("استهلاك الكهرباء", electricity_usage), ("قيمة الكهرباء", electricity_amount),
            ("استهلاك الماء", water_usage), ("قيمة الماء", water_amount), ("المصاريف المشتركة", shared_expenses),
            ("المتأخرات", arrears), ("الإجمالي", f"{total} {currency}"),
        ]
        for label, value in rows:
            pdf.drawRightString(width - 60, y, _rtl(f"{label}: {value}"))
            y -= 24
        pdf.showPage(); pdf.save()
        return buffer.getvalue()
