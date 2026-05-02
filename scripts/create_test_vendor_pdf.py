from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER

def create_vendor_pdf(output_path: str):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=25*mm,
        leftMargin=25*mm,
        topMargin=25*mm,
        bottomMargin=25*mm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title', parent=styles['Heading1'],
        fontSize=16, spaceAfter=12, alignment=TA_CENTER
    )
    h2_style = ParagraphStyle(
        'H2', parent=styles['Heading2'],
        fontSize=13, spaceAfter=8, spaceBefore=16
    )
    h3_style = ParagraphStyle(
        'H3', parent=styles['Heading3'],
        fontSize=11, spaceAfter=6, spaceBefore=12
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontSize=10, spaceAfter=6, leading=14
    )

    story = []

    # Cover page
    story.append(Spacer(1, 30*mm))
    story.append(Paragraph("VENDOR PROPOSAL", title_style))
    story.append(Paragraph("IT Managed Services — Response to RFP-2026-IT-001", title_style))
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph("Submitted by: Apex Technology Solutions Ltd", body_style))
    story.append(Paragraph("Date: 15 April 2026", body_style))
    story.append(Paragraph("Reference: ATS-RFP-2026-001", body_style))
    story.append(Spacer(1, 20*mm))

    # Section 1 - Company Overview
    story.append(Paragraph("1. Company Overview", h2_style))
    story.append(Paragraph(
        "Apex Technology Solutions Ltd is a UK-based managed IT services provider "
        "established in 2009 with headquarters in Manchester and regional offices in "
        "London, Birmingham, and Edinburgh. We employ 340 full-time staff across our "
        "four UK locations with a dedicated service desk team of 85 engineers.",
        body_style
    ))
    story.append(Paragraph(
        "Our annual turnover for the financial year ending March 2026 was £42.3 million, "
        "representing 18% year-on-year growth. We currently serve 94 enterprise clients "
        "across financial services, healthcare, and public sector verticals.",
        body_style
    ))

    # Section 2 - Certifications
    story.append(Paragraph("2. Certifications and Compliance", h2_style))

    story.append(Paragraph("2.1 Information Security", h3_style))
    story.append(Paragraph(
        "Apex Technology Solutions Ltd holds current ISO 27001:2022 certification "
        "for information security management, issued by BSI Group (Certificate number "
        "IS 123456) covering all UK operations. Our certification was last audited in "
        "January 2026 and is valid until March 2028.",
        body_style
    ))

    story.append(Paragraph("2.2 Service Management", h3_style))
    story.append(Paragraph(
        "We hold ISO 20000-1:2018 certification for IT service management, "
        "demonstrating our commitment to delivering consistent, high-quality "
        "managed services. Certificate issued by Lloyd's Register, valid until "
        "September 2027.",
        body_style
    ))

    story.append(Paragraph("2.3 Quality Management", h3_style))
    story.append(Paragraph(
        "Our operations are certified to ISO 9001:2015 quality management standards, "
        "covering all service delivery, project management, and support functions.",
        body_style
    ))

    # Section 3 - Insurance
    story.append(Paragraph("3. Insurance", h2_style))
    story.append(Paragraph(
        "Apex Technology Solutions Ltd maintains the following insurance coverage:",
        body_style
    ))

    insurance_data = [
        ['Insurance Type', 'Coverage Amount', 'Provider', 'Expiry'],
        ['Professional Indemnity', '£10,000,000', 'Hiscox UK', 'December 2026'],
        ['Public Liability', '£5,000,000', 'Zurich Insurance', 'December 2026'],
        ['Cyber Liability', '£2,000,000', 'AXA XL', 'October 2026'],
        ['Employers Liability', '£10,000,000', 'Aviva', 'December 2026'],
    ]
    insurance_table = Table(insurance_data, colWidths=[120, 100, 100, 80])
    insurance_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.lightgrey]),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(insurance_table)
    story.append(Spacer(1, 6*mm))

    # Section 4 - Service Level Agreements
    story.append(Paragraph("4. Service Level Agreements", h2_style))
    story.append(Paragraph(
        "We commit to the following service level agreements for all priority incidents:",
        body_style
    ))

    sla_data = [
        ['Priority', 'Definition', 'Response Time', 'Resolution Time'],
        ['P1 Critical', 'Complete service outage', '15 minutes', '4 hours'],
        ['P2 High', 'Major degradation', '30 minutes', '8 hours'],
        ['P3 Medium', 'Partial impact', '2 hours', '24 hours'],
        ['P4 Low', 'Minimal impact', '4 hours', '72 hours'],
    ]
    sla_table = Table(sla_data, colWidths=[70, 130, 90, 90])
    sla_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.lightgrey]),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(sla_table)
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        "Our guaranteed uptime for all managed infrastructure is 99.95% measured "
        "monthly, excluding scheduled maintenance windows agreed in advance with "
        "the client.",
        body_style
    ))

    # Section 5 - Relevant Experience
    story.append(Paragraph("5. Relevant Experience and Client References", h2_style))

    story.append(Paragraph("5.1 NHS Foundation Trust — IT Managed Services", h3_style))
    story.append(Paragraph(
        "We have provided full IT managed services to a major NHS Foundation Trust "
        "since 2021, supporting 4,200 end users across 8 hospital sites. The contract "
        "value is £3.2 million per annum. We delivered a 94% first-call resolution rate "
        "and reduced average ticket resolution time from 18 hours to 6.5 hours within "
        "the first year. A reference is available upon request.",
        body_style
    ))

    story.append(Paragraph("5.2 Regional Local Authority — Digital Transformation", h3_style))
    story.append(Paragraph(
        "We delivered a three-year digital transformation programme for a regional "
        "local authority with 2,800 staff, migrating legacy infrastructure to Microsoft "
        "Azure and implementing a modern service desk. Project completed on time and "
        "4% under budget at £1.8 million total value.",
        body_style
    ))

    story.append(Paragraph("5.3 Financial Services Firm — Cybersecurity Programme", h3_style))
    story.append(Paragraph(
        "We implemented a comprehensive cybersecurity programme for a mid-size "
        "financial services firm with 650 employees, achieving ISO 27001 certification "
        "within 14 months and reducing security incidents by 78%. Contract value "
        "£920,000 over two years.",
        body_style
    ))

    # Section 6 - Commercial Proposal
    story.append(Paragraph("6. Commercial Proposal", h2_style))
    story.append(Paragraph(
        "Our pricing proposal for the three-year managed services contract is as follows:",
        body_style
    ))

    pricing_data = [
        ['Service Component', 'Year 1', 'Year 2', 'Year 3'],
        ['Service Desk (24x7)', '£420,000', '£432,600', '£445,578'],
        ['Infrastructure Management', '£280,000', '£288,400', '£297,052'],
        ['Security Operations', '£180,000', '£185,400', '£190,962'],
        ['Project Management', '£95,000', '£97,850', '£100,786'],
        ['TOTAL', '£975,000', '£1,004,250', '£1,034,378'],
    ]
    pricing_table = Table(pricing_data, colWidths=[160, 80, 80, 80])
    pricing_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.lightblue),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.lightgrey]),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(pricing_table)
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        "All prices are exclusive of VAT. Year 2 and Year 3 pricing includes a "
        "contractual annual increase of 3% in line with CPI. The total three-year "
        "contract value is £3,013,628 exclusive of VAT.",
        body_style
    ))

    # Section 7 - UK Presence
    story.append(Paragraph("7. UK Presence and Service Delivery", h2_style))
    story.append(Paragraph(
        "Our primary service desk is located in Manchester, United Kingdom, operating "
        "24 hours per day, 7 days per week, 365 days per year. All service desk "
        "engineers are based in the UK with no offshore delivery. Our Manchester "
        "facility holds ISO 27001 certification and operates under UK GDPR compliance.",
        body_style
    ))

    doc.build(story)
    print(f"PDF created: {output_path}")
    print("Document contains:")
    print("  - Company overview (340 staff, £42.3M turnover)")
    print("  - ISO 27001:2022 certification (BSI, valid to March 2028)")
    print("  - ISO 20000-1 and ISO 9001 certifications")
    print("  - Professional indemnity £10M (Hiscox)")
    print("  - P1 SLA: 15 min response, 4 hour resolution")
    print("  - 99.95% uptime guarantee")
    print("  - 3 client references with contract values")
    print("  - 3-year pricing: £975K / £1.004M / £1.034M")
    print("  - UK-only service desk in Manchester")

if __name__ == "__main__":
    create_vendor_pdf("data/documents/test_vendor_apex.pdf")
