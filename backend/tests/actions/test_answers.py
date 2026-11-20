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
    ],
)
def test_no(text: str) -> None:
    assert classify_answer(text) is Answer.NO


@pytest.mark.parametrize(
    "text",
    [
        "",
        "yes but make it 7pm",
        "no, make it 7pm instead",
        "what time did you say?",
        "I went to the gym today",
        "yes yes yes yes yes yes",
    ],
)
def test_anything_else_is_not_an_answer(text: str) -> None:
    assert classify_answer(text) is Answer.OTHER
