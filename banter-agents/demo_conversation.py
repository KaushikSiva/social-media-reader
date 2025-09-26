"""Example script demonstrating persona-driven conversation with configurable LLMs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from engine import (
    Agent,
    Conversation,
    GeminiLLMClient,
    GrokLLMClient,
    OpenAILLMClient,
    Persona,
    PromptSet,
    TemplateRenderer,
    load_personas,
    load_prompts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a persona-driven banter session.")
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
    parser.add_argument(
        "--default-provider",
        default="openai",
        help="Fallback provider when a persona lacks an explicit llm block.",
    )
    parser.add_argument(
        "--default-model",
        default="gpt-4o-mini",
        help="Fallback model when a persona lacks an explicit llm model.",
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


def main() -> None:
    args = parse_args()

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

    records = []
    for agent in agents:
        turn = conversation.step(agent)
        label = turn.llm_display or personas[turn.speaker].llm.get("display") or personas[turn.speaker].llm.get("provider", "")
        suffix = f" ({label})" if label else ""
        record = {
            "agent": turn.speaker,
            "llm": label,
            "text": turn.text,
            "parameters": turn.parameters or llm_map[turn.speaker][2],
        }
        records.append(record)
        if not getattr(args, "json", False):
            print(f"{turn.speaker}{suffix}: {turn.text}\n")

    if getattr(args, "json", False):
        print(json.dumps(records, indent=2))
    else:
        print("Full history:")
        for record in records:
            label = record["llm"]
            suffix = f" ({label})" if label else ""
            print(f"- {record['agent']}{suffix}: {record['text']}")


if __name__ == "__main__":
    main()
