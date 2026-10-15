"""Local four-column documentation parsing with immutable source provenance."""

import hashlib
import io
import heapq
from pathlib import Path
import re
from difflib import SequenceMatcher

from fastapi import HTTPException
from app.services.preparation_import import (
    MAX_UPLOAD_BYTES,
    check_archive,
    checked_rows,
    invalid,
    preview_spreadsheet,
)

ALIASES = {
    "required_documentation": {
        "document required content",
        "document record required",
        "required report evidence",
        "required record report",
        "report evidence",
        "record report",
        "document evidence",
        "documentation required",
        "documentation",
        "title",
        "deliverable",
        "requested document",
        "request",
        "question",
        "description of document",
        "documentation requirement",
        "item",
    },
    "description": {
        "description",
        "details",
        "document description",
        "requirement",
        "wording",
        "request wording",
        "comment explanation",
        "comment",
        "explanation",
    },
    "document_name": {"document", "document name", "document title"},
    "category": {"category", "type", "document type", "area", "section"},
    "source_reference": {
        "source",
        "reference",
        "source reference",
        "requirement reference",
        "legal reference",
        "regulatory reference",
        "regulation",
        "id",
        "request id",
        "ref",
        "scp reference",
        "dga source and location",
    },
}
METADATA_ALIASES = {
    "notes",
    "note",
    "comments",
    "source aliases",
    "source alias",
    "aliases",
    "owner",
    "responsible",
    "status",
}


def normalise(value):
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def detect_header(rows):
    best = None
    for index, values in enumerate(rows[:30]):
        mapped = {}
        for column, value in enumerate(values):
            label = normalise(value)
            for key, aliases in ALIASES.items():
                if label in aliases and key not in mapped:
                    mapped[key] = column
        # A generic one-column Document list remains importable. In a four-column
        # list, the required-material heading always wins over the draft label.
        if "required_documentation" not in mapped and "document_name" in mapped:
            mapped["required_documentation"] = mapped.pop("document_name")
        if not ("required_documentation" in mapped or "description" in mapped):
            continue
        score = len(mapped) * 10 + sum(normalise(value) in METADATA_ALIASES for value in values)
        if best is None or score > best[0]:
            best = (score, index, mapped)
    return None if best is None else (best[1], best[2])


def row_from_values(
    name, row_number, values, headers, mapping, existing=(), *, candidate_texts=None
):
    """Keep the four source columns separate; only the compatibility title is clipped."""
    fields = {
        key: values[column] if column < len(values) else "" for key, column in mapping.items()
    }
    required = fields.get("required_documentation", fields.get("title"))
    if required is None:
        required = fields.get("description", "")
    if (
        not required.strip()
        or normalise(required) in METADATA_ALIASES
        or normalise(required) in {"notes and source aliases", "notes source aliases"}
    ):
        return None
    title = required.strip()[:500]
    if candidate_texts is None:
        candidate_texts = [
            (str(item.id), normalise(getattr(item, "required_documentation", None) or item.title))
            for item in existing
        ]
    candidates = []
    text = normalise(required)
    for id_, other in candidate_texts:
        matcher = SequenceMatcher(None, text, other)
        minimum = max(0.65, candidates[0][0] if len(candidates) == 5 else 0.65)
        if matcher.real_quick_ratio() < minimum or matcher.quick_ratio() < minimum:
            continue
        score = matcher.ratio()
        if score >= 0.65:
            heapq.heappush(candidates, (score, id_))
            if len(candidates) > 5:
                heapq.heappop(candidates)
    candidates.sort(reverse=True)
    return {
        "key": f"{name}:{row_number}",
        "sheet": name,
        "row_number": row_number,
        "required_documentation": required,
        "title": title,
        "description": fields.get("description", ""),
        "source_reference": fields.get("source_reference", ""),
        "document_name": fields.get("document_name", ""),
        "category": fields.get("category", name)[:100],
        "metadata": {
            headers[i] or f"column_{i + 1}": value
            for i, value in enumerate(values)
            if value and i not in mapping.values()
        },
        "original_title": required,
        "original_values": values,
        "original_headers": headers,
        "candidate_expectation_ids": [id_ for score, id_ in candidates[:5] if score >= 0.65],
    }


