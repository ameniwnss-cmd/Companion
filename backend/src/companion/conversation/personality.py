import re
from dataclasses import dataclass
from pathlib import Path

from companion.conversation.safety import Mode

REQUIRED_SECTIONS = ("Voice", "Teasing rules", "Boundaries", "Style examples")

ROLE = "You are the user's voice companion: a close friend and productivity coach."
SPOKEN_FORMAT = (
    "Everything you write is spoken aloud. Reply in at most 3 short sentences, "
    "plain text only: no emojis, lists or markdown."
)
NO_TEASING = (
    "The user asked you to stop teasing. Do not tease, roast or joke at their expense. "
    "Stay warm, encouraging and practical until they say teasing is back on."
)
SUPPORTIVE = (
    "The user is having a hard time, or the topic is personal. Be warm, calm and steady. "
    "No jokes, no slang, no teasing, no judgment. Acknowledge how they feel, then offer one "
    "small, kind next step."
)
CRISIS = (
    "The user seems to be in real distress. Be calm, warm and steady. No jokes, no slang. "
    "Acknowledge what they feel and offer one simple grounding step, like one slow breath. "
    "Do not diagnose or give medical advice."
)

_HEADING = re.compile(r"^## (.+)$", re.MULTILINE)
_QUOTED = re.compile(r'^- "(.+)"$', re.MULTILINE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
MIN_EXAMPLE_SENTENCE = 15


@dataclass(frozen=True, slots=True)
class Personality:
    sections: dict[str, str]

    @classmethod
    def from_markdown(cls, markdown: str) -> "Personality":
        parts = _HEADING.split(markdown)
        sections = {
            title.strip(): body.strip()
            for title, body in zip(parts[1::2], parts[2::2], strict=True)
        }
        missing = [name for name in REQUIRED_SECTIONS if name not in sections]
        if missing:
            raise ValueError(f"personality.md is missing sections: {', '.join(missing)}")
        return cls(sections)

    @classmethod
    def load(cls, path: Path) -> "Personality":
        return cls.from_markdown(path.read_text(encoding="utf-8"))

    @property
    def example_sentences(self) -> tuple[str, ...]:
        quoted = _QUOTED.findall(self.sections["Style examples"])
        sentences = (s.strip() for q in quoted for s in _SENTENCE_END.split(q))
        return tuple(s for s in sentences if len(s) >= MIN_EXAMPLE_SENTENCE)

    def system_prompt(
        self, mode: Mode, *, teasing_allowed: bool, include_examples: bool = True
    ) -> str:
        s = self.sections
        match mode:
            case Mode.CRISIS:
                parts = [ROLE, SPOKEN_FORMAT, s["Boundaries"], CRISIS]
            case Mode.SUPPORTIVE:
                parts = [ROLE, SPOKEN_FORMAT, s["Boundaries"], SUPPORTIVE]
            case Mode.NORMAL if teasing_allowed:
                parts = [ROLE, s["Voice"], s["Teasing rules"], s["Boundaries"]]
                if include_examples:
                    parts.append(s["Style examples"])
            case Mode.NORMAL:
                parts = [ROLE, SPOKEN_FORMAT, s["Boundaries"], NO_TEASING]
        return "\n\n".join(parts)
