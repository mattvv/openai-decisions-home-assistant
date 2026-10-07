"""Payload building and answer parsing."""

import pytest

from custom_components.openai_decisions.decisions import (
    InvalidQuestion,
    build_payload,
    image_part,
    normalize_questions,
    parse_answers,
)


def test_predicate_defaults_type():
    assert normalize_questions([{"name": "p", "instructions": "Is it?"}]) == [
        {"type": "predicate", "name": "p", "instructions": "Is it?"}
    ]


def test_choice_and_level_shorthand():
    qs = normalize_questions(
        [
            {"type": "choice", "name": "c", "instructions": "Which?", "choices": ["a", {"value": "b", "description": "B"}]},
            {"type": "score", "name": "s", "instructions": "How bad?", "levels": ["low", "high"]},
        ]
    )
    assert qs[0]["choices"] == [{"value": "a", "description": "a"}, {"value": "b", "description": "B"}]
    assert qs[1]["levels"] == [{"label": "low", "description": "low"}, {"label": "high", "description": "high"}]


@pytest.mark.parametrize(
    "questions",
    [
        [],
        [{"name": "x"}],
        [{"instructions": "y"}],
        [{"type": "bogus", "name": "x", "instructions": "y"}],
        [{"type": "choice", "name": "x", "instructions": "y", "choices": ["only"]}],
        [{"name": "x", "instructions": "y"}, {"name": "x", "instructions": "z"}],
    ],
)
def test_invalid_questions(questions):
    with pytest.raises(InvalidQuestion):
        normalize_questions(questions)


def test_text_only_payload_is_string():
    q = normalize_questions([{"name": "p", "instructions": "?"}])
    assert build_payload("m", q, "hello", [])["input"] == "hello"


def test_image_payload():
    img = image_part(b"\xff\xd8", "image/jpeg")
    assert img == {"type": "input_image", "image_url": "data:image/jpeg;base64,/9g="}
    q = normalize_questions([{"name": "p", "instructions": "?"}])
    payload = build_payload("gpt-6-luna", q, "ctx", [img])
    assert payload["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "ctx"}, img]}
    ]


def test_no_input_rejected():
    q = normalize_questions([{"name": "p", "instructions": "?"}])
    with pytest.raises(InvalidQuestion):
        build_payload("m", q, None, [])


def test_parse_answers():
    body = {
        "answers": [
            {"type": "predicate", "name": "package", "probability": 0.92},
            {"type": "refusal", "name": "other"},
        ]
    }
    assert parse_answers(body) == {
        "package": {"type": "predicate", "probability": 0.92},
        "other": {"type": "refusal"},
    }
