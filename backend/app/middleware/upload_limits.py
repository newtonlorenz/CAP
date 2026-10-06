"""Bound upload bodies before multipart parsing, including chunked requests."""

import re

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings


_EVIDENCE_PATH = re.compile(
    r"/api/v1/(?:requirements/[^/]+/files|review-cycles/[^/]+/items/[^/]+/files)/?"
)
# Allow form fields and MIME framing without increasing the handler's file limit.
_FORM_OVERHEAD = 1024 * 1024


def upload_body_limit(scope: Scope) -> int | None:
    if scope["type"] != "http" or scope["method"] != "POST":
        return None
    path = scope["path"].rstrip("/")
    if path == "/api/v1/documents":
        limit_mb = settings.max_document_upload_mb
    elif path == "/api/v1/preparation/templates/import-preview":
        limit_mb = 5
    elif path == "/api/v1/admin/backups/import":
        limit_mb = settings.backup_upload_max_mb
    elif path == "/api/v1/preparation/evidence/upload" or _EVIDENCE_PATH.fullmatch(path):
        limit_mb = settings.max_evidence_upload_mb
    else:
        return None
    return limit_mb * 1024 * 1024 + _FORM_OVERHEAD


class UploadLimitsMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = upload_body_limit(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return

        lengths = [value for name, value in scope["headers"] if name.lower() == b"content-length"]
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(
                    scope, receive, send
                )
                return
            declared = lengths[0].lstrip(b"0") or b"0"
            maximum = str(limit).encode("ascii")
            if len(declared) > len(maximum) or (
                len(declared) == len(maximum) and declared > maximum
            ):
                await JSONResponse({"detail": "Upload request is too large"}, status_code=413)(
                    scope, receive, send
                )
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # The pinned Starlette parser closes partial temporary files
                    # on stream errors; FastAPI preserves this 413 response.
                    raise HTTPException(413, "Upload request is too large")
            return message

        await self.app(scope, limited_receive, send)
