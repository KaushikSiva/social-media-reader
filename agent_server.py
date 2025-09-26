"""Flask server that speaks text for agents, assigns images, and renders a Zoom-style UI."""

from __future__ import annotations

import os
import random
from importlib import import_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flask import Flask, abort, jsonify, render_template, request, send_file, url_for

from speak_agent import (
    VOICE_ASSIGNMENTS,
    clear_voice_assignment,
    get_or_assign_voice,
    mark_voice_unusable,
)
from tts_voice import speak as tts_provider

INWORLD_TTS = import_module("tts_voice.speak")

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
IMAGE_DIR = Path(os.path.expanduser("~/Downloads/rand"))
IMAGE_ASSIGNMENTS: Dict[str, Path] = {}
AGENT_STATES: Dict[str, Dict[str, str]] = {}
LAST_AGENT_ID: Optional[str] = None
STATE_VERSION: int = 0

app = Flask(__name__)


def _list_image_files() -> List[Path]:
    if not IMAGE_DIR.exists():
        raise RuntimeError(f"Image directory not found: {IMAGE_DIR}")

    files = [p for p in IMAGE_DIR.iterdir() if p.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS and p.is_file()]
    if not files:
        raise RuntimeError(f"No image files found in {IMAGE_DIR}")
    return files


def get_or_assign_image(agent_id: str) -> Path:
    assigned = IMAGE_ASSIGNMENTS.get(agent_id)
    if assigned and assigned.exists():
        return assigned

    available = _list_image_files()
    existing = {path for path in IMAGE_ASSIGNMENTS.values() if path.exists()}

    normalized = _normalize(agent_id)

    def _score(path: Path) -> int:
        stem = _normalize(path.stem)
        if stem == normalized:
            return 3
        if normalized and normalized in stem:
            return 2
        return 1

    # Prefer images whose filename matches the agent id; avoid using files already
    # assigned to other agents unless there is an exact match.
    candidates = sorted(available, key=lambda p: (-_score(p), p.name.lower()))
    image_path: Optional[Path] = None
    for candidate in candidates:
        if candidate in existing and _score(candidate) < 3:
            continue
        image_path = candidate
        break

    if image_path is None:
        image_path = random.choice(available)

    IMAGE_ASSIGNMENTS[agent_id] = image_path
    return image_path


def _normalize(value: str) -> str:
    return value.lower().replace(" ", "").replace("_", "")


def _update_agent_state(agent_id: str, text: str, voice_id: str) -> None:
    global LAST_AGENT_ID

    VOICE_ASSIGNMENTS[agent_id] = voice_id
    AGENT_STATES[agent_id] = {"text": text, "voice_id": voice_id}
    LAST_AGENT_ID = agent_id


@app.route("/")
def index():
    agent_id = request.args.get("agent_id", "").strip()
    text = request.args.get("text", "").strip()

    context: Dict[str, Optional[str]] = {
        "agent_id": agent_id,
        "voice_id": None,
        "image_url": None,
        "message": None,
        "error": None,
    }

    if agent_id and text:
        try:
            voice_id = handle_speech(agent_id, text)
            context["voice_id"] = voice_id
            context["image_url"] = url_for("agent_image", agent_id=agent_id)
            context["message"] = "Playback complete."
        except Exception as exc:  # pragma: no cover - interactive failure
            context["error"] = str(exc)
    elif agent_id or text:
        context["error"] = "Both agent_id and text query parameters are required."

    full_context = build_participant_context(agent_id)
    full_context.update(context)
    return render_template("agent.html", **full_context)


@app.route("/agent_image/<agent_id>")
def agent_image(agent_id: str):
    image_path = get_or_assign_image(agent_id)
    if not image_path or not image_path.exists():
        abort(404)

    return send_file(image_path)


@app.post("/api/speak")
def api_speak():
    payload = request.get_json(silent=True) or {}
    agent_id = (payload.get("agent_id") or "").strip()
    text = (payload.get("text") or "").strip()

    if not agent_id or not text:
        abort(400, description="JSON body must include 'agent_id' and 'text'.")

    try:
        voice_id = handle_speech(agent_id, text)
    except Exception as exc:  # pragma: no cover - integration failure
        abort(500, description=str(exc))

    return jsonify({
        "status": "ok",
        "agent_id": agent_id,
    })


