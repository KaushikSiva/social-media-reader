"""Conversation simulator wiring personas, prompts, and pluggable LLM clients."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence
import re

try:  # PyYAML is optional but required to load personas.
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - surfaced with a helpful error later.
    yaml = None


@dataclass
class Persona:
    """Container for a single persona’s configuration."""

    key: str
    name: str
    role: str
    worldview: Dict[str, Any]
    style: Dict[str, Any]
    examples: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, key: str, raw: Dict[str, Any]) -> "Persona":
        return cls(
            key=key,
            name=raw.get("name", key),
            role=raw.get("role", ""),
            worldview=raw.get("worldview", {}),
            style=raw.get("style", {}),
            examples=raw.get("examples", []),
        )

    def to_template_context(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "role": self.role,
            "worldview": self.worldview,
            "style": self.style,
            "examples": self.examples,
        }


@dataclass
class PromptSet:
    """Grouped prompt templates for a single agent invocation."""

    system: str
    developer: str
    user: str


@dataclass
class ConversationTurn:
    speaker: str
    text: str

    def as_dict(self) -> Dict[str, str]:
        return {"speaker": self.speaker, "text": self.text}


class LLMClient(Protocol):
    """Minimal interface expected from any language model backend."""

    def complete(self, messages: Sequence[Dict[str, str]], **kwargs: Any) -> str:
        """Return the model response for the provided chat messages."""


class EchoLLMClient:
    """Fallback client useful for local smoke tests."""

    def complete(self, messages: Sequence[Dict[str, str]], **_: Any) -> str:  # pragma: no cover - test double.
        last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
        payload = last_user["content"] if last_user else ""
        return f"[echo] {payload.strip()}"


class TemplateRenderer:
    """Very small Handlebars-inspired renderer for the project templates."""

    _section_re = re.compile(r"{{#(each|if) ([^}]+)}}")
    _open_re = re.compile(r"{{#(each|if) [^}]+}}")
    _var_re = re.compile(r"{{([^#/{][^}]*)}}")

    def render(self, template: str, context: Dict[str, Any]) -> str:
        return self._render(template, [context])

    def _render(self, template: str, context_stack: List[Dict[str, Any]]) -> str:
        result: List[str] = []
        idx = 0
        while idx < len(template):
            match = self._section_re.search(template, idx)
            if not match:
                result.append(self._replace_variables(template[idx:], context_stack))
                break

            start, section_start = match.span()
            result.append(self._replace_variables(template[idx:start], context_stack))

            tag_type = match.group(1)
            expression = match.group(2).strip()
            section_body, section_end = self._extract_section(template, section_start, tag_type)

            if tag_type == "each":
                values = self._resolve(expression, context_stack)
                if values:
                    iterable: Iterable[Any]
                    if isinstance(values, dict):
                        iterable = values.items()
                    elif isinstance(values, (str, bytes)):
                        iterable = [values]
                    elif isinstance(values, Iterable):
                        iterable = values
                    else:
                        iterable = []
                    for item in iterable:
                        layer = self._build_layer(item)
                        result.append(self._render(section_body, [layer] + context_stack))
            else:  # if-block
                value = self._resolve(expression, context_stack)
                if value:
                    layer = self._build_layer(value)
                    result.append(self._render(section_body, [layer] + context_stack))

            idx = section_end

        return "".join(result)

    def _build_layer(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            layer = dict(value)
            layer.setdefault("this", value)
            return layer
        if isinstance(value, tuple) and len(value) == 2:
            key, val = value
            return {"key": key, "value": val, "this": value}
        return {"this": value}

    def _replace_variables(self, text: str, context_stack: List[Dict[str, Any]]) -> str:
        def repl(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            value = self._resolve(expr, context_stack)
            return "" if value is None else str(value)

        return self._var_re.sub(repl, text)

    def _extract_section(self, template: str, start: int, tag_type: str) -> (str, int):
        close_tag = f"{{{{/{tag_type}}}}}"
        idx = start
        depth = 1
        while depth:
            next_open = self._open_re.search(template, idx)
            next_close = template.find(close_tag, idx)
            if next_close == -1:
                raise ValueError(f"Unclosed section for {tag_type}")
            if next_open and next_open.start() < next_close:
                depth += 1
                idx = next_open.end()
            else:
                depth -= 1
                idx = next_close + len(close_tag)
        body_start = start
        body_end = idx - len(close_tag)
        return template[body_start:body_end], idx

    def _resolve(self, expression: str, context_stack: List[Dict[str, Any]]) -> Any:
        path = expression.split('.')
        for layer in context_stack:
            if path[0] in layer:
                value: Any = layer[path[0]]
                for part in path[1:]:
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        value = getattr(value, part, None)
                    if value is None:
                        break
                else:
                    return value
                if value is not None:
                    return value
        return None


@dataclass
class Agent:
    """Wraps a persona, prompt set, and model client to produce replies."""

    key: str
    persona: Persona
    prompts: PromptSet
    renderer: TemplateRenderer
    llm: LLMClient
    default_round_rule: str = "Keep the banter friendly."
    default_length_limit: int = 280

    def respond(
        self,
        conversation: "Conversation",
        *,
        topic: str,
        round_rule: Optional[str] = None,
        length_limit: Optional[int] = None,
        llm_options: Optional[Dict[str, Any]] = None,
    ) -> ConversationTurn:
        ctx = {
            "persona": self.persona.to_template_context(),
            "round_rule": round_rule or self.default_round_rule,
            "length_limit": length_limit or self.default_length_limit,
            "topic": topic,
            "history": [turn.as_dict() for turn in conversation.turns],
        }

        messages = [
            {"role": "system", "content": self.renderer.render(self.prompts.system, ctx)},
            {"role": "system", "content": self.renderer.render(self.prompts.developer, ctx)},
            {"role": "user", "content": self.renderer.render(self.prompts.user, ctx)},
        ]

        payload = self.llm.complete(messages, **(llm_options or {}))
        reply = payload.strip()
        return ConversationTurn(speaker=self.persona.key, text=reply)


@dataclass
class Conversation:
    """Stateful transcript shared by a group of agents."""

    topic: str
    turns: List[ConversationTurn] = field(default_factory=list)

    def step(
        self,
        agent: Agent,
        *,
        round_rule: Optional[str] = None,
        length_limit: Optional[int] = None,
        llm_options: Optional[Dict[str, Any]] = None,
    ) -> ConversationTurn:
        turn = agent.respond(
            self,
            topic=self.topic,
            round_rule=round_rule,
            length_limit=length_limit,
            llm_options=llm_options,
        )
        self.turns.append(turn)
        return turn

    def as_history(self) -> List[Dict[str, str]]:
        return [turn.as_dict() for turn in self.turns]


def load_personas(path: Path) -> Dict[str, Persona]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load persona definitions")
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    personas: Dict[str, Persona] = {}
    for key, raw in payload.get("personas", {}).items():
        personas[key] = Persona.from_dict(key, raw)
    return personas


def load_prompts(base_dir: Path) -> PromptSet:
    system = (base_dir / "system.md").read_text(encoding="utf-8")
    developer = (base_dir / "developer.md").read_text(encoding="utf-8")
    user = (base_dir / "user.md").read_text(encoding="utf-8")
    return PromptSet(system=system, developer=developer, user=user)


if __name__ == "__main__":  # pragma: no cover - convenience smoke test.
    root = Path(__file__).resolve().parent.parent
    personas = load_personas(root / "codex" / "personas.yaml")
    prompts = load_prompts(root / "codex" / "prompts")

    renderer = TemplateRenderer()
    llm = EchoLLMClient()
    pro_agent = Agent(
        key="PRO",
        persona=personas["PRO"],
        prompts=prompts,
        renderer=renderer,
        llm=llm,
    )
    con_agent = Agent(
        key="CON",
        persona=personas["CON"],
        prompts=prompts,
        renderer=renderer,
        llm=llm,
    )

    convo = Conversation(topic="Should we build the toast-rating AI?")
    for agent in (pro_agent, con_agent):
        turn = convo.step(agent)
        print(f"{turn.speaker}: {turn.text}")
