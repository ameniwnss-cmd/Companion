import pytest

from companion.conversation.speech import FALLBACK_REPLY, to_speech


@pytest.mark.parametrize(
    ("raw", "spoken"),
    [
        ("Nice work.", "Nice work."),
        ("**Three** workouts? *Look* at you.", "Three workouts? Look at you."),
        ("## Plan\n- Pick a day\n- Start small", "Plan Pick a day Start small"),
        ("1. Study\n2) Sleep", "Study Sleep"),
        ("Let's go 💪🔥 bro", "Let's go bro"),
        ("You did it — finally!", "You did it, finally!"),
        ("  lots   of\n\nspace  ", "lots of space"),
    ],
)
def test_strips_formatting_that_cannot_be_spoken(raw: str, spoken: str) -> None:
    assert to_speech(raw) == spoken


def test_keeps_at_most_three_sentences() -> None:
    raw = "One. Two! Three? Four. Five."

    assert to_speech(raw) == "One. Two! Three?"


def test_empty_output_gets_a_fallback_reply() -> None:
    assert to_speech("** 🔥 **") == FALLBACK_REPLY
