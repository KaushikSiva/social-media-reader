"""Text-to-speech helpers for ElevenLabs."""

from __future__ import annotations

import os
import platform
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.elevenlabs.io/v1"
DEFAULT_MODEL_ID = "eleven_v3"
DEFAULT_OUTPUT_DIR = Path("tts_output")


def _get_api_key() -> str:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. Add it to your environment or .env file."
        )
    return api_key


def fetch_available_voices() -> List[str]:
    """Return a list of available ElevenLabs voice IDs (male voices by default)."""
    headers = {"xi-api-key": _get_api_key()}
    response = requests.get(f"{BASE_URL}/voices", headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()
    voices = data.get("voices", [])
    print("🔍 ElevenLabs voice response example:")
    if voices:
        sample = {k: voices[0].get(k) for k in ("voice_id", "name", "category", "gender")}
        print(sample)
    preferred_gender = os.getenv("ELEVENLABS_VOICE_GENDER", "").strip().lower()

    def _voice_gender(entry: Dict[str, object]) -> str:
        direct = str(entry.get("gender", "") or "").lower()
        if direct:
            return direct
        labels = entry.get("labels")
        if isinstance(labels, dict):
            label_gender = str(labels.get("gender", "") or "").lower()
            if label_gender:
                return label_gender
        return ""

    matching: List[str] = []
    fallback: List[str] = []
    for voice in voices:
        voice_id = voice.get("voice_id")
        if not voice_id:
            continue
        gender = _voice_gender(voice)
        if preferred_gender and gender:
            if gender == preferred_gender:
                matching.append(voice_id)
                continue
        fallback.append(voice_id)

    if preferred_gender:
        if matching:
            result = matching
            print(f"✅ Loaded {len(result)} voices matching gender='{preferred_gender}'.")
        else:
            result = fallback
            print(
                f"⚠️ No voices matched gender='{preferred_gender}'. Falling back to {len(result)} available voices."
            )
    else:
        result = matching + fallback
        print(f"✅ Loaded {len(result)} voices (no gender filter).")

    if not result:
        raise RuntimeError("No ElevenLabs voices available after filtering.")

    return result


def speak(
    text: str,
    voice_id: str,
    *,
    model_id: Optional[str] = None,
    output_path: Optional[Path] = None,
    voice_settings: Optional[Dict[str, float]] = None,
    play_audio: bool = True,
) -> Path:
    """Generate speech with ElevenLabs and optionally play it.

    Returns the path to the generated audio file.
    """

    if not text:
        raise ValueError("Text to speak must be non-empty.")

    model_id = model_id or os.getenv("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID)
    voice_settings = voice_settings or {
        "stability": 0.5,
        "similarity_boost": 0.5,
        "style": 0.0,
        "use_speaker_boost": True,
    }

    headers = {
        "xi-api-key": _get_api_key(),
        "Accept": "audio/wav",
        "Content-Type": "application/json",
    }

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": voice_settings,
    }

    url = f"{BASE_URL}/text-to-speech/{voice_id}"
    response = requests.post(url, json=payload, headers=headers, stream=True, timeout=120)
    response.raise_for_status()

    if output_path:
        output_path = Path(output_path)

    output_dir = output_path.parent if output_path else DEFAULT_OUTPUT_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = output_path.name if output_path else f"elevenlabs_{voice_id}_{uuid.uuid4().hex}.wav"
    file_path = output_dir / filename

    with open(file_path, "wb") as audio_file:
        for chunk in response.iter_content(chunk_size=4096):
            if chunk:
                audio_file.write(chunk)

    if play_audio:
        _play_audio(file_path)

    return file_path


def _play_audio(file_path: Path) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["afplay", str(file_path)], check=True)
    elif system == "Windows":
        command = [
            "powershell",
            "-Command",
            f"Start-Process -FilePath 'wmplayer' -ArgumentList '{file_path}' -Wait",
        ]
        subprocess.run(command, check=True)
    else:
        subprocess.run(["aplay", str(file_path)], check=True)


__all__ = ["fetch_available_voices", "speak"]
