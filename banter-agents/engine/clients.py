"""LLM client implementations for the banter agent engine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

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


class GeminiLLMClient(LLMClient):
    """Adapter that calls the Gemini REST API directly."""

    _API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        *,
        model: str,
        api_key: Optional[str] = None,
        client_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - surfaced only when requests missing.
            raise RuntimeError(
                "requests package is required for GeminiLLMClient. Install it via `pip install requests`."
            ) from exc

        if not api_key:
            raise RuntimeError("GeminiLLMClient requires an API key")

        self._requests = requests
        self._session = requests.Session()
        self._model = model
        self._api_key = api_key
        options = client_options or {}
        self._generation_config = options.get("generation_config")
        self._safety_settings = options.get("safety_settings")
        self._request_timeout = options.get("timeout", 30)

    def complete(self, messages: Sequence[Dict[str, str]], **kwargs: Any) -> str:
        payload = self._build_payload(messages)
        if kwargs:
            payload.setdefault("generation_config", {}).update(kwargs.get("generation_config", {}))
        response = self._session.post(
            self._endpoint,
            params={"key": self._api_key},
            json=payload,
            timeout=self._request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        return self._extract_text(data)

    @property
    def _endpoint(self) -> str:
        return f"{self._API_ROOT}/models/{self._model}:generateContent"

    def _build_payload(self, messages: Sequence[Dict[str, str]]) -> Dict[str, Any]:
        system_parts: List[str] = []
        contents: List[Dict[str, Any]] = []

        for message in messages:
            role = message.get("role", "user")
            text = message.get("content", "")
            if not text:
                continue
            if role == "system":
                system_parts.append(text)
                continue

            mapped_role = "user" if role in {"user", "system"} else "model"
            contents.append({
                "role": mapped_role,
                "parts": [{"text": text}],
            })

        if not contents:
            contents.append({"role": "user", "parts": [{"text": ""}]})

        payload: Dict[str, Any] = {"contents": contents}

        if system_parts:
            payload["system_instruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}]
            }

        if self._generation_config:
            payload["generation_config"] = self._generation_config
        if self._safety_settings:
            payload["safety_settings"] = self._safety_settings

        return payload

    def _extract_text(self, data: Dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            texts = [part.get("text") for part in parts if part.get("text")]
            if texts:
                return "".join(texts)
        return data.get("text") or ""


class GrokLLMClient(LLMClient):
    """Adapter for xAI's Grok chat completions API."""

    _API_ROOT = "https://api.x.ai/v1"

    def __init__(
        self,
        *,
        model: str,
        api_key: Optional[str] = None,
        client_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - surfaced only when requests missing.
            raise RuntimeError(
                "requests package is required for GrokLLMClient. Install it via `pip install requests`."
            ) from exc

        if not api_key:
            raise RuntimeError("GrokLLMClient requires an API key")

        self._requests = requests
        self._session = requests.Session()
        self._model = model
        self._api_key = api_key
        opts = dict(client_options or {})
        self._timeout = opts.pop("timeout", 30)
        self._defaults = opts

    def complete(self, messages: Sequence[Dict[str, str]], **kwargs: Any) -> str:
        payload = self._build_payload(messages)
        options = dict(self._defaults)
        options.update(kwargs)
        payload.update({key: value for key, value in options.items() if value is not None})

        response = self._session.post(
            f"{self._API_ROOT}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return self._extract_text(data)

    def _build_payload(self, messages: Sequence[Dict[str, str]]) -> Dict[str, Any]:
        formatted: List[Dict[str, str]] = []
        for message in messages:
            role = message.get("role") or "user"
            content = message.get("content") or ""
            formatted.append({"role": role, "content": content})
        if not formatted:
            formatted.append({"role": "user", "content": ""})
        return {"model": self._model, "messages": formatted}

    def _extract_text(self, data: Dict[str, Any]) -> str:
        choices = data.get("choices") or []
        for choice in choices:
            message = choice.get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                pieces = [part.get("text") for part in content if isinstance(part, dict) and part.get("text")]
                if pieces:
                    return "".join(pieces)
        return data.get("output") or ""
