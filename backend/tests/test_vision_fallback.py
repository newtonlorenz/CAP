import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock

import pytest
from reportlab.pdfgen import canvas

from app.services import vision_parser as vision
from app.services.ai_provider import ProviderConfig


def _raw(confidence):
    return json.dumps({"requirements": [{
        "reference_id": "1", "title": None,
        "text": "The operator must keep records.",
        "requirement_type": "mandatory", "parent_reference": None,
        "confidence": confidence,
    }]})


@pytest.mark.parametrize("confidence,review", [
    (0.0, True), (0.749, True), (0.75, False), (1.0, False),
])
async def test_vision_uses_validated_confidence(monkeypatch, confidence, review):
    monkeypatch.setattr(vision.settings, "vision_fallback_enabled", True)
    monkeypatch.setattr(vision, "_bounded_render_page_png_data_uri", AsyncMock(return_value="data:image/png;base64,AA=="))
    parser = type("Parser", (), {"complete": AsyncMock(return_value=_raw(confidence))})()
    monkeypatch.setattr(vision, "create_parser", lambda config: parser)

    result = await vision.parse_requirements_from_page_image(
        file_path="unused.pdf", page_number=3, document_type="standard",
        page_text="The operator must keep records.",
        provider_config=ProviderConfig("openai", "test", "test", 1),
    )
    assert result.warnings == []
    assert len(result.items) == 1
    assert result.items[0]["confidence"] == confidence
    assert result.items[0]["needs_review"] is review
    assert result.items[0]["review_reason"] == ("low_confidence" if review else None)
    assert result.items[0]["parser_strategy"] == "vision"


async def test_vision_invalid_candidate_fails_once(monkeypatch):
    monkeypatch.setattr(vision.settings, "vision_fallback_enabled", True)
    monkeypatch.setattr(vision, "_bounded_render_page_png_data_uri", AsyncMock(return_value="data:image/png;base64,AA=="))
    parser = type("Parser", (), {"complete": AsyncMock(return_value=_raw(-0.1))})()
    monkeypatch.setattr(vision, "create_parser", lambda config: parser)
    result = await vision.parse_requirements_from_page_image(
        file_path="unused.pdf", page_number=1, document_type="standard",
        page_text="The operator must keep records.",
        provider_config=ProviderConfig("openai", "test", "test", 1),
    )
    assert result.items == []
    assert result.warnings == ["The extraction provider returned invalid requirement data."]
    parser.complete.assert_awaited_once()


async def test_bounded_render_produces_png_and_data_uri(tmp_path):
    source = tmp_path / "ordinary.pdf"
    pdf = canvas.Canvas(str(source))
    pdf.drawString(72, 720, "A readable PDF page")
    pdf.save()
    uri = await vision._bounded_render_page_png_data_uri(str(source), 1, dpi=72, timeout=10)
    assert uri.startswith("data:image/png;base64,iVBOR")


async def test_ordinary_vision_extraction_uses_rendered_pdf(tmp_path, monkeypatch):
    source = tmp_path / "ordinary.pdf"
    pdf = canvas.Canvas(str(source))
    pdf.drawString(72, 720, "The operator must keep records.")
    pdf.save()
    monkeypatch.setattr(vision.settings, "vision_fallback_enabled", True)
    monkeypatch.setattr(vision.settings, "vision_fallback_render_dpi", 72)
    parser = type("Parser", (), {"complete": AsyncMock(return_value=_raw(0.75))})()
    monkeypatch.setattr(vision, "create_parser", lambda config: parser)

    result = await vision.parse_requirements_from_page_image(
        file_path=str(source), page_number=1, document_type="standard",
        page_text="The operator must keep records.",
        provider_config=ProviderConfig("openai", "test", "test", 5),
    )
    assert result.warnings == []
    assert len(result.items) == 1
    assert result.items[0]["needs_review"] is False
    assert parser.complete.await_args.kwargs["image_uri"].startswith("data:image/png;base64,iVBOR")


@pytest.mark.parametrize("mode", ["timeout", "cancel", "cancel_during_spawn"])
async def test_bounded_render_stops_child_on_timeout_or_cancellation(monkeypatch, tmp_path, mode):
    original_spawn = asyncio.create_subprocess_exec
    spawned = []
    killed_groups = []
    original_killpg = os.killpg
    spawn_started = asyncio.Event()

    async def slow_child(*args, **kwargs):
        assert kwargs["start_new_session"] is True
        spawn_started.set()
        if mode == "cancel_during_spawn":
            await asyncio.sleep(0.05)
        process = await original_spawn(sys.executable, "-c", "import time; time.sleep(30)", **kwargs)
        spawned.append(process)
        return process

    def kill_group(pid, signum):
        killed_groups.append(pid)
        return original_killpg(pid, signum)

    monkeypatch.setattr(vision.asyncio, "create_subprocess_exec", slow_child)
    monkeypatch.setattr(vision.os, "killpg", kill_group)
    task = asyncio.create_task(vision._bounded_render_page_png_data_uri(
        str(tmp_path / "unused.pdf"), 1, dpi=72, timeout=0.1 if mode == "timeout" else 10,
    ))
    if mode == "cancel_during_spawn":
        await spawn_started.wait()
        task.cancel()
    elif mode == "cancel":
        while not spawned:
            await asyncio.sleep(0.01)
        task.cancel()
    with pytest.raises(TimeoutError if mode == "timeout" else asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)
    assert len(spawned) == 1
    assert spawned[0].returncode is not None
    assert killed_groups == [spawned[0].pid]
