"""Explicit, injectable AI transports. No SDK, ambient endpoint or global client."""

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.extraction_prompts import EXTRACTION_PROMPT, OPENAI_JSON_SCHEMA


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "none"
    model: str = ""
    api_key: str = field(default="", repr=False)
    timeout: float = 120

    @classmethod
    def from_settings(cls, settings, *, provider=None, model=None):
        selected = provider if provider is not None else settings.ai_provider
        if selected in {"none", "local", "deterministic"}:
            return cls()
        if selected != settings.ai_provider:
            raise ValueError(
                "Extraction provider changed since this run was requested. Start a new run."
            )
        if selected not in {"openai", "anthropic"}:
            raise ValueError("Unsupported extraction provider.")
        key = getattr(settings, f"{selected}_api_key").strip()
        if not key:
            raise ValueError("The selected extraction provider has no credentials.")
        return cls(selected, model or settings.ai_model, key, settings.ai_request_timeout_seconds)


class RequirementCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    reference_id: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=2000)
    text: str = Field(min_length=1, max_length=50000)
    requirement_type: Literal["mandatory", "recommended", "informational"]
    parent_reference: str | None = Field(default=None, max_length=200)
    confidence: float = Field(ge=0, le=1)


class CandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirements: list[RequirementCandidate] = Field(max_length=500)


def parse_candidates(raw: str, page_number: int) -> list[dict]:
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        response = CandidateResponse.model_validate_json(raw)
    except (ValidationError, ValueError):
        raise ValueError("The extraction provider returned invalid requirement data.") from None
    return [dict(item.model_dump(), page_number=page_number) for item in response.requirements]


class AIParser(ABC):
    @property
    @abstractmethod
    def provider(self) -> str: ...

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    async def parse(self, text: str, document_type: str, page_number: int) -> list[dict]: ...


class RemoteParser(AIParser):
    def __init__(self, config: ProviderConfig, *, transport=None):
        if config.provider not in {"openai", "anthropic"} or not config.api_key:
            raise ValueError("No AI provider configured.")
        self.config = config
        self.transport = transport

    @property
    def provider(self):
        return self.config.provider

    @property
    def model(self):
        return self.config.model

    async def complete(self, prompt: str, schema: dict, *, image_uri=None, max_tokens=4096) -> str:
        if self.provider == "openai":
            content = (
                prompt
                if image_uri is None
                else [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_uri}},
                ]
            )
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.config.api_key}"}
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": content}],
                "max_completion_tokens": max_tokens,
                "response_format": {"type": "json_schema", "json_schema": schema},
            }
        else:
            content = [{"type": "text", "text": prompt}]
            if image_uri:
                content.insert(
                    0,
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_uri.split(",", 1)[1],
                        },
                    },
                )
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": self.config.api_key, "anthropic-version": "2023-06-01"}
            payload = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": content}],
            }
        try:
            async with (
                asyncio.timeout(self.config.timeout),
                httpx.AsyncClient(
                    timeout=self.config.timeout,
                    trust_env=False,
                    follow_redirects=False,
                    transport=self.transport,
                ) as client,
                client.stream("POST", url, headers=headers, json=payload) as response,
            ):
                if response.status_code != 200:
                    raise ValueError(f"Extraction provider returned HTTP {response.status_code}.")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 2 * 1024 * 1024:
                        raise ValueError("Extraction provider response exceeds 2 MB.")
            result = json.loads(body)
            if self.provider == "openai":
                choice = result["choices"][0]
                if choice.get("finish_reason") != "stop":
                    raise ValueError("Extraction provider returned an incomplete response.")
                raw = choice["message"]["content"]
            else:
                if result.get("stop_reason") != "end_turn":
                    raise ValueError("Extraction provider returned an incomplete response.")
                raw = "\n".join(
                    block["text"] for block in result["content"] if block["type"] == "text"
                )
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("Extraction provider returned no result.")
            return raw.strip()
        except httpx.TimeoutException:
            raise TimeoutError("Extraction provider timed out.") from None
        except httpx.HTTPError:
            raise ValueError("Extraction provider request failed.") from None
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            raise ValueError("Extraction provider returned an invalid response.") from None

    async def parse(self, text: str, document_type: str, page_number: int) -> list[dict]:
        if not text.strip():
            return []
        prompt = EXTRACTION_PROMPT.format(
            text=text, document_type=document_type, page_number=page_number
        )
        raw = await self.complete(prompt, OPENAI_JSON_SCHEMA)
        return parse_candidates(raw, page_number)


def create_parser(config: ProviderConfig, *, transport=None) -> RemoteParser:
    return RemoteParser(config, transport=transport)
