from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid
import pytest
from fastapi import HTTPException
from app.services.source_validation import structure_errors, validate_extraction_complete
from app.services.pdf_worker import bounded_preprocess


def row(
    ref="3.1", text="The operator shall retain records.", kind="mandatory", parent=None, id=None
):
    return SimpleNamespace(
        id=id or uuid.uuid4(), reference_id=ref, text=text, requirement_type=kind, parent_id=parent
    )


def test_source_structure_catches_duplicates_cycles_and_empty_obligations():
    parent = row()
    child = row("3.1", text="<p><br></p>", parent=parent.id)
    parent.parent_id = child.id
    errors = structure_errors([parent, child])
    assert any("Duplicate" in message for message in errors)
    assert any("circular" in message for message in errors)
    assert any("empty" in message for message in errors)
    assert any("outside" in message for message in structure_errors([row(parent=uuid.uuid4())]))


@pytest.mark.parametrize(
    "status,total,current",
    [("running", 25, 4), ("failed", 25, 25), ("completed", 25, 24), ("completed", 0, 0)],
)
async def test_cannot_publish_incomplete_extraction(status, total, current):
    doc = SimpleNamespace(id=uuid.uuid4(), current_extraction_id=uuid.uuid4())
    db = SimpleNamespace(
        refresh=AsyncMock(),
        get=AsyncMock(
            return_value=SimpleNamespace(
                document_id=doc.id, status=status, total_pages=total, current_page=current
            )
        )
    )
    with pytest.raises(HTTPException) as error:
        await validate_extraction_complete(db, doc)
    assert error.value.status_code == 409


async def test_pdf_preprocessor_rejects_invalid_source_in_subprocess(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF broken")
    with pytest.raises(ValueError, match="preprocessing failed"):
        await bounded_preprocess(str(bad), "standard")


def test_scp_heading_does_not_downgrade_numbered_obligations():
    from app.services.ai_parser import parse_requirements_rule_based

    source = """3.1.1 Terms and conditions
1 The base platform shall require customers to accept the terms on registration.
2 The base platform may only allow customers to play after accepting the terms.
3 The operator should provide a readable summary.
"""
    rows = {
        r["reference_id"]: r for r in parse_requirements_rule_based(source, "standard", 10)
    }
    assert rows["3.1.1"]["requirement_type"] == "informational"
    assert rows["3.1.1.1"]["requirement_type"] == "mandatory"
    assert rows["3.1.1.2"]["requirement_type"] == "mandatory"
    assert rows["3.1.1.3"]["requirement_type"] == "recommended"


def test_layout_merge_preserves_cross_page_numbered_controls():
    from app.services.pdf_preprocessor import _merge_layout_and_native
    from app.services.ai_parser import parse_requirements_rule_based

    text = "4 The base platform shall generate registration reports.\n5 The platform shall report suspended accounts."
    pages = _merge_layout_and_native(
        [{"page_number": 18, "text": text}],
        [{"page_number": 18, "text": "[SECTION_CONTINUATION:3.5.1]\n" + text}],
    )
    rows = parse_requirements_rule_based(pages[0]["text"], "standard", 18)
    assert {r["reference_id"] for r in rows} == {"3.5.1.4", "3.5.1.5"}
    assert all(
        r["requirement_type"] == "mandatory" and r["parent_reference"] == "3.5.1" for r in rows
    )


def test_continuation_does_not_reclassify_parent_and_test_marker_is_mandatory():
    from app.services.ai_parser import parse_requirements_rule_based

    rows = parse_requirements_rule_based(
        "[SECTION_CONTINUATION:3.2.8]\n4 [TEST] A suspension entails that the customer is unable to make deposits.",
        "standard",
        14,
    )
    assert len(rows) == 1
    assert rows[0]["reference_id"] == "3.2.8.4"
    assert rows[0]["requirement_type"] == "mandatory"


@pytest.mark.parametrize("reference, section, remaining", [
    ("2.2.1", "2.2.1", "2.2.2\nPersonnel requirements"),
    ("3.2.5.2", "3.2.5", "3 [TEST] The platform shall keep records."),
])
def test_page_continuation_keeps_prose_and_table_tails(reference, section, remaining):
    from app.tasks.extraction import attach_page_continuation
    entry = SimpleNamespace(text="The platform shall follow the", original_text="", source_excerpt="")
    text = f"[SECTION_CONTINUATION:{section}]\ncertification programme. The report shall include accreditation.\n{remaining}"
    rest = attach_page_continuation(text, {reference: entry})
    assert entry.text.endswith("certification programme. The report shall include accreditation.")
    assert entry.source_excerpt == entry.original_text == entry.text
    assert "certification programme" not in rest
    assert remaining in rest


def test_scp_nested_numbered_lists_stay_with_their_own_table_control():
    from app.services.ai_parser import parse_requirements_rule_based
    rows = parse_requirements_rule_based("""3.2.3 Electronic ID
1 The platform shall use electronic ID when:
1) Creating an account
2) Approving a new device
3) Changing identity details
Guidance: This does not apply without a CPR number.
2 The platform must retain records for at least
90 days after the game.
3 The platform must use strong authentication when:
1) Depositing
2) Withdrawing
3) Changing payment instruments
""", "standard", 12)
    by_ref = {r["reference_id"]: r["text"] for r in rows}
    assert "Approving a new device" in by_ref["3.2.3.1"]
    assert "CPR number" in by_ref["3.2.3.1"]
    assert "Depositing" not in by_ref["3.2.3.1"]
    assert by_ref["3.2.3.2"] == "The platform must retain records for at least 90 days after the game."
    assert "3.2.3.90" not in by_ref
    assert "Withdrawing" in by_ref["3.2.3.3"]
