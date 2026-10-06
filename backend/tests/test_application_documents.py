import csv
import io

from app.services.application_documents import build_application_documents


def test_readable_application_export_preserves_answers_and_escapes_untrusted_content():
    record = {
        "application": {"name": "Annex <script>alert(1)</script>", "scope": "annex_only"},
        "version": 2,
        "approved_at": "2026-09-29T12:00:00+00:00",
        "components": [{"name": "Annex B", "kind": "annex", "required": True, "case_id": "case-1"}],
        "forms": [
            {
                "id": "case-1",
                "name": "Annex B answers",
                "template_name": "Example annex",
                "template_revision": 1,
                "fields": [
                    {"key": "name", "label": "Company", "required": True},
                    {"key": "zero", "label": "Count", "required": True},
                    {"key": "no", "label": "Yes or no", "required": True},
                ],
                "responses": [
                    {
                        "field_key": "name",
                        "value": '=HYPERLINK("https://example.test")',
                        "evidence_ids": ["ev-1"],
                    },
                    {"field_key": "zero", "value": 0},
                    {
                        "field_key": "no",
                        "value": False,
                        "not_applicable_reason": "Reason <img src=x>",
                    },
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-1",
                "title": "Supporting file",
                "kind": "file",
                "filename": "Annex & notes.txt",
                "body": "Safe <script>text</script>",
            },
            {
                "id": "ev-2",
                "title": "Unsafe link",
                "kind": "link",
                "link_url": "javascript:alert(1)",
            },
        ],
        "followups": [
            {
                "question": "Authority question",
                "response": "Follow-up answer",
                "status": "resolved",
                "evidence_ids": ["ev-1"],
            }
        ],
    }
    documents = build_application_documents(record)
    rows = list(csv.DictReader(io.StringIO(documents["responses.csv"].decode("utf-8-sig"))))
    assert [row["Response"] for row in rows] == [
        '\'=HYPERLINK("https://example.test")',
        "0",
        "false",
    ]
    assert rows[0]["Component"] == "Annex B"
    assert rows[0]["Evidence IDs"] == "ev-1"
    page = documents["application.html"].decode()
    assert "<script>" not in page and "<img src=x>" not in page
    assert 'href="javascript:' not in page
    assert "&lt;script&gt;" in page
    assert "Annex%20%26%20notes.txt" in page
    assert "Follow-up answer" in page
    assert 'href="#evidence-ev-1"' in page
    assert "Approved pack version 2" in page
