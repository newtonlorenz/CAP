"""Exercise the parser boundary using the real application and streamed bodies."""

from unittest.mock import AsyncMock

import pytest
from starlette import formparsers

from app.config import settings
from app.main import app
from app.middleware.upload_limits import UploadLimitsMiddleware, upload_body_limit


PATHS = [
    ("/api/v1/documents", "max_document_upload_mb"),
    ("/api/v1/admin/backups/import", "backup_upload_max_mb"),
    ("/api/v1/requirements/00000000-0000-0000-0000-000000000001/files", "max_evidence_upload_mb"),
    ("/api/v1/review-cycles/00000000-0000-0000-0000-000000000001/items/00000000-0000-0000-0000-000000000002/files", "max_evidence_upload_mb"),
]


@pytest.mark.parametrize("path,setting", PATHS)
async def test_declared_oversized_upload_never_reads_or_parses_body(path, setting, monkeypatch):
    monkeypatch.setattr(settings, setting, 1)
    downstream = AsyncMock()
    receive = AsyncMock()
    send = AsyncMock()
    scope = {"type": "http", "method": "POST", "path": path,
             "headers": [(b"content-length", b"2097153")]}
    await UploadLimitsMiddleware(downstream)(scope, receive, send)
    assert send.call_args_list[0].args[0]["status"] == 413
    receive.assert_not_called()
    downstream.assert_not_called()


@pytest.mark.parametrize("claimed_length", [None, "1"])
async def test_stream_overflow_returns_413_and_closes_partial_files(client, monkeypatch, claimed_length):
    monkeypatch.setattr(settings, "max_document_upload_mb", 1)
    opened = []
    original = formparsers.SpooledTemporaryFile

    def tracked_file(*args, **kwargs):
        result = original(*args, **kwargs)
        opened.append(result)
        return result

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked_file)
    chunks_read = []

    async def stream():
        yield (b'--boundary\r\nContent-Disposition: form-data; name="file"; '
               b'filename="large.pdf"\r\nContent-Type: application/pdf\r\n\r\n')
        for index in range(8):
            chunks_read.append(index)
            yield b"x" * (512 * 1024)
        yield b"\r\n--boundary--\r\n"

    headers = {"Content-Type": "multipart/form-data; boundary=boundary"}
    if claimed_length:
        headers["Content-Length"] = claimed_length
    response = await client.post("/api/v1/documents", headers=headers, content=stream())
    assert response.status_code == 413, response.text
    assert len(chunks_read) == 4
    assert opened and all(file.closed for file in opened)


async def test_normal_upload_still_reaches_authentication(client):
    response = await client.post("/api/v1/documents", files={"file": ("small.pdf", b"%PDF")})
    assert response.status_code == 401


@pytest.mark.parametrize("headers", [
    [(b"content-length", b"-1")],
    [(b"content-length", b"invalid")],
    [(b"content-length", b"10"), (b"content-length", b"20")],
])
async def test_invalid_lengths_fail_before_read(headers):
    downstream, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
    await UploadLimitsMiddleware(downstream)(
        {"type": "http", "method": "POST", "path": "/api/v1/documents", "headers": headers},
        receive, send,
    )
    assert send.call_args_list[0].args[0]["status"] == 400
    receive.assert_not_called()
    downstream.assert_not_called()


def test_all_multipart_routes_have_a_pre_parser_limit():
    # New upload endpoints must choose a quota before they can parse a body.
    for route in app.routes:
        if not getattr(route, "body_field", None):
            continue
        if route.body_field.field_info.media_type == "multipart/form-data":
            scope = {"type": "http", "method": "POST", "path": route.path}
            assert upload_body_limit(scope) is not None, route.path


async def test_small_stream_is_unchanged():
    messages = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"def", "more_body": False},
    ]
    receive = AsyncMock(side_effect=messages)
    seen = []

    async def downstream(scope, receive, send):
        seen.extend([await receive(), await receive()])

    await UploadLimitsMiddleware(downstream)(
        {"type": "http", "method": "POST", "path": "/api/v1/documents/", "headers": []},
        receive, AsyncMock(),
    )
    assert seen == messages
