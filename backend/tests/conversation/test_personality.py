import pytest

from companion.conversation.personality import Personality
from companion.conversation.safety import Mode

TEASING_MARKERS = ("Tease behaviour", "I'm writing it down", "light slang")


def test_the_real_personality_file_loads(personality: Personality) -> None:
    assert "Boundaries" in personality.sections


def test_normal_mode_has_the_full_personality(personality: Personality) -> None:
    prompt = personality.system_prompt(Mode.NORMAL, teasing_allowed=True)

    assert all(marker in prompt for marker in TEASING_MARKERS)


@pytest.mark.parametrize(
    ("mode", "teasing_allowed"),
    [
        (Mode.NORMAL, False),
        (Mode.SUPPORTIVE, True),
        (Mode.SUPPORTIVE, False),
        (Mode.CRISIS, True),
    ],
)
def test_gentle_prompts_contain_no_teasing_instructions(
    personality: Personality, mode: Mode, teasing_allowed: bool
) -> None:
    prompt = personality.system_prompt(mode, teasing_allowed=teasing_allowed)

    assert not any(marker in prompt for marker in TEASING_MARKERS)
    assert "not a therapist" in prompt
    assert "no emojis" in prompt


def test_crisis_prompt_forbids_medical_advice(personality: Personality) -> None:
    prompt = personality.system_prompt(Mode.CRISIS, teasing_allowed=True)

    assert "Do not diagnose" in prompt


def test_intro_text_before_the_first_heading_is_not_sent_to_the_model() -> None:
    markdown = "# Title\nNotes for humans.\n" + "".join(
        f"## {name}\nbody of {name}\n"
        for name in ("Voice", "Teasing rules", "Boundaries", "Style examples")
    )

    personality = Personality.from_markdown(markdown)

    assert "Notes for humans" not in personality.system_prompt(Mode.NORMAL, teasing_allowed=True)


def test_a_missing_section_is_reported() -> None:
    with pytest.raises(ValueError, match="Teasing rules, Style examples"):
        Personality.from_markdown("## Voice\nx\n## Boundaries\ny\n")


def test_example_sentences_are_extracted_for_the_copy_guard(personality: Personality) -> None:
    examples = personality.example_sentences

    assert "Pick a day, I'm writing it down." in examples
    assert "Don't get cocky, we're aiming for three." in examples
    assert "Look at you." not in examples
