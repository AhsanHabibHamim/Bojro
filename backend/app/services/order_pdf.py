"""Dependency-light, snapshot-based bilingual order PDF rendering."""

from __future__ import annotations

import html
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.errors import DomainError
from app.db.models import Order

_FONT_NAME = "BojroNotoBengali"


class OrderPDFService:
    def __init__(self, font_path: str) -> None:
        self._font_path = Path(font_path)

    def render(self, order: Order, document: str, language: str) -> bytes:
        self._ensure_font()
        is_bn = language == "bn"
        snapshot = order.merchant_snapshot
        branding = snapshot.get("branding", snapshot)
        contact = snapshot.get("contact", {})
        if not isinstance(branding, dict):
            branding = {}
        if not isinstance(contact, dict):
            contact = {}
        store_name = str(
            branding.get("store_name_bn" if is_bn else "store_name_en")
            or ("বজ্র" if is_bn else "Bojro")
        )
        title = (
            ("অর্ডার ইনভয়েস (রাজস্ব চালান নয়)" if is_bn else "Order Invoice (Non-fiscal)")
            if document == "invoice"
            else ("প্যাকিং তালিকা" if is_bn else "Packing Slip")
        )
        buffer = BytesIO()
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
            title=f"{order.number} {title}",
            author=store_name,
        )
        styles = getSampleStyleSheet()
        normal = ParagraphStyle(
            "BojroNormal",
            parent=styles["Normal"],
            fontName=_FONT_NAME,
            fontSize=9,
            leading=13,
        )
        heading = ParagraphStyle(
            "BojroHeading",
            parent=normal,
            fontSize=16,
            leading=22,
            spaceAfter=4,
        )
        right = ParagraphStyle("BojroRight", parent=normal, alignment=TA_RIGHT)
        placed_at = order.placed_at.astimezone(ZoneInfo("Asia/Dhaka")).strftime("%Y-%m-%d %H:%M %Z")
        story: list[object] = [
            Paragraph(_safe(store_name), heading),
            Paragraph(_safe(title), normal),
            Paragraph(_safe(f"{('অর্ডার' if is_bn else 'Order')}: {order.number}"), normal),
            Paragraph(
                _safe(f"{('তারিখ' if is_bn else 'Placed')}: {placed_at}"),
                normal,
            ),
            Spacer(1, 8),
        ]
        address = order.address_snapshot
        recipient = str(
            address.get("recipient")
            or address.get("recipient_name")
            or address.get("customer_name")
            or ""
        )
        phone = str(address.get("phone") or "")
        address_lines = [
            recipient,
            phone,
            str(
                address.get("address_line")
                or address.get("line1")
                or address.get("address_line1")
                or ""
            ),
            ", ".join(
                value
                for value in (
                    _snapshot_geo_name(address.get("upazila"), is_bn),
                    _snapshot_geo_name(address.get("district"), is_bn),
                    _snapshot_geo_name(address.get("division"), is_bn),
                    str(address.get("district_name") or ""),
                )
                if value
            ),
        ]
        story.extend(
            [
                Paragraph(
                    _safe("ডেলিভারি ঠিকানা" if is_bn else "Delivery address"),
                    normal,
                ),
                Paragraph(_safe("<br/>".join(line for line in address_lines if line)), normal),
                Spacer(1, 10),
            ]
        )
        header = [
            "পণ্য" if is_bn else "Item",
            "SKU",
            "পরিমাণ" if is_bn else "Qty",
            "একক মূল্য" if is_bn else "Unit",
            "মোট" if is_bn else "Total",
        ]
        data: list[list[object]] = [[Paragraph(_safe(value), normal) for value in header]]
        for item in sorted(order.items, key=lambda value: value.id):
            name = item.name_bn if is_bn else item.name_en
            data.append(
                [
                    Paragraph(_safe(name), normal),
                    Paragraph(_safe(item.sku), normal),
                    Paragraph(str(item.quantity), right),
                    Paragraph(_money(item.unit_price), right),
                    Paragraph(_money(item.line_total), right),
                ]
            )
        table = Table(
            data,
            colWidths=[74 * mm, 31 * mm, 17 * mm, 28 * mm, 28 * mm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9F7F3")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#12372A")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9D8D1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([table, Spacer(1, 10)])
        if document == "invoice":
            totals = [
                ("উপমোট" if is_bn else "Subtotal", order.subtotal),
                ("ছাড়" if is_bn else "Discount", -order.discount_total),
                ("ডেলিভারি" if is_bn else "Delivery", order.shipping_total),
                ("সর্বমোট" if is_bn else "Grand total", order.grand_total),
            ]
            total_table = Table(
                [
                    [Paragraph(_safe(label), right), Paragraph(_money(amount), right)]
                    for label, amount in totals
                ],
                colWidths=[130 * mm, 48 * mm],
            )
            total_table.setStyle(
                TableStyle(
                    [
                        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#12372A")),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.extend([total_table, Spacer(1, 12)])
        contact_text = " | ".join(
            str(contact.get(key) or "")
            for key in ("phone", "email", "address_en")
            if contact.get(key)
        )
        if contact_text:
            story.append(Paragraph(_safe(contact_text), normal))
        story.append(
            Paragraph(
                _safe(
                    "এটি রাজস্ব বা ভ্যাট চালান নয়।"
                    if is_bn and document == "invoice"
                    else "This is not a fiscal or VAT invoice."
                    if document == "invoice"
                    else "Packed against the immutable order snapshot."
                ),
                normal,
            )
        )
        pdf.build(story)
        value = buffer.getvalue()
        if not value.startswith(b"%PDF"):
            raise RuntimeError("PDF renderer returned invalid output")
        return value

    def _ensure_font(self) -> None:
        if _FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return
        if not self._font_path.is_file():
            raise DomainError(
                "PDF_FONT_UNAVAILABLE",
                "The bundled Bengali PDF font is unavailable.",
                status_code=503,
            )
        pdfmetrics.registerFont(TTFont(_FONT_NAME, str(self._font_path)))


def _safe(value: str) -> str:
    return html.escape(value, quote=True).replace("\n", "<br/>")


def _money(poisha: int) -> str:
    sign = "-" if poisha < 0 else ""
    absolute = abs(poisha)
    return f"{sign}BDT {absolute // 100:,}.{absolute % 100:02d}"


def _snapshot_geo_name(value: object, is_bn: bool) -> str:
    if not isinstance(value, dict):
        return ""
    key = "name_bn" if is_bn else "name_en"
    return str(value.get(key) or value.get("name") or "")
