import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.api.backups import router as backups_router
from app.api.auth import router as auth_router
from app.api.capabilities import router as capabilities_router
from app.api.change_management import router as change_management_router
from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.requirement_quality import router as requirement_quality_router
from app.api.evidence import router as evidence_router
from app.api.integrations import router as integrations_router
from app.api.installation_settings import router as installation_settings_router
from app.api.jurisdictions import router as jurisdictions_router
from app.api.market_packs import router as market_packs_router
from app.api.program import router as program_router
from app.api.applications import router as applications_router
from app.api.access import router as access_router
from app.api.preparation import router as preparation_router
from app.api.preparation_evidence import router as preparation_evidence_router
from app.api.preparation_export import router as preparation_export_router
from app.api.reports import router as reports_router
from app.api.requirements import router as requirements_router
from app.api.reviews import router as reviews_router
from app.api.users import router as users_router
from app.api.product_feedback import router as product_feedback_router
from app.services.bootstrap import ensure_bootstrap_admin
from app.services.extraction_watchdog import run_extraction_watchdog
from app.middleware.restore_guard import RestoreGuardMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.upload_limits import UploadLimitsMiddleware

docs_url = "/docs" if settings.docs_enabled else None
redoc_url = "/redoc" if settings.docs_enabled else None
openapi_url = "/openapi.json" if settings.docs_enabled else None


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    await ensure_bootstrap_admin()

    task = None
    if not os.getenv("PYTEST_CURRENT_TEST"):
        task = asyncio.create_task(run_extraction_watchdog())
        fastapi_app.state.extraction_watchdog_task = task

    try:
        yield
    finally:
        running_task = task or getattr(fastapi_app.state, "extraction_watchdog_task", None)
        if running_task:
            running_task.cancel()
            try:
                await running_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Compliance Audit Platform",
    version="0.1.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
    lifespan=lifespan,
)

app.add_middleware(UploadLimitsMiddleware)
app.add_middleware(RestoreGuardMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
if settings.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

app.include_router(auth_router)
app.include_router(capabilities_router)
app.include_router(backups_router)
app.include_router(change_management_router)
app.include_router(dashboard_router)
app.include_router(documents_router)
app.include_router(requirement_quality_router)
app.include_router(evidence_router)
app.include_router(integrations_router)
app.include_router(installation_settings_router)
app.include_router(jurisdictions_router)
app.include_router(market_packs_router)
app.include_router(program_router)
app.include_router(applications_router)
app.include_router(access_router)
app.include_router(preparation_router)
app.include_router(preparation_evidence_router)
app.include_router(preparation_export_router)
app.include_router(reports_router)
app.include_router(requirements_router)
app.include_router(reviews_router)
app.include_router(users_router)
app.include_router(product_feedback_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}
