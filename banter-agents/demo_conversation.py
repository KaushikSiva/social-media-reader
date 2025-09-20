"""Example script demonstrating persona-driven conversation using OpenAI."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List

from engine import (
    Agent,
    Conversation,
    ConversationTurn,
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
        "--model",
        default="gpt-4o-mini",
        help="OpenAI chat model identifier.",
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=["PRO", "CON", "CHAOS"],
        metavar="PERSONA",
        help="Ordered list of persona keys to include.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="Number of rounds (each agent speaks once per round).",
    )
    parser.add_argument(
        "--history",
        type=Path,
        help="Optional JSON file providing prior conversation history.",
    )
    parser.add_argument(
        "--round-rule",
        dest="round_rule",
        help="Override the default round rule shared with agents.",
    )
    parser.add_argument(
        "--length-limit",
        type=int,
        help="Override the default character limit shared with agents.",
    )
    return parser.parse_args()


def build_agent(
    key: str,
    persona: Persona,
    llm: OpenAILLMClient,
    prompts: PromptSet,
    renderer: TemplateRenderer,
) -> Agent:
    return Agent(
        key=key,
        persona=persona,
        prompts=prompts,
        renderer=renderer,
        llm=llm,
    )


def load_history(path: Path) -> List[ConversationTurn]:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    turns: List[ConversationTurn] = []
    for entry in raw:
        if not isinstance(entry, dict) or "speaker" not in entry or "text" not in entry:
            raise ValueError("History entries must be objects with 'speaker' and 'text'")
        turns.append(ConversationTurn(speaker=entry["speaker"], text=entry["text"]))
    return turns


def main() -> None:
    args = parse_args()

    if args.rounds < 1:
        raise SystemExit("--rounds must be at least 1")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Set OPENAI_API_KEY before running this script.")

    root = Path(__file__).resolve().parent
    personas = load_personas(root / "codex" / "personas.yaml")

    missing = [key for key in args.agents if key not in personas]
    if missing:
        raise SystemExit(f"Unknown persona keys: {', '.join(missing)}")

    llm = OpenAILLMClient(model=args.model, api_key=api_key)
    renderer = TemplateRenderer()
    prompts = load_prompts(root / "codex" / "prompts")

    agents: List[Agent] = [
        build_agent(key, personas[key], llm, prompts, renderer) for key in args.agents
    ]

    conversation = Conversation(topic=args.topic)

    if args.history:
        history_turns = load_history(args.history)
        conversation.turns.extend(history_turns)
        if history_turns:
            print("Preloaded history:")
            for turn in history_turns:
                print(f"- {turn.speaker}: {turn.text}")
            print("\nContinuing conversation...\n")

    for round_index in range(args.rounds):
        for agent in agents:
            turn = conversation.step(
                agent,
                round_rule=args.round_rule,
                length_limit=args.length_limit,
            )
            print(f"[{round_index + 1}] {turn.speaker}: {turn.text}\n")

    print("Conversation complete. Final transcript:")
    for turn in conversation.turns:
        print(f"- {turn.speaker}: {turn.text}")


if __name__ == "__main__":
    main()