def build_participant_context(active_query_agent: Optional[str]) -> Dict[str, object]:
    participants = []
    for participant_id, path in IMAGE_ASSIGNMENTS.items():
        if not path.exists():
            continue
        state = AGENT_STATES.get(participant_id, {})
        participants.append(
            {
                "agent_id": participant_id,
                "voice_id": state.get("voice_id"),
                "text": state.get("text"),
                "image_url": url_for("agent_image", agent_id=participant_id),
            }
        )

    participants.sort(key=lambda item: item["agent_id"])

    active_id = (active_query_agent or "").strip() or LAST_AGENT_ID

    active_participant = None
    if active_id:
        active_participant = next(
            (p for p in participants if p["agent_id"] == active_id and p.get("text")),
            None,
        )

    if active_participant is None and participants:
        active_participant = next((p for p in participants if p.get("text")), participants[0])

    other_participants = [p for p in participants if p is not active_participant]

    return {
        "participants": participants,
        "active_participant": active_participant,
        "other_participants": other_participants,
        "active_text": (active_participant or {}).get("text"),
        "state_version": STATE_VERSION,
    }


def handle_speech(agent_id: str, text: str) -> str:
    if not text:
        raise ValueError("Text must be non-empty")

    voice_id = get_or_assign_voice(agent_id)
    get_or_assign_image(agent_id)
    _update_agent_state(agent_id, text, voice_id)

    try:
        tts_provider.speak(text, voice_id)
    except Exception as exc:  # pragma: no cover - external TTS failure
        print(f"[tts] Playback failed for {agent_id}: {exc}")
        mark_voice_unusable(voice_id)
        clear_voice_assignment(agent_id)
        fallback_voice = get_or_assign_voice(agent_id)
        fallback_success, fallback_voice = _attempt_elevenlabs_retry(agent_id, text, voice_id)
        if not fallback_success:
            fallback_voice = _attempt_inworld_fallback(agent_id, text)
            if fallback_voice:
                voice_id = fallback_voice
                _update_agent_state(agent_id, text, voice_id)

    global STATE_VERSION
    STATE_VERSION += 1
    return voice_id


def _attempt_elevenlabs_retry(agent_id: str, text: str, failed_voice: str) -> Tuple[bool, Optional[str]]:
    clear_voice_assignment(agent_id)
    try:
        fallback_voice = get_or_assign_voice(agent_id)
    except RuntimeError as exc:  # No voices left
        print(f"[tts] Retry skipped for {agent_id}: {exc}")
        return False, None

    if fallback_voice == failed_voice:
        print(f"[tts] No alternative ElevenLabs voice available for {agent_id} after failure.")
        return False, None

    try:
        tts_provider.speak(text, fallback_voice)
        _update_agent_state(agent_id, text, fallback_voice)
        return True, fallback_voice
    except Exception as retry_exc:  # pragma: no cover - secondary failure
        print(f"[tts] Retry failed for {agent_id}: {retry_exc}")
        mark_voice_unusable(fallback_voice)
        return False, None


def _attempt_inworld_fallback(agent_id: str, text: str) -> Optional[str]:
    token = os.getenv("INWORLD_API_TOKEN")
    if not token:
        print("[tts] Inworld fallback skipped: missing INWORLD_API_TOKEN.")
        return None

    try:
        voices = INWORLD_TTS.fetch_available_voices()
    except Exception as exc:  # pragma: no cover
        print(f"[tts] Inworld fallback failed to fetch voices: {exc}")
        return None

    if not voices:
        print("[tts] Inworld fallback found no available voices.")
        return None

    voice_id = voices[0]
    try:
        INWORLD_TTS.speak(text, voice_id)
        print(f"[tts] Inworld fallback succeeded for {agent_id} using voice {voice_id}.")
        return f"inworld:{voice_id}"
    except Exception as exc:  # pragma: no cover
        print(f"[tts] Inworld fallback failed for {agent_id}: {exc}")
        return None


@app.get("/api/state_version")
def api_state_version():
    return jsonify({
        "version": STATE_VERSION,
        "active_agent": LAST_AGENT_ID,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5053)
