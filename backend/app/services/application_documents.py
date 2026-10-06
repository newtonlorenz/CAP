"""Readable, portable views of the exact record retained at application approval."""

import csv
import html
import io
from urllib.parse import quote, urlsplit

from app.services.preparation_export import _csv_value
from app.services.preparation_files import clean_filename


def _text(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _escape(value):
    return html.escape(_text(value), quote=True)


def build_application_documents(record: dict) -> dict[str, bytes]:
    """Never fetch external links or emit executable markup from stored answers."""
    application = record["application"]
    components = record.get("components", [])
    evidence = record.get("evidence", [])
    evidence_by_id = {item["id"]: item for item in evidence}
    csv_output = io.StringIO(newline="")
    writer = csv.writer(csv_output)
    writer.writerow(
        [
            "Component",
            "Form",
            "Section",
            "Reference",
            "Question",
            "Required",
            "Response",
            "Not applicable reason",
            "Accepted at",
            "Evidence IDs",
        ]
    )
    parts = [
        '<!doctype html><html lang="en"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{_escape(application["name"])}</title>',
        ("<style>body{font:15px/1.5 system-ui,sans-serif;color:#17212b;max-width:1000px;"
        "margin:40px auto;padding:0 24px}h1,h2,h3{line-height:1.2}h2{margin-top:32px;"
        "border-bottom:1px solid #ccd3d8;padding-bottom:8px}table{border-collapse:collapse;"
        "width:100%;margin:12px 0}th,td{padding:10px;text-align:left;vertical-align:top;"
        "border:1px solid #ccd3d8;overflow-wrap:anywhere}th{background:#f0f3f5}"
        "h4{white-space:pre-wrap;overflow-wrap:anywhere}.answer{white-space:pre-wrap;overflow-wrap:anywhere}.meta{color:#455462}"
        "article{break-inside:avoid}a{color:#145a84}@media print{body{margin:0;"
        "max-width:none;font-size:11pt}h2,h3{break-after:avoid}a{color:inherit}}</style>"),
        f'<body><h1>{_escape(application["name"])}</h1>',
        (f'<p class="meta">Approved pack version {_escape(record.get("version"))} · '
        f'{_escape(record.get("approved_at"))}</p>'),
        ("<p>This is the internally approved pack. Downloading or printing it does not "
        "submit it to an authority. Use the authority’s required forms and submission channel.</p>"),
        "<table><tbody>",
    ]
    for label, key in [
        ("Scope", "scope"),
        ("Applicant", "applicant"),
        ("Authority", "authority"),
        ("Jurisdiction reference", "jurisdiction_id"),
        ("Deadline", "due_date"),
        ("Description", "description"),
    ]:
        value = application.get(key)
        if key == "scope":
            value = {
                "annex_only": "Annexes only",
                "licence": "Licence application",
                "full_pack": "Full application pack",
            }.get(value, value)
        parts.append(f'<tr><th>{label}</th><td class="answer">{_escape(value)}</td></tr>')
    parts.append(
        "</tbody></table><h2>Included components</h2><table><thead><tr>"
        "<th>Name</th><th>Type</th><th>Required</th><th>Deadline</th>"
        "</tr></thead><tbody>"
    )
    for component in components:
        parts.append(
            "<tr>"
            + "".join(
                f"<td>{_escape(value)}</td>"
                for value in [
                    component["name"],
                    component["kind"],
                    component["required"],
                    component.get("due_date"),
                ]
            )
            + "</tr>"
        )
    parts.append("</tbody></table><h2>Forms and annexes</h2>")
    for form in record.get("forms", []):
        names = "; ".join(item["name"] for item in components if item.get("case_id") == form["id"])
        parts.append(
            f'<h3>{_escape(names or form["name"])}</h3><p class="meta">'
            f'{_escape(form.get("template_name"))} · template version '
            f'{_escape(form.get("template_revision"))} · form revision '
            f'{_escape(form.get("revision"))}</p>'
        )
        responses = {answer["field_key"]: answer for answer in form.get("responses", [])}
        for field in form.get("fields", []):
            response = responses.get(field["key"], {})
            ids = response.get("evidence_ids", [])
            writer.writerow(
                [
                    _csv_value(value)
                    for value in [
                        names,
                        form["name"],
                        field.get("section"),
                        field["key"],
                        field["label"],
                        field.get("required"),
                        response.get("value"),
                        response.get("not_applicable_reason"),
                        response.get("accepted_at"),
                        "; ".join(ids),
                    ]
                ]
            )
            parts.append(
                f'<article><h4>{_escape(field.get("section"))} · '
                f'{_escape(field["key"])} — {_escape(field["label"])}</h4>'
            )
            if field.get("help_text"):
                parts.append(f'<p class="answer meta">{_escape(field["help_text"])}</p>')
            parts.append(f'<p class="answer">{_escape(response.get("value"))}</p>')
            if response.get("not_applicable_reason"):
                parts.append(
                    '<p class="answer">Not applicable: '
                    f'{_escape(response["not_applicable_reason"])}</p>'
                )
            parts.append(
                f'<p class="meta">Required: {_escape(field.get("required"))} · '
                f'Accepted at: {_escape(response.get("accepted_at"))}</p>'
            )
            if ids:
                parts.append(
                    "<p>Evidence: "
                    + ", ".join(
                        f'<a href="#evidence-{quote(key, safe="")}">'
                        f'{_escape(evidence_by_id.get(key, {}).get("title", key))}</a>'
                        for key in ids
                    )
                    + "</p>"
                )
            parts.append("</article>")
    parts.append("<h2>Supporting information</h2>")
    for item in evidence:
        parts.append(
            f'<article id="evidence-{quote(item["id"], safe="")}">'
            f'<h3>{_escape(item["title"])}</h3>'
        )
        related = [part["name"] for part in components if part.get("evidence_id") == item["id"]]
        if related:
            parts.append(f'<p>Component: {_escape("; ".join(related))}</p>')
        if item.get("body"):
            parts.append(f'<p class="answer">{_escape(item["body"])}</p>')
        if item.get("link_url"):
            url = item["link_url"]
            # The API validates links, but the export renderer also treats its input as data.
            if urlsplit(url).scheme.lower() in {"http", "https"}:
                parts.append(
                    f'<p><a rel="noreferrer noopener" href="{html.escape(url, quote=True)}">'
                    f"{_escape(url)}</a></p>"
                )
            else:
                parts.append(f"<p>{_escape(url)}</p>")
        if item["kind"] == "file":
            path = f'evidence/{item["id"]}/{clean_filename(item.get("filename"))}'
            parts.append(
                f'<p><a href="{quote(path, safe="/")}">' f'{_escape(item.get("filename"))}</a></p>'
            )
        parts.append(
            f'<p class="meta">Valid from: {_escape(item.get("valid_from"))} · '
            f'Valid until: {_escape(item.get("valid_until"))}</p></article>'
        )
    if record.get("followups"):
        parts.append("<h2>Follow-up responses</h2>")
        for item in record["followups"]:
            parts.append(
                f'<article><h3>{_escape(item["question"])}</h3>'
                f'<p class="answer">{_escape(item.get("response"))}</p>'
                f'<p class="meta">Status: {_escape(item["status"])} · '
                f'Deadline: {_escape(item.get("due_date"))} · '
                f'Resolved at: {_escape(item.get("resolved_at"))}</p>'
            )
            for key in item.get("evidence_ids", []):
                parts.append(
                    f'<p><a href="#evidence-{quote(key, safe="")}">'
                    f'{_escape(evidence_by_id.get(key, {}).get("title", key))}</a></p>'
                )
            parts.append("</article>")
    parts.append("</body></html>")
    return {
        "responses.csv": csv_output.getvalue().encode("utf-8-sig"),
        "application.html": "\n".join(parts).encode("utf-8"),
    }
