import pytest

from companion.actions.answers import Answer, classify_answer


@pytest.mark.parametrize(
    "text",
    [
        "yes",
        "Yes!",
        "yeah",
        "yep please",
        "ok",
        "okay do it",
        "sure",
        "go ahead",
        "save it",
        "sounds good",
        "perfect thanks",
        "please do",
        "yes please save it",
        "Yes, David.",
        "Yeah, do that.",
        "Oh yeah, that's right",
        "sure thing",
        "yes yes yes yes yes yes",
        "save them all",
    ],
)
def test_yes(text: str) -> None:
    assert classify_answer(text) is Answer.YES


@pytest.mark.parametrize(
    "text",
    [
        "no",
        "No.",
        "nope",
        "nah",
        "cancel",
        "cancel it",
        "no thanks",
        "never mind",
        "not now",
        "don\N{RIGHT SINGLE QUOTATION MARK}t save it",
        "forget it",
        "scrap that",
        "No, David.",
        "um no",
    ],
)
def test_no(text: str) -> None:
    assert classify_answer(text) is Answer.NO


@pytest.mark.parametrize(
    "text",
    ["undo", "Undo that.", "take it back", "take that back please", "uh, undo it"],
)
def test_undo(text: str) -> None:
    assert classify_answer(text) is Answer.UNDO


@pytest.mark.parametrize(
    "text",
    [
        "and do",
        "And do.",
        "and do it",
        "an do that",
        "un-do",
        "on do please",
        "Undue.",
        "um, and do",
    ],
)
def test_common_mishearings_of_undo_still_undo(text: str) -> None:
    assert classify_answer(text) is Answer.UNDO


@pytest.mark.parametrize(
    "text",
    ["and do the dishes", "and do it tomorrow", "on doing my homework", "and then do it"],
)
def test_a_mishearing_only_counts_on_its_own(text: str) -> None:
    assert classify_answer(text) is not Answer.UNDO


@pytest.mark.parametrize(
    "text",
    [
        "",
        "yes but make it 7pm",
        "no, make it 7pm instead",
        "okay and also remind me to buy milk",
        "yeah, add another one for Friday",
        "what time did you say?",
        "I went to the gym today",
        "yes I think I will go to the gym later tonight",
        "hmm",
    ],
)
def test_anything_else_is_not_an_answer(text: str) -> None:
    assert classify_answer(text) is Answer.OTHER
