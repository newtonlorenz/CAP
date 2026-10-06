"""Real Celery transport/process tests with no PDF execution or external AI."""

import asyncio
import os
import billiard
from pathlib import Path

from app.tasks import celery_app
from app.tasks import extraction
from app.services.pdf_preprocessor import PreprocessResult

ROOT = Path(os.environ["CAP_JOB_FIXTURE_DIR"])


async def preprocess(path, *args, **kwargs):
    name = Path(path).name
    marker = ROOT / (name + ".attempted")
    if name.startswith(("fail_once_", "crash_once_")):
        try:
            fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
            if name.startswith("crash_once_"):
                os._exit(73)
            raise RuntimeError("Synthetic one-time worker failure")
    if name.startswith(("slow_", "cancel_", "supersede_")):
        await asyncio.sleep(2)
    return PreprocessResult(
        pages=[{"page_number": 1, "text": "Synthetic workflow fixture."}],
        page_quality=[],
        low_quality_pages=[],
        ocr_applied=False,
        ocr_pages=0,
        warning_count=0,
        warnings=[],
        family_fingerprint=None,
        cleanup_paths=[],
        parseability_score=1.0,
        fallback_trigger_reason=None,
        diagnostics={},
    )


class Adapter:
    async def parse_requirements(self, **kwargs):
        return [
            {
                "reference_id": "1.1",
                "title": "Synthetic fixture",
                "text": "A synthetic job result.",
                "requirement_type": "mandatory",
                "confidence": 1.0,
            }
        ]


extraction.bounded_preprocess = preprocess
extraction.PdfParser = lambda: Adapter()
celery_app.conf.update(
    task_default_queue=os.environ["CAP_JOB_FIXTURE_QUEUE"],
    worker_cancel_long_running_tasks_on_connection_loss=True,
)
if __name__ == "__main__":
    # Match the Linux deployment worker model inside this disposable test process.
    billiard.set_start_method("fork", force=True)
    celery_app.worker_main(
        [
            "worker",
            "--pool=prefork",
            "--concurrency=2",
            "--loglevel=INFO",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            "--hostname=cap-verification@%h",
        ]
    )
