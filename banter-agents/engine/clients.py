"""LLM client implementations for the banter agent engine."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from .simulation import LLMClient


class OpenAILLMClient(LLMClient):
    """Adapter for OpenAI's Chat Completions API."""

    def __init__(
        self,
        *,
        model: str,
        api_key: Optional[str] = None,
        organization: Optional[str] = None,
        default_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - surfaced at runtime for users.
            raise RuntimeError(
                "openai package is required for OpenAILLMClient."
            ) from exc

        self._client = OpenAI(api_key=api_key, organization=organization)
        self._model = model
        self._defaults = default_options or {}

    def complete(self, messages: Sequence[Dict[str, str]], **kwargs: Any) -> str:
        payload = [{"role": msg["role"], "content": msg["content"]} for msg in messages]
        options = {**self._defaults, **kwargs}
        response = self._client.chat.completions.create(
            model=self._model,
            messages=payload,
            **options,
        )
        choice = response.choices[0]
        return choice.message.content or ""
