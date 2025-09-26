"""Async persona conversation demo with pluggable post-turn hooks and multi-LLM support."""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import requests

from engine import (
    Agent,
    Conversation,
    ConversationTurn,
    GeminiLLMClient,
    GrokLLMClient,
    OpenAILLMClient,
    Persona,
    PromptSet,
    TemplateRenderer,
    load_personas,
    load_prompts,
)

TurnHook = Callable[[ConversationTurn, int], Awaitable[None]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an async persona-driven banter session.")
    parser.add_argument(
        "--topic",
        default="Should we launch a banter podcast for our social-media reader?",
        help="Conversation topic shared with every agent.",
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=["PRO", "CON", "CHAOS", "MOD"],
        metavar="PERSONA",
        help="Ordered list of persona keys to include.",
    )
    parser.add_argument("--default-provider", default="openai", help="Fallback provider if persona lacks llm settings.")
    parser.add_argument("--default-model", default="gpt-4o-mini", help="Fallback model if persona lacks llm model.")
    parser.add_argument("--rounds", type=int, default=1, help="Number of rounds; each agent speaks once per round.")
    parser.add_argument(
        "--history",
        type=Path,
        help="Optional JSON file providing prior conversation history.",
    )
    parser.add_argument("--round-rule", dest="round_rule", help="Override the default round rule shared with agents.")
    parser.add_argument("--length-limit", type=int, help="Override the default character limit shared with agents.")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds to wait after each turn (e.g. to allow external playback).",
    )
    parser.add_argument(
        "--flask-url",
        default=os.getenv("BANTER_FLASK_URL", "http://127.0.0.1:5053/"),
        help="Agent playback server base URL. Set to 'none' to disable automatic playback.",
    )
    parser.add_argument(
        "--hook",
        help="Optional dotted path to an async function invoked after each turn. Signature: async def hook(turn, round_index).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the conversation as JSON records instead of plain text.",
    )
    return parser.parse_args()


def build_agent(
    key: str,
    persona: Persona,
    llm,
    prompts: PromptSet,
    renderer: TemplateRenderer,
    llm_display: str,
    base_parameters: Dict[str, Any],
) -> Agent:
    parameters = {key: value for key, value in base_parameters.items()}
    voice = persona.style.get("voice") if isinstance(persona.style, dict) else None
    if isinstance(voice, str) and voice:
        style_cfg = parameters.setdefault("style", {}) if isinstance(parameters, dict) else {}
        if isinstance(style_cfg, dict):
            style_cfg.setdefault("voice", voice)
            parameters["style"] = style_cfg
    return Agent(
        key=key,
        persona=persona,
        prompts=prompts,
        renderer=renderer,
        llm=llm,
        llm_display=llm_display,
        parameters=parameters,
    )


def load_history(path: Path) -> List[ConversationTurn]:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, list):  # pragma: no cover - defensive path.
        raise ValueError("History JSON must be a list of objects")
    turns: List[ConversationTurn] = []
    for entry in raw:
        if not isinstance(entry, dict) or "speaker" not in entry or "text" not in entry:
            raise ValueError("History entries must be objects with 'speaker' and 'text'")
        turns.append(
            ConversationTurn(
                speaker=entry["speaker"],
                text=entry["text"],
                llm_display=entry.get("llm_display", ""),
                parameters=entry.get("parameters", {}),
            )
        )
    return turns


def resolve_hook(path: Optional[str]) -> Optional[TurnHook]:
    if not path:
        return None
    module_name, _, attr = path.rpartition(".")
    if not module_name:
        raise SystemExit("--hook must be a dotted path like pkg.module.func")
    module = importlib.import_module(module_name)
    hook = getattr(module, attr, None)
    if hook is None:
        raise SystemExit(f"Hook '{path}' not found")
    if not asyncio.iscoroutinefunction(hook):
        raise SystemExit("Hook must be an async function accepting (turn, round_index)")
    return hook  # type: ignore[return-value]


def get_api_key(provider: str, config: Dict[str, Any], persona_key: str) -> Tuple[str, str]:
    explicit = config.get("api_key")
    api_key_env = config.get("api_key_env")
    if explicit:
        if not isinstance(explicit, str):
            raise SystemExit(f"Persona {persona_key} llm.api_key must be a string if provided")
        env_identifier = api_key_env if isinstance(api_key_env, str) else ""
        return explicit, env_identifier

    if not isinstance(api_key_env, str) or not api_key_env:
        if provider == "openai":
            api_key_env = "OPENAI_API_KEY"
        elif provider == "gemini":
            api_key_env = "GEMINI_API_KEY"
        elif provider == "grok":
            api_key_env = "GROK_API_KEY"
        else:
            raise SystemExit(f"Unknown provider '{provider}' for persona {persona_key} - specify llm.api_key_env")

    api_key = os.getenv(api_key_env)
    if not api_key:
        raise SystemExit(f"Persona {persona_key} requires environment variable {api_key_env} to be set")
    return api_key, api_key_env


