"""Small, provider-neutral structured-output interface for Hyphae agents."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(RuntimeError):
    """Raised when an LLM response cannot safely be used."""


class LLMClient(Protocol):
    """Return JSON-compatible data conforming to the supplied schema."""

    def complete(self, *, prompt: str, response_schema: dict[str, Any]) -> Any: ...


@dataclass
class StaticLLMClient:
    """Deterministic client for tests and offline/replay execution."""

    response: Any

    def complete(self, *, prompt: str, response_schema: dict[str, Any]) -> Any:
        # JSON round-trip prevents callers from mutating the configured fixture.
        return json.loads(json.dumps(self.response))


class OpenAIClient:
    """OpenAI Responses API adapter using strict JSON-schema output.

    The SDK import and credential lookup are deliberately lazy: deterministic
    Hyphae runs never require the optional ``openai`` package or an API key.
    """

    def __init__(self, *, model: str = "gpt-5", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is required for OpenAI-backed execution")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise LLMError("Install the 'openai' package for OpenAI-backed execution") from exc
        self._client = OpenAI(api_key=self.api_key)

    def complete(self, *, prompt: str, response_schema: dict[str, Any]) -> Any:
        try:  # pragma: no cover - network integration
            response = self._client.responses.create(
                model=self.model,
                input=prompt,
                store=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "hyphae_response",
                        "schema": response_schema,
                        "strict": True,
                    }
                },
            )
            return json.loads(response.output_text)
        except Exception as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc
