import asyncio
import os
from pathlib import Path
import sys

import pytest
from reportlab.pdfgen import canvas

from app.config import settings
from app.services.pdf_worker import bounded_preprocess


async def test_pdf_page_limit_is_enforced_in_child(tmp_path, monkeypatch):
    source = tmp_path / "two-pages.pdf"
    pdf = canvas.Canvas(str(source))
    for _ in range(2):
        pdf.drawString(40, 700, "1.1 The operator shall keep records.")
        pdf.showPage()
    pdf.save()
    monkeypatch.setattr(settings, "pdf_max_pages", 1)
    with pytest.raises(ValueError, match="preprocessing failed"):
        await bounded_preprocess(str(source), "Custom certification")


@pytest.mark.parametrize("cancel", [False, True])
async def test_timeout_and_cancellation_reap_process_and_staging(tmp_path, monkeypatch, cancel):
    create = asyncio.create_subprocess_exec
    started = asyncio.Event()
    child = None
    staging = None

    async def sleeping_child(*args, **kwargs):
        nonlocal child, staging
        staging = Path(kwargs["env"]["TMPDIR"])
        child = await create(sys.executable, "-c", "import time; time.sleep(30)", **kwargs)
        started.set()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", sleeping_child)
    monkeypatch.setattr(settings, "pdf_preprocess_timeout_seconds", 0.1)
    task = asyncio.create_task(bounded_preprocess(str(tmp_path / "input.pdf"), "Custom certification"))
    await started.wait()
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(ValueError, match="exceeded its time limit"):
            await task
    assert child.returncode is not None
    assert not staging.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(child.pid, 0)
