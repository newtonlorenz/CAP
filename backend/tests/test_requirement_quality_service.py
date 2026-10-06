"""Safety and cost contracts at the public source-quality evaluator boundary."""

import asyncio
import copy

import pytest

from app.services.jev_provider import JevConfig, JevError
from app.services.requirement_quality import evaluate_requirements

CONFIG = JevConfig(enabled=True, api_key="test-key")


def row(ref="1", text="Operators must retain records."):
    return {
        "id": f"requirement-{ref}",
        "reference_id": ref,
        "text": text,
        "requirement_type": "mandatory",
        "parent_id": None,
        "page_number": 1,
    }


def choice(question, selected, confidence=1, probability=1):
    options = list(question["criteria"])
    others = [key for key in options if key != selected]
    return {
        "type": "choice",
        "choice": selected,
        "confidence": confidence,
        "probabilities": {
            key: probability if key == selected else (1 - probability) / len(others)
            for key in options
        },
    }


def provider(
    monkeypatch,
    *,
    supported=0.1,
    faithful=1,
    confidence=1,
    probability=1,
    no_match=False,
    parent="none",
    classification="mandatory",
):
    calls = []

    async def evaluate(self, state, questions):
        calls.append((copy.deepcopy(state), copy.deepcopy(questions)))
        if "source_candidates" in state:
            requirement = state["requirement"]
            candidates = state["source_candidates"]
            selected = next(
                (s for s in candidates if s["reference_id"] == requirement["reference_id"]),
                candidates[0],
            )["id"]
            answers = {
                "source": choice(
                    questions["source"],
                    "no_match" if no_match else selected,
                    confidence,
                    probability,
                ),
                "supported": {"type": "noul", "noul": supported},
                "type": choice(questions["type"], classification),
                "parent": choice(
                    questions["parent"], parent if requirement["reference_id"] != "1" else "none"
                ),
            }
        elif "faithful" in questions:
            answers = {"faithful": {"type": "noul", "noul": faithful}}
        elif "relation" in questions:
            answers = {"relation": choice(questions["relation"], "distinct")}
        else:
            answers = {
                "requirement": {"type": "noul", "noul": 1},
                "type": choice(questions["type"], "mandatory"),
            }
        return {
            "model": "jev-1.13.0",
            "answers": answers,
            "usage": {"input_tokens": 20, "output_tokens": 5},
        }

    monkeypatch.setattr("app.services.jev_provider.JevClient.evaluate", evaluate)
    return calls


async def test_blank_paragraph_exception_is_retained_in_eligible_source_repair(monkeypatch):
    provider(monkeypatch)
    source = "1 Operators must retain records.\n\nExcept where national law prohibits retention."
    result = await evaluate_requirements([row()], [{"page_number": 1, "text": source}], CONFIG)
    finding = next(f for f in result["findings"] if f["kind"] == "accuracy")
    assert finding["after"]["text"] == source
    assert finding["source_excerpt"] == source
    assert finding["auto_eligible"]


async def test_cross_page_exception_blocks_automatic_shortening(monkeypatch):
    provider(monkeypatch)
    rows = [
        row(text="1 Operators must retain records. Except where national law prohibits retention.")
    ]
    pages = [
        {"page_number": 1, "text": "1 Operators must retain records."},
        {"page_number": 2, "text": "Except where national law prohibits retention."},
    ]
    result = await evaluate_requirements(rows, pages, CONFIG)
    assert not any(f["auto_eligible"] for f in result["findings"])


@pytest.mark.parametrize(
    "options,eligible",
    [
        ({}, True),
        ({"confidence": 0.97}, False),
        ({"probability": 0.97}, False),
        ({"faithful": 0.97}, False),
        ({"no_match": True}, False),
    ],
)
async def test_repair_requires_confident_selection_and_source_verification(
    monkeypatch, options, eligible
):
    calls = provider(monkeypatch, **options)
    result = await evaluate_requirements(
        [row()],
        [{"page_number": 1, "text": "1 Operators must retain records for five years."}],
        CONFIG,
    )
    finding = next(f for f in result["findings"] if f["kind"] == "accuracy")
    assert finding["auto_eligible"] is eligible
    if eligible:
        state = next(s for s, q in calls if "faithful" in q)
        assert state["requirement"]["text"] == "1 Operators must retain records for five years."


