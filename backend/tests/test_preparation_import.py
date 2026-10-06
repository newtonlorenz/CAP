import io
import zipfile
from datetime import date

import pytest
from app.models import User
from app.services.auth import create_access_token
from openpyxl import Workbook

URL = "/api/v1/preparation/templates/import-preview"


@pytest.fixture
async def import_headers(db_session):
    users = {}
    for role in ("manager", "contributor"):
        user = User(
            email=f"import-{role}@example.com",
            password_hash="unused",
            full_name=role,
            role=role,
            active=True,
        )
        db_session.add(user)
        await db_session.flush()
        users[role] = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
    await db_session.commit()
    return users


def workbook_bytes():
    workbook = Workbook()
    workbook.active.title = "Cover"
    workbook.active.append(["Application instructions"])
    sheet = workbook.create_sheet("Questions")
    sheet.append(["Reference", "Question", "Date", "Formula"])
    sheet.append(["1.1", "Applicant’s name\nAs registered", date(2026, 9, 29), "=1+1"])
    sheet.append([])
    sheet.append(["1.2", "Confirm the declaration ☐"])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


async def test_workbook_preview_preserves_rows_and_does_not_create_template(client, import_headers):
    response = await client.post(
        URL,
        files={"file": ("form.xlsx", workbook_bytes())},
        data={"sheet_name": "Questions"},
        headers=import_headers["manager"],
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["sheets"] == ["Cover", "Questions"]
    assert preview["sheet_name"] == "Questions"
    assert preview["rows"] == [
        ["Reference", "Question", "Date", "Formula"],
        ["1.1", "Applicant’s name\nAs registered", "2026-09-29T00:00:00", ""],
        ["", "", "", ""],
        ["1.2", "Confirm the declaration ☐", "", ""],
    ]
    assert any("formula" in warning.lower() for warning in preview["warnings"])
    assert (await client.get(URL.rsplit("/", 1)[0], headers=import_headers["manager"])).json()[
        "total"
    ] == 0


@pytest.mark.parametrize(
    "filename,content,expected",
    [
        (
            "form.csv",
            b'Question,Help\r\n"First, question","Line one\nLine two"\r\n=1+1,Literal',
            [["Question", "Help"], ["First, question", "Line one\nLine two"], ["=1+1", "Literal"]],
        ),
        (
            "form.tsv",
            "\ufeffQuestion\tReference\nName\t1.1".encode(),
            [["Question", "Reference"], ["Name", "1.1"]],
        ),
        ("form.csv", b"Question;Reference\nName;1.1", [["Question", "Reference"], ["Name", "1.1"]]),
    ],
)
async def test_delimited_preview(client, import_headers, filename, content, expected):
    response = await client.post(
        URL, files={"file": (filename, content)}, headers=import_headers["manager"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["rows"] == expected


async def test_preview_requires_template_management_role(client, import_headers):
    for headers, expected in [({}, 401), (import_headers["contributor"], 403)]:
        response = await client.post(
            URL, files={"file": ("form.csv", b"Question\nName")}, headers=headers
        )
        assert response.status_code == expected


@pytest.mark.parametrize(
    "filename,content,status",
    [
        ("form.xls", b"old workbook", 422),
        ("form.xlsx", b"not a zip", 422),
        ("form.csv", b"\xff\xfeinvalid", 422),
        ("form.csv", b"", 422),
        ("form.csv", b"x\n" * 2001, 422),
        ("form.csv", b",".join([b"x"] * 51), 422),
        ("form.csv", b"x" * 10001, 422),
        ("form.csv", (b"x" * 10000 + b"\n") * 201, 422),
        ("form.csv", b"x" * (5 * 1024 * 1024 + 1), 413),
    ],
)
async def test_preview_rejects_unsupported_malformed_or_oversized_input(
    client, import_headers, filename, content, status
):
    response = await client.post(
        URL, files={"file": (filename, content)}, headers=import_headers["manager"]
    )
    assert response.status_code == status, response.text


async def test_preview_rejects_missing_sheet(client, import_headers):
    response = await client.post(
        URL,
        files={"file": ("form.xlsx", workbook_bytes())},
        data={"sheet_name": "Missing"},
        headers=import_headers["manager"],
    )
    assert response.status_code == 422
    assert "sheet" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "member,contents",
    [
        ("xl/sharedStrings.xml", b"x" * (20 * 1024 * 1024 + 1)),
        ("xl/sharedStrings.xml", b'<!DOCTYPE a [<!ENTITY x "expansion">]><a>&x;</a>'),
        (
            "xl/worksheets/sheet1.xml",
            b'<worksheet><sheetData><row r="1"><c r="ZZZ1"/></row></sheetData></worksheet>',
        ),
    ],
)
async def test_preview_bounds_workbook_expansion_and_xml(client, import_headers, member, contents):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, contents)
    response = await client.post(
        URL, files={"file": ("form.xlsx", output.getvalue())}, headers=import_headers["manager"]
    )
    assert response.status_code == 422, response.text
    assert any(word in response.json()["detail"].lower() for word in ("large", "limit", "xml"))
