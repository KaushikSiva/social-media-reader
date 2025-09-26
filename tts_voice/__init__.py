"""Provider-agnostic TTS helpers."""

from importlib import import_module
import os

_PROVIDER_MODULES = {
    "inworld": "tts_voice.speak",
    "elevenlabs": "tts_voice.elevenlabs",
}


def _load_provider():
    provider = os.getenv("TTS_PROVIDER", "elevenlabs").lower()
    module_path = _PROVIDER_MODULES.get(provider)
    if not module_path:
        raise ValueError(
            f"Unsupported TTS_PROVIDER '{provider}'. "
            f"Available options: {', '.join(_PROVIDER_MODULES)}."
        )
    return import_module(module_path)


_provider = _load_provider()
fetch_available_voices = _provider.fetch_available_voices
speak_text = getattr(_provider, "speak")

# Expose provider module so existing imports `from tts_voice import speak`
# continue to work regardless of which backend is active.
speak = _provider

__all__ = ["fetch_available_voices", "speak", "speak_text"]
