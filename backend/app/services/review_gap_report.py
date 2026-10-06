"""Presentation of a review's assessed gaps; classification stays in review_assurance."""
import html
import io
from collections import Counter
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


def summary_metrics(context):
    rows = context.rows
    applicable = [r for r in rows if r.requirement_status != "not_applicable"]
    gaps = [r for r in rows if r.needs_attention]
    return [
        ("Assessed requirements", len(rows)),
        ("Applicable controls", len(applicable)),
        ("Applicable controls ready", sum(not r.needs_attention for r in applicable)),
        ("Needs attention", len(gaps)),
        ("Evidence gaps", sum(r.requires_evidence for r in rows)),
        ("No evidence recorded", sum(bool(r.no_evidence_recorded) for r in rows)),
        ("Review decision / attribution gaps", sum(r.review_complete is False for r in rows)),
        ("Not applicable", len(rows) - len(applicable)),
        ("Informational sections (excluded)", context.informational_count),
        ("Overdue gaps", sum(bool(r.overdue) for r in gaps)),
        ("Gaps without a responsible owner", sum(not (r.responsible_user_name or r.responsible_user_email) for r in gaps)),
    ]


def owner_actions(context):
    groups = {}
    for row in context.rows:
        if row.needs_attention:
            groups.setdefault(row.owner_group_label, []).append(row)
    return [(owner, len(rows), sum(r.requires_evidence for r in rows),
             sum(r.review_complete is False for r in rows), sum(bool(r.overdue) for r in rows))
            for owner, rows in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0].lower()))]


