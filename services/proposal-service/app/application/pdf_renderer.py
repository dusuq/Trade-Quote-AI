"""Pure PDF rendering logic — given a fully-populated ProposalDocument,
produce branded PDF bytes. No I/O beyond the in-memory buffer; storage and
event-emission are the caller's job (see application/services.py).
"""

from __future__ import annotations

import io

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.domain.entities import ProposalDocument

PAGE_MARGIN = 0.75 * inch


def _qr_image_reader(url: str) -> io.BytesIO:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def render_proposal_pdf(doc: ProposalDocument) -> bytes:
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title=f"Proposal — {doc.customer.display_name}",
    )

    styles = getSampleStyleSheet()
    primary = colors.HexColor(doc.branding.primary_color)

    company_style = ParagraphStyle(
        "Company", parent=styles["Title"], textColor=primary, fontSize=20, spaceAfter=2
    )
    label_style = ParagraphStyle("ProposalLabel", parent=styles["Normal"], textColor=colors.grey)
    heading_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], textColor=primary, spaceBefore=14, spaceAfter=6
    )
    body_style = styles["BodyText"]
    signature_label_style = ParagraphStyle(
        "SignatureLabel", parent=styles["Normal"], fontSize=9, textColor=colors.grey
    )
    caption_style = ParagraphStyle(
        "Caption", parent=styles["Normal"], fontSize=8, textColor=colors.grey, alignment=TA_CENTER
    )

    story: list = []

    # --- Header / cover ---
    story.append(Paragraph(doc.branding.company_name, company_style))
    contact_bits = [b for b in (doc.branding.phone, doc.branding.email, doc.branding.website) if b]
    if contact_bits:
        story.append(Paragraph(" · ".join(contact_bits), label_style))
    story.append(Spacer(1, 18))
    story.append(Paragraph("PROPOSAL", ParagraphStyle("Big", parent=styles["Heading1"])))
    if doc.valid_until:
        story.append(Paragraph(f"Valid until {doc.valid_until}", label_style))
    story.append(Spacer(1, 12))

    # --- Customer / property ---
    story.append(Paragraph("Prepared For", heading_style))
    customer_lines = [doc.customer.display_name]
    if doc.customer.property_address:
        customer_lines.append(doc.customer.property_address)
    if doc.customer.phone:
        customer_lines.append(doc.customer.phone)
    if doc.customer.email:
        customer_lines.append(doc.customer.email)
    story.append(Paragraph("<br/>".join(customer_lines), body_style))

    # --- Scope of work ---
    story.append(Paragraph("Scope of Work", heading_style))
    story.append(Paragraph(doc.scope_of_work, body_style))

    # --- Line items table ---
    story.append(Paragraph("Materials &amp; Labor", heading_style))
    table_data = [["Description", "Qty", "Unit", "Unit Price", "Total"]]
    for item in doc.line_items:
        table_data.append(
            [
                item.description,
                f"{item.quantity:g}",
                item.unit,
                item.unit_price.formatted(),
                item.line_total.formatted(),
            ]
        )
    items_table = Table(table_data, colWidths=[2.6 * inch, 0.6 * inch, 0.7 * inch, 1 * inch, 1 * inch])
    items_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), primary),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(items_table)
    story.append(Spacer(1, 10))

    # --- Totals ---
    totals_data = [
        ["Subtotal", doc.subtotal.formatted()],
        ["Tax", doc.tax.formatted()],
        ["Total", doc.total.formatted()],
    ]
    totals_table = Table(totals_data, colWidths=[5.9 * inch, 1 * inch], hAlign="RIGHT")
    totals_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("FONTSIZE", (0, 2), (-1, 2), 12),
                ("LINEABOVE", (0, 2), (-1, 2), 1, primary),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(totals_table)

    # --- Warranty / terms ---
    if doc.warranty_text:
        story.append(Paragraph("Warranty", heading_style))
        story.append(Paragraph(doc.warranty_text, body_style))
    if doc.terms_text:
        story.append(Paragraph("Terms &amp; Conditions", heading_style))
        story.append(Paragraph(doc.terms_text, body_style))

    # --- Signature page ---
    story.append(PageBreak())
    story.append(Paragraph("Approval", heading_style))
    story.append(Spacer(1, 24))
    sig_rows = [
        [Paragraph("Customer Signature", signature_label_style), Paragraph("Date", signature_label_style)],
        ["_" * 40, "_" * 20],
        [Paragraph("Company Signature", signature_label_style), Paragraph("Date", signature_label_style)],
        ["_" * 40, "_" * 20],
    ]
    sig_table = Table(sig_rows, colWidths=[4.5 * inch, 2 * inch])
    sig_table.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 18)]))
    story.append(sig_table)

    if doc.qr_payload_url:
        story.append(Spacer(1, 24))
        qr_buf = _qr_image_reader(doc.qr_payload_url)
        story.append(Image(qr_buf, width=1.3 * inch, height=1.3 * inch))
        story.append(Paragraph("Scan to view &amp; pay online", caption_style))

    pdf.build(story)
    return buffer.getvalue()