async def test_existing_reference_missing_clause_becomes_gap_not_new_duplicate(monkeypatch):
    provider(monkeypatch, no_match=True)
    result = await evaluate_requirements(
        [row()],
        [{"page_number": 1, "text": "1 Operators must retain records and provide auditor access."}],
        CONFIG,
    )
    gaps = [f for f in result["findings"] if f["kind"] == "source_gap"]
    assert len(gaps) == 1 and not gaps[0]["auto_eligible"]
    assert gaps[0]["after"]["text"] == "1 Operators must retain records and provide auditor access."
    assert not any(f["kind"] == "omission" for f in result["findings"])


async def test_provider_outage_reports_partial_without_changing_inputs(monkeypatch):
    async def unavailable(self, state, questions):
        raise JevError("Unavailable")

    monkeypatch.setattr("app.services.jev_provider.JevClient.evaluate", unavailable)
    rows, pages = [row()], [{"page_number": 1, "text": "1 Operators must retain records."}]
    before = copy.deepcopy((rows, pages))
    result = await evaluate_requirements(rows, pages, CONFIG)
    assert result["status"] == "partial" and result["findings"] == []
    assert result["coverage"]["checked"] == 0
    assert (rows, pages) == before


async def test_exact_cache_reuse_avoids_paid_request_but_source_changes_are_rechecked(monkeypatch):
    calls = provider(monkeypatch, supported=1)
    rows = [row(text="1 Operators must retain records.")]
    pages = [{"page_number": 1, "text": "1 Operators must retain records."}]
    first = await evaluate_requirements(rows, pages, CONFIG)
    assert len(calls) == 1
    again = await evaluate_requirements(rows, pages, CONFIG, cached=first["findings"])
    assert len(calls) == 1 and again["coverage"] == first["coverage"]
    assert again["usage"] == {"input_tokens": 0, "output_tokens": 0}
    await evaluate_requirements(
        rows,
        [{"page_number": 1, "text": "1 Operators must retain records securely."}],
        CONFIG,
        cached=first["findings"],
    )
    assert len(calls) > 1


async def test_outer_cancellation_stops_active_and_queued_requests(monkeypatch):
    active, started = set(), []
    ready = asyncio.Event()

    async def hanging(self, state, questions):
        identity = state["requirement"]["id"]
        started.append(identity)
        active.add(identity)
        if len(active) == 2:
            ready.set()
        try:
            await asyncio.Event().wait()
        finally:
            active.remove(identity)

    monkeypatch.setattr("app.services.jev_provider.JevClient.evaluate", hanging)
    rows = [row(str(i), f"Operators must retain category {i}.") for i in range(1, 6)]
    pages = [
        {
            "page_number": 1,
            "text": "\n".join(f"{i} Operators must retain category {i}." for i in range(1, 6)),
        }
    ]
    operation = asyncio.create_task(evaluate_requirements(rows, pages, CONFIG))
    try:
        await asyncio.wait_for(ready.wait(), timeout=2)
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(operation, timeout=2)
        await asyncio.sleep(0)
        assert not active and len(started) == 2
    finally:
        if not operation.done():
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)


async def test_parent_repair_verification_contains_real_parent_context(monkeypatch):
    calls = provider(monkeypatch, supported=1, parent="requirement-1")
    rows = [
        row(text="1 Record management obligations."),
        row("1.1", "1.1 Operators must retain records."),
    ]
    pages = [
        {
            "page_number": 1,
            "text": "1 Record management obligations.\n1.1 Operators must retain records.",
        }
    ]
    result = await evaluate_requirements(rows, pages, CONFIG)
    child = next(
        f
        for f in result["findings"]
        if f["requirement_id"] == "requirement-1.1" and f["kind"] == "accuracy"
    )
    assert child["after"]["parent_id"] == "requirement-1" and child["auto_eligible"]
    verification = next(
        s for s, q in calls if "faithful" in q and s["requirement"]["id"] == "requirement-1.1"
    )
    assert verification["parent"]["text"] == "1 Record management obligations."
    assert any(
        s["text"] == "1 Record management obligations." for s in verification["parent_source"]
    )


async def test_uncertain_classification_preserves_existing_type_for_review(monkeypatch):
    provider(monkeypatch, supported=1, classification="uncertain")
    original = row(text="1 Operators should retain records.")
    original["requirement_type"] = "recommended"
    result = await evaluate_requirements(
        [original], [{"page_number": 1, "text": "1 Operators should retain records."}], CONFIG
    )
    accuracy = next(f for f in result["findings"] if f["kind"] == "accuracy")
    assert accuracy["after"] == {} and not accuracy["auto_eligible"]
    assert original["requirement_type"] == "recommended"
