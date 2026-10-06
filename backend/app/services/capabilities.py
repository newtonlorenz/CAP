"""Non-secret installation capabilities shared by the API and diagnostics."""

import shutil

from app.services.structured_pdf import structured_pdf_available


def installation_capabilities(settings) -> dict:
    return {
        "ai": {
            "enabled": settings.ai_provider != "none"
            and bool(getattr(settings, f"{settings.ai_provider}_api_key", "").strip()),
            "provider": settings.ai_provider,
            "model": settings.ai_model if settings.ai_provider != "none" else None,
            "external_processing": settings.ai_provider != "none",
        },
        "jev": {
            "enabled": settings.jev_enabled and bool(settings.typesafe_api_key.strip()),
            "model": settings.jev_model,
            "external_processing": settings.jev_enabled,
            "revision": settings.jev_settings_revision,
        },
        "email": {"enabled": settings.email_available, "mode": settings.email_mode},
        "pdf_structure": {
            "engine": settings.pdf_structure_engine,
            "available": settings.pdf_structure_engine == "native" or structured_pdf_available(),
            "local_only": True,
        },
        "ocr": {"enabled": settings.ocr_enabled, "available": bool(shutil.which("tesseract"))},
        "feedback": {
            "enabled": bool(settings.feedback_service_url and settings.feedback_service_key)
        },
    }