def workbook_sheets(content, filename):
    """Validate/open an XLSX once, retaining blank sheets and the shared reader limits."""
    if Path(filename).suffix.lower() != ".xlsx":
        return [preview_spreadsheet(content, filename, None)]
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Spreadsheet exceeds the 5 MiB upload limit")
    if not content:
        invalid("The spreadsheet is empty")
    from openpyxl import load_workbook

    try:
        check_archive(content)
        workbook = load_workbook(
            io.BytesIO(content), read_only=True, data_only=False, keep_links=False
        )
        try:
            result = []
            for sheet in workbook.worksheets:
                sheet.reset_dimensions()
                formulas = 0

                def values():
                    nonlocal formulas
                    for cells in sheet.iter_rows():
                        row = []
                        for cell in cells:
                            if cell.data_type == "f":
                                formulas += 1
                                row.append("")
                            else:
                                row.append(cell.value)
                        yield row

                try:
                    rows = checked_rows(values())
                except HTTPException as error:
                    if (
                        error.status_code != 422
                        or error.detail != "The selected sheet contains no text"
                    ):
                        raise
                    rows = []
                warnings = []
                if formulas:
                    warnings.append(
                        f"Skipped {formulas} formula cell(s). Paste their displayed text if needed."
                    )
                warnings.append(
                    "Preview includes cell text only. Checkboxes, images and page layout must be recreated in the form editor."
                )
                result.append({"sheet_name": sheet.title, "rows": rows, "warnings": warnings})
            if not result:
                invalid("The workbook has no worksheets")
            return result
        finally:
            workbook.close()
    except HTTPException:
        raise
    except Exception:
        invalid("Could not read this workbook. Save a valid .xlsx file and try again")


def build_import_preview(content, filename, existing=()):
    fingerprint = hashlib.sha256(content).hexdigest()
    sheets = workbook_sheets(content, filename)
    candidate_texts = [
        (str(item.id), normalise(getattr(item, "required_documentation", None) or item.title))
        for item in existing
    ]
    result = {
        "input_fingerprint": fingerprint,
        "filename": filename[:255],
        "sheets": [],
        "rows": [],
    }
    total_chars = 0
    for sheet in sheets:
        name = sheet["sheet_name"]
        if not sheet["rows"]:
            result["sheets"].append(
                {
                    "name": name,
                    "raw_rows": [],
                    "header_row": None,
                    "headers": [],
                    "included": False,
                    "warnings": ["This sheet contains no text."],
                }
            )
            continue
        rows = sheet["rows"]
        total_chars += sum(len(value) for row in rows for value in row)
        if total_chars > 2_000_000:
            raise HTTPException(413, "Workbook text exceeds the 2 million character limit")
        if normalise(name) in {"notes", "notes and sources", "notes sources", "sources"} or (
            rows and normalise(rows[0][0]) == "topic source code"
        ):
            result["sheets"].append(
                {
                    "name": name,
                    "raw_rows": rows,
                    "header_row": 1,
                    "headers": rows[0],
                    "included": False,
                    "warnings": [],
                    "metadata_rows": [
                        {"row_number": i + 1, "values": row} for i, row in enumerate(rows[1:], 1)
                    ],
                }
            )
            continue
        detected = detect_header(rows)
        warnings = list(sheet["warnings"])
        if not detected:
            result["sheets"].append(
                {
                    "name": name,
                    "raw_rows": rows,
                    "header_row": None,
                    "headers": [],
                    "included": False,
                    "warnings": warnings
                    + ["No document heading detected. Review this sheet manually."],
                }
            )
            continue
        index, mapping = detected
        headers = rows[index]
        result["sheets"].append(
            {
                "name": name,
                "raw_rows": rows,
                "header_row": index + 1,
                "headers": headers,
                "mapping": mapping,
                "included": True,
                "warnings": warnings,
                "preamble_rows": rows[:index],
            }
        )
        for row_number, values in enumerate(rows[index + 1 :], index + 2):
            row = row_from_values(
                name, row_number, values, headers, mapping, candidate_texts=candidate_texts
            )
            if row is not None:
                result["rows"].append(row)
            if len(result["rows"]) > 2000:
                raise HTTPException(413, "Workbook exceeds 2,000 document entries")
    return result
