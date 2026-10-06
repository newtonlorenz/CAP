from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.services.backups import is_restore_in_progress


class RestoreGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not is_restore_in_progress():
            return await call_next(request)

        path = request.url.path
        if path == "/api/v1/health" or path.startswith("/api/v1/admin/backups"):
            return await call_next(request)

        return JSONResponse(
            status_code=503,
            content={"detail": "Restore in progress. Try again later."},
        )