def build_llm_clients(
    persona_map: Dict[str, Persona],
    selected_keys: Tuple[str, ...],
    default_provider: str,
    default_model: str,
) -> Dict[str, Tuple[object, str, Dict[str, Any]]]:
    cache: Dict[Tuple[str, str, str], object] = {}
    resolved: Dict[str, Tuple[object, str, Dict[str, Any]]] = {}

    for key in selected_keys:
        persona = persona_map[key]
        config = persona.llm or {}
        provider = (config.get("provider") or default_provider).lower()
        model = config.get("model") or default_model
        if not model:
            raise SystemExit(f"Persona {key} needs an llm.model or specify --default-model")

        api_key, cache_env = get_api_key(provider, config, key)
        client_options = config.get("client_options")
        if not isinstance(client_options, dict):
            client_options = {}
        cache_identifier = cache_env or f"key:{hash(api_key)}"
        cache_key = (provider, model, cache_identifier)
        if cache_key not in cache:
            if provider == "openai":
                cache[cache_key] = OpenAILLMClient(model=model, api_key=api_key, default_options=client_options)
            elif provider == "gemini":
                cache[cache_key] = GeminiLLMClient(model=model, api_key=api_key, client_options=client_options)
            elif provider == "grok":
                cache[cache_key] = GrokLLMClient(model=model, api_key=api_key, client_options=client_options)
            else:
                raise SystemExit(f"Unsupported LLM provider '{provider}' for persona {key}")
        display = config.get("display")
        if not isinstance(display, str) or not display:
            display = provider
        params: Dict[str, Any] = {}
        voice = persona.style.get("voice") if isinstance(persona.style, dict) else None
        if isinstance(voice, str) and voice:
            params["style"] = {"voice": voice}
        resolved[key] = (cache[cache_key], display, params)

    return resolved


async def run_async(args: argparse.Namespace) -> None:
    if args.rounds < 1:
        raise SystemExit("--rounds must be at least 1")

    root = Path(__file__).resolve().parent
    personas = load_personas(root / "codex" / "personas.yaml")

    missing = [key for key in args.agents if key not in personas]
    if missing:
        raise SystemExit(f"Unknown persona keys: {', '.join(missing)}")

    prompts = load_prompts(root / "codex" / "prompts")
    renderer = TemplateRenderer()

    selected_keys = tuple(args.agents)
    llm_map = build_llm_clients(personas, selected_keys, args.default_provider, args.default_model)

    agents = [
        build_agent(key, personas[key], llm_map[key][0], prompts, renderer, llm_map[key][1], llm_map[key][2])
        for key in selected_keys
    ]

    conversation = Conversation(topic=args.topic)
    records: List[Dict[str, Any]] = []

    if args.history:
        history_turns = load_history(args.history)
        conversation.turns.extend(history_turns)
        if history_turns:
            for turn in history_turns:
                label = turn.llm_display or personas[turn.speaker].llm.get("display") or personas[turn.speaker].llm.get("provider", "")
                record = {
                    "agent": turn.speaker,
                    "llm": label,
                    "text": turn.text,
                    "parameters": turn.parameters or llm_map.get(turn.speaker, (None, label, {}))[2],
                }
                records.append(record)
                if not args.json:
                    suffix = f" ({label})" if label else ""
                    print(f"- {turn.speaker}{suffix}: {turn.text}")
            if not args.json:
                print("\nContinuing conversation...\n")

    hook = resolve_hook(args.hook)

    flask_url = (args.flask_url or "").strip()
    if flask_url.lower() == "none":
        flask_url = ""

    for round_index in range(args.rounds):
        for agent in agents:
            turn = await conversation.astep(
                agent,
                round_rule=args.round_rule,
                length_limit=args.length_limit,
            )
            label = turn.llm_display or personas[turn.speaker].llm.get("display") or personas[turn.speaker].llm.get("provider", "")
            suffix = f" ({label})" if label else ""
            record = {
                "agent": turn.speaker,
                "llm": label,
                "text": turn.text,
                "parameters": turn.parameters or llm_map[turn.speaker][2],
            }
            records.append(record)
            if not args.json:
                print(f"[{round_index + 1}] {turn.speaker}{suffix}: {turn.text}\n")

            if hook is not None:
                await hook(turn, round_index)

            if flask_url:
                await broadcast_to_flask(flask_url, turn)

            if args.delay > 0:
                await asyncio.sleep(args.delay)

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print("Conversation complete. Final transcript:")
        for record in records:
            label = record["llm"]
            suffix = f" ({label})" if label else ""
            print(f"- {record['agent']}{suffix}: {record['text']}")


async def broadcast_to_flask(base_url: str, turn: ConversationTurn) -> None:
    """Send the current turn to the Flask playback server."""

    agent_id = (turn.speaker or "").strip()
    if not agent_id:
        return

    payload = {"agent_id": agent_id, "text": turn.text}
    endpoint = base_url.rstrip("/") + "/api/speak"

    def _request() -> None:
        try:
            response = requests.post(endpoint, json=payload, timeout=120)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - best effort side effect.
            print(f"[flask] Failed to trigger playback for {agent_id}: {exc}")

    await asyncio.to_thread(_request)


def main() -> None:
    args = parse_args()
    asyncio.run(run_async(args))


if __name__ == "__main__":
    main()
