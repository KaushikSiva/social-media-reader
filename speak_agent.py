"""Assign voices to agents on the fly and speak via the active TTS provider."""

from __future__ import annotations

import random
from typing import Dict, Optional, Set, Tuple

from tts_voice import speak

VOICE_ASSIGNMENTS: Dict[str, str] = {}
_AVAILABLE_VOICES_CACHE: Optional[Set[str]] = None
_UNUSABLE_VOICES: Set[str] = set()

# Prefer consistent casing when looking up cached assignments.
def _normalize_agent(agent_id: str) -> str:
    return agent_id.strip().lower()


def _load_available_voices(force: bool = False) -> Set[str]:
    global _AVAILABLE_VOICES_CACHE
    if force or _AVAILABLE_VOICES_CACHE is None:
        _AVAILABLE_VOICES_CACHE = set(speak.fetch_available_voices())
    return _AVAILABLE_VOICES_CACHE


def _find_existing_assignment(agent_id: str) -> Tuple[Optional[str], Optional[str]]:
    normalized = _normalize_agent(agent_id)
    for key, voice in VOICE_ASSIGNMENTS.items():
        if _normalize_agent(key) == normalized:
            return key, voice
    return None, None


def get_or_assign_voice(agent_id: str) -> str:
    """Return an existing voice for the agent or assign a new one."""
    existing_key, existing_voice = _find_existing_assignment(agent_id)
    if existing_voice:
        # Ensure assignment sticks with the original dictionary key.
        if existing_key != agent_id:
            VOICE_ASSIGNMENTS[agent_id] = existing_voice
        return existing_voice

    available = [voice for voice in _load_available_voices() if voice not in _UNUSABLE_VOICES]
    if not available:
        raise RuntimeError("No voices available from the active TTS provider.")

    assigned = {voice for voice in VOICE_ASSIGNMENTS.values()}
    choices = [voice for voice in available if voice not in assigned]
    voice_id = random.choice(choices or available)

    VOICE_ASSIGNMENTS[agent_id] = voice_id
    return voice_id


def speak_for_agent(agent_id: str, text: str) -> str:
    """Speak the provided text for the agent and return the voice used."""
    if not text:
        raise ValueError("Text to speak must be non-empty.")

    voice_id = get_or_assign_voice(agent_id)
    speak.speak(text, voice_id)
    return voice_id


def main() -> None:
    agent_id = input("Agent ID: ").strip()
    text = input("Text to speak: ").strip()

    if not agent_id or not text:
        raise SystemExit("Agent ID and text are required.")

    voice_id = speak_for_agent(agent_id, text)

    print(f"🗣️ Agent '{agent_id}' using voice '{voice_id}'")


if __name__ == "__main__":
    main()


def clear_voice_assignment(agent_id: str) -> None:
    """Remove any cached voice assignment for the given agent."""
    normalized = _normalize_agent(agent_id)
    for key in list(VOICE_ASSIGNMENTS.keys()):
        if _normalize_agent(key) == normalized:
            VOICE_ASSIGNMENTS.pop(key, None)
            break


def mark_voice_unusable(voice_id: str) -> None:
    """Remember a voice id that failed so we avoid reusing it."""
    _UNUSABLE_VOICES.add(voice_id)
    for key, assigned in list(VOICE_ASSIGNMENTS.items()):
        if assigned == voice_id:
            VOICE_ASSIGNMENTS.pop(key, None)


__all__ = [
    "get_or_assign_voice",
    "speak_for_agent",
    "VOICE_ASSIGNMENTS",
    "clear_voice_assignment",
    "mark_voice_unusable",
]
