"""TypeSafe transport contract: typed judgments, bounded retries and secret isolation."""

import json

import httpx
import pytest

from app.services.jev_provider import JevClient, JevConfig, JevError

QUESTIONS = {
    "supported": {"type": "noul", "instructions": "Does the source support this?"},
    "classification": {
        "type": "choice",
        "instructions": "Select the obligation",
        "criteria": {"mandatory": None, "informational": None},
    },
    "relevance": {
        "type": "score",
        "instructions": "Rate relevance",
        "criteria": ["unrelated", "related"],
    },
}


def response():
    return {
        "model": "jev-1.13.0",
        "answers": {
            "supported": {"type": "noul", "noul": 0.99},
            "classification": {
                "type": "choice",
                "choice": "mandatory",
                "confidence": 0.99,
                "probabilities": {"mandatory": 0.999, "informational": 0.001},
            },
            "relevance": {
                "type": "score",
                "score": 0.8,
                "confidence": 0.5,
                "probabilities": {"0": 0.2, "1": 0.8},
                "legend": {"0": "unrelated", "1": "related"},
            },
        },
        "usage": {"input_tokens": 200, "output_tokens": 30},
    }


async def test_http_contract_and_single_transient_retry():
    requests = []

    def handle(request):
        requests.append(request)
        assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
        assert request.headers["authorization"] == "Bearer private-key"
        assert json.loads(request.content) == {
            "state": {"source": "must"},
            "model": "jev-1.13.0",
            "questions": QUESTIONS,
        }
        return httpx.Response(529) if len(requests) == 1 else httpx.Response(200, json=response())

    result = await JevClient(
        JevConfig(True, api_key="private-key"), httpx.MockTransport(handle)
    ).evaluate({"source": "must"}, QUESTIONS)
    assert result == response()
    assert len(requests) == 2


@pytest.mark.parametrize(
    "config", [JevConfig(), JevConfig(True), JevConfig(False, api_key="private-key")]
)
async def test_unavailable_never_sends(config):
    def handle(request):
        pytest.fail("Unavailable Jev sent source data")

    with pytest.raises(JevError, match="unavailable"):
        await JevClient(config, httpx.MockTransport(handle)).evaluate("private source", QUESTIONS)


@pytest.mark.parametrize(
    "change",
    [
        lambda data: data["answers"].pop("supported"),
        lambda data: data["answers"]["supported"].update(noul=float("nan")),
        lambda data: data["answers"]["classification"].update(choice="invented"),
        lambda data: data["answers"]["classification"].update(confidence=True),
        lambda data: data["answers"]["classification"].update(probabilities={"mandatory": 0.9}),
        lambda data: data["answers"]["relevance"].update(score=0.2),
        lambda data: data["usage"].update(input_tokens=-1),
    ],
)
async def test_rejects_invalid_provider_judgments(change):
    data = response()
    change(data)
    raw = json.dumps(data).encode()
    with pytest.raises(JevError, match="invalid judgment"):
        await JevClient(
            JevConfig(True, api_key="secret"),
            httpx.MockTransport(lambda request: httpx.Response(200, content=raw)),
        ).evaluate("source", QUESTIONS)


@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_safe_errors_and_bounded_delivery(status):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            status, text="secret provider body", headers={"Location": "https://untrusted.example/"}
        )

    with pytest.raises(JevError) as error:
        await JevClient(JevConfig(True, api_key="secret"), httpx.MockTransport(handle)).evaluate(
            "source", QUESTIONS
        )
    assert "secret" not in str(error.value)
    assert len(requests) == (2 if status in {429, 500} else 1)


async def test_cancellation_after_rate_limit_prevents_retry_post():
    requests = []

    async def should_continue():
        return not requests

    def handle(request):
        requests.append(request)
        return httpx.Response(429)

    with pytest.raises(JevError, match="cancelled"):
        await JevClient(
            JevConfig(True, api_key="secret"),
            httpx.MockTransport(handle),
            should_continue=should_continue,
        ).evaluate("source", QUESTIONS)
    assert len(requests) == 1


@pytest.mark.parametrize(
    "requested,actual,accepted",
    [
        ("jev-1.13.0", "jev-1.14.0", False),
        ("jev-latest", "jev-1.14.0", True),
    ],
)
async def test_pinned_model_provenance_is_enforced_while_alias_resolutions_are_recorded(
    requested, actual, accepted
):
    data = response()
    data["model"] = actual
    client = JevClient(
        JevConfig(True, model=requested, api_key="secret"),
        httpx.MockTransport(lambda request: httpx.Response(200, json=data)),
    )
    if accepted:
        assert (await client.evaluate("source", QUESTIONS))["model"] == actual
    else:
        with pytest.raises(JevError, match="different model"):
            await client.evaluate("source", QUESTIONS)
