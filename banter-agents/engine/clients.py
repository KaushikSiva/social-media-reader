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
            from openai import AsyncOpenAI, OpenAI
        except ImportError as exc:  # pragma: no cover - surfaced at runtime for users.
            raise RuntimeError(
                "openai package is required for OpenAILLMClient."
            ) from exc

        self._client = OpenAI(api_key=api_key, organization=organization)
        self._async_client = AsyncOpenAI(api_key=api_key, organization=organization)
        self._model = model
        self._defaults = default_options or {}

    def complete(self, messages: Sequence[Dict[str, str]], **kwargs: Any) -> str:
        payload = self._format_messages(messages)
        options = self._merge_options(dict(kwargs))
        response = self._client.chat.completions.create(
            model=self._model,
            messages=payload,
            **options,
        )
        return self._extract_text(response)

    async def acomplete(self, messages: Sequence[Dict[str, str]], **kwargs: Any) -> str:
        payload = self._format_messages(messages)
        options = self._merge_options(dict(kwargs))
        response = await self._async_client.chat.completions.create(
            model=self._model,
            messages=payload,
            **options,
        )
        return self._extract_text(response)

    def _merge_options(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        options = dict(self._defaults)
        options.update(overrides)
        return options

    def _format_messages(self, messages: Sequence[Dict[str, str]]) -> Sequence[Dict[str, str]]:
        return [{"role": msg["role"], "content": msg["content"]} for msg in messages]

    def _extract_text(self, response: Any) -> str:
        choice = response.choices[0]
        return choice.message.content or ""
