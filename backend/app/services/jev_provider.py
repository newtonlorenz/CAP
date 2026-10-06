"""Bounded TypeSafe HTTP judgments; credentials and provider errors stay server-side."""

import asyncio
import json
import math
import re
from dataclasses import dataclass, field

import httpx


class JevError(ValueError):
    """Safe message suitable for user-visible quality-run diagnostics."""


@dataclass(frozen=True)
class JevConfig:
    enabled: bool = False
    model: str = "jev-1.13.0"
    api_key: str = field(default="", repr=False)
    revision: int = 0
    timeout: float = 30

    @classmethod
    def from_settings(cls, settings):
        return cls(
            bool(settings.jev_enabled),
            settings.jev_model,
            settings.typesafe_api_key.strip(),
            settings.jev_settings_revision,
            getattr(settings, "jev_request_timeout_seconds", 30),
        )


def _number(value, maximum=1):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JevError("Jev returned invalid judgment data.")
    if not math.isfinite(value) or not 0 <= value <= maximum:
        raise JevError("Jev returned invalid judgment data.")


def _validate_questions(questions):
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 128:
        raise JevError("Jev requires a bounded set of questions.")
    for key, question in questions.items():
        if not isinstance(key, str) or not key or not isinstance(question, dict):
            raise JevError("Invalid Jev question.")
        kind = question.get("type")
        if kind not in {"choice", "score", "noul"} or not isinstance(
            question.get("instructions"), (str, dict, list)
        ):
            raise JevError("Invalid Jev question.")
        criteria = question.get("criteria")
        if kind == "choice" and (
            not isinstance(criteria, dict)
            or not 1 <= len(criteria) <= 255
            or any(not isinstance(k, str) for k in criteria)
        ):
            raise JevError("Invalid Jev choice criteria.")
        if kind == "score" and (not isinstance(criteria, list) or not 2 <= len(criteria) <= 10):
            raise JevError("Invalid Jev score criteria.")


def _validate_response(data, questions):
    invalid = "Jev returned invalid judgment data."
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("model"), str)
        or not data["model"]
        or len(data["model"]) > 255
    ):
        raise JevError(invalid)
    answers = data.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise JevError(invalid)
    for key, question in questions.items():
        answer = answers[key]
        kind = question["type"]
        if not isinstance(answer, dict) or answer.get("type") != kind:
            raise JevError(invalid)
        if kind == "noul":
            _number(answer.get("noul"))
            continue
        _number(answer.get("confidence"))
        expected = (
            set(question["criteria"])
            if kind == "choice"
            else {str(i) for i in range(len(question["criteria"]))}
        )
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != expected:
            raise JevError(invalid)
        for probability in probabilities.values():
            _number(probability)
        if not math.isclose(sum(probabilities.values()), 1, abs_tol=0.001):
            raise JevError(invalid)
        if kind == "choice":
            choice = answer.get("choice")
            if (
                not isinstance(choice, str)
                or choice not in expected
                or probabilities[choice] < max(probabilities.values())
            ):
                raise JevError(invalid)
        else:
            _number(answer.get("score"), len(expected) - 1)
            if not isinstance(answer.get("legend"), dict) or set(answer["legend"]) != expected:
                raise JevError(invalid)
            if any(not isinstance(v, str) for v in answer["legend"].values()):
                raise JevError(invalid)
            weighted = sum(int(k) * v for k, v in probabilities.items())
            if not math.isclose(answer["score"], weighted, abs_tol=0.01):
                raise JevError(invalid)
    usage = data.get("usage")
    if not isinstance(usage, dict):
        raise JevError(invalid)
    for key in ("input_tokens", "output_tokens"):
        value = usage.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100_000_000:
            raise JevError(invalid)
    return {
        "model": data["model"],
        "answers": answers,
        "usage": {k: usage[k] for k in ("input_tokens", "output_tokens")},
    }


class JevClient:
    def __init__(self, config: JevConfig, transport=None, *, should_continue=None):
        self.config, self.transport = config, transport
        self.should_continue = should_continue

    async def evaluate(self, state, questions):
        if not self.config.enabled or not self.config.api_key:
            raise JevError("Jev enhancement is unavailable. Enable it and save an API key first.")
        if not isinstance(state, (str, dict, list)):
            raise JevError("Invalid Jev state.")
        _validate_questions(questions)
        try:
            payload = json.dumps(
                {"state": state, "model": self.config.model, "questions": questions},
                allow_nan=False,
            ).encode()
        except (TypeError, ValueError):
            raise JevError("Invalid Jev request data.") from None
        if len(payload) > 1_000_000:
            raise JevError("Jev request exceeds the bounded input size.")
        for attempt in range(2):
            if self.should_continue and not await self.should_continue():
                raise JevError("The source check was cancelled or its settings changed.")
            try:
                async with (
                    asyncio.timeout(self.config.timeout),
                    httpx.AsyncClient(
                        timeout=self.config.timeout,
                        trust_env=False,
                        follow_redirects=False,
                        transport=self.transport,
                    ) as client,
                    client.stream(
                        "POST",
                        "https://api.typesafe.ai/v1/systemone",
                        headers={
                            "Authorization": f"Bearer {self.config.api_key}",
                            "Content-Type": "application/json",
                        },
                        content=payload,
                    ) as response,
                ):
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt == 0:
                            await asyncio.sleep(0.25)
                            continue
                        raise JevError(
                            "Jev is temporarily unavailable or rate limited. Try again later."
                        )
                    if response.status_code in {401, 403}:
                        raise JevError(
                            "Jev access was rejected. Check the saved API key and model permissions."
                        )
                    if response.status_code != 200:
                        raise JevError(
                            "Jev rejected the request. Check the saved model and provider availability."
                        )
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2_000_000:
                            raise JevError("Jev returned an oversized response.")
                    try:
                        data = json.loads(raw)
                    except (ValueError, UnicodeError):
                        raise JevError("Jev returned invalid judgment data.") from None
                    result = _validate_response(data, questions)
                    if (
                        re.fullmatch(r"jev-\d+\.\d+\.\d+", self.config.model)
                        and result["model"] != self.config.model
                    ):
                        raise JevError(
                            "Jev returned a different model from the pinned version. Request a new check after reviewing model settings."
                        )
                    return result
            except (httpx.TransportError, TimeoutError):
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                raise JevError("Jev could not connect or timed out. Try again later.") from None