def render_review_gap_pdf(context):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=40, rightMargin=40,
                            topMargin=46, bottomMargin=42, title=f"Gap analysis - {context.cycle.name}", author="CAP")
    ink, teal, muted = "#193345", "#087F79", "#526571"
    def style(name, size=9, leading=13, **kw):
        return ParagraphStyle(name, fontName="Helvetica", fontSize=size, leading=leading,
                              textColor=colors.HexColor(ink), spaceAfter=5, **kw)
    body = style("Body")
    small = style("Small", 8, 11)
    title = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=27, leading=31, textColor=colors.HexColor(ink), spaceAfter=12)
    heading = style("Section", 14, 19, spaceBefore=14, keepWithNext=True)
    item_heading = style("Item", 11, 15, spaceBefore=13, keepWithNext=True)
    label = style("Label", 8, 11, keepWithNext=True)
    intro = ParagraphStyle("Intro", parent=small, keepWithNext=True)
    white = ParagraphStyle("White", parent=small, textColor=colors.white, fontName="Helvetica-Bold")
    def p(value, st=body):
        return Paragraph(html.escape(str(value)), st)
    def table(headers, rows, widths):
        data = [[p(h, white) for h in headers]] + [[p(cell, small) for cell in row] for row in rows]
        result = Table(data, colWidths=widths, repeatRows=1, splitInRow=1, hAlign="LEFT")
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(ink)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6F7")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, -1), (-1, -1), .4, colors.HexColor("#CAD7DD")),
        ]))
        return result
    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    cycle = context.cycle
    frozen = f"Frozen assessment: {cycle.closed_at.strftime('%d %b %Y, %H:%M UTC')}" if cycle.closed_at else "Live assessment at export"
    deadline = cycle.deadline.strftime("%d %b %Y") if cycle.deadline else "Not set"
    metrics = dict(summary_metrics(context))
    gaps = [r for r in context.rows if r.needs_attention]
    story = [p("Review gap analysis", title), p(cycle.name, heading),
             p(f"{context.jurisdiction.name}  |  {context.scope_label}  |  Deadline: {deadline}", body),
             p(f"{frozen}  |  Generated {generated}", small), Spacer(1, 12)]
    metric_cells = []
    for name in ["Applicable controls ready", "Needs attention", "Overdue gaps"]:
        metric_cells.append([Paragraph(f'<font size="23" color="{teal}"><b>{metrics[name]}</b></font>', style("Metric", 23, 27)), p(name, small)])
    strip = Table([metric_cells], colWidths=[doc.width / 3] * 3)
    strip.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF6F5")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 14), ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("LEFTPADDING", (0, 0), (-1, -1), 12)]))
    story += [strip, p("Scope and readiness", heading),
              p(f"{len(context.rows)} assessed requirements: {metrics['Applicable controls']} applicable and {metrics['Not applicable']} not applicable. {context.informational_count} informational sections are excluded from gap and readiness counts."),
              p("A requirement needs attention while its assessment status or review decision is unfinished, or its not-applicable rationale is missing. An empty evidence record is counted separately and does not reopen an evidenced, confirmed assessment. Counts can overlap because one requirement may have several gaps.", small),
              p("Priorities show escalations first, then blocked work, overdue gaps and other open items. Unassigned ownership is reported separately from completion blockers.", small),
              table(["Assessment measure", "Requirements"], [(key, value) for key, value in summary_metrics(context) if key in {"Evidence gaps", "No evidence recorded", "Review decision / attribution gaps", "Gaps without a responsible owner"}], [doc.width * .75, doc.width * .25]),
              p("Outstanding work by responsible person", heading)]
    if gaps:
        story.append(table(["Responsible person", "Open", "Evidence", "Review", "Overdue"], owner_actions(context), [doc.width * .48] + [doc.width * .13] * 4))
    else:
        story.append(p("No outstanding gaps. All assessed requirements satisfy the review completion checks."))
    story += [p("Requirement and decision status", heading),
              table(["Requirement status", "Count", "Review decision", "Count"], _status_rows(context), [doc.width * .37, doc.width * .13, doc.width * .37, doc.width * .13]),
              p("This report records internal review readiness. It does not constitute certification or regulator approval.", small)]
    if gaps:
        story += [PageBreak(), p("Outstanding actions", title), p("Every item below needs attention. Use its review link to open the assessment in CAP.", small)]
        for index, row in enumerate(gaps, 1):
            story += [p(f"{index}. {row.reference_id} - {row.title or row.document_name}", item_heading),
                      p(f"{row.priority.upper()}  |  {row.document_name}" + (f"  |  Baseline v{row.baseline_version}" if row.baseline_version else ""), intro),
                      p(f"Responsible: {row.responsible_user_label}  |  Reviewer: {row.assigned_reviewer_label}", intro),
                      p(f"Assessment: {row.requirement_status.replace('_', ' ').title()}  |  Decision: {row.review_status.title()}  |  Deadline: {deadline}", intro)]
            for reason in row.gap_reasons:
                story.append(Paragraph(f'<font color="{teal}"><b>Action:</b></font> {html.escape(reason)}', body))
            if row.unassigned:
                story.append(p("Ownership: assign a responsible person to coordinate the outstanding work.", small))
            story.append(p("Requirement", label))
            story.append(p(row.requirement_text or "No requirement text recorded."))
            story.append(p("Recorded evidence / applicability rationale", label))
            story.append(p(row.review_evidence or "No evidence reference or rationale recorded."))
            story.append(p(f"Attachments ({row.evidence_file_count or '0'}): {row.evidence_file_names or 'None recorded'}", small))
            if row.latest_comment:
                story += [p("Latest comment", label), p(row.latest_comment)]
            if row.jira_issue_key:
                story.append(p(f"Linked issue: {row.jira_issue_key} - {row.jira_status or 'status unavailable'}", small))
            if row.review_link.startswith(("http://", "https://")):
                story.append(Paragraph(f'<link href="{html.escape(row.review_link, quote=True)}" color="{teal}"><u>Open {html.escape(row.reference_id)} in CAP</u></link>', small))
            story.append(Spacer(1, 10))
    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CAD7DD")); canvas.line(40, 35, A4[0] - 40, 35)
        canvas.setFont("Helvetica", 8); canvas.setFillColor(colors.HexColor(muted))
        canvas.drawString(40, 23, "CAP  /  Review gap analysis")
        canvas.drawRightString(A4[0] - 40, 23, f"Page {document.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _status_rows(context):
    requirement = sorted(Counter(r.requirement_status for r in context.rows).items())
    review = sorted(Counter(r.review_status for r in context.rows).items())
    result = []
    for index in range(max(len(requirement), len(review))):
        left = requirement[index] if index < len(requirement) else ("", "")
        right = review[index] if index < len(review) else ("", "")
        result.append([left[0].replace("_", " ").title(), left[1], right[0].title(), right[1]])
    return result
