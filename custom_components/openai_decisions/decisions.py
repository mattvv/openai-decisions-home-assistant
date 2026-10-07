"""Request building and answer parsing for /v1/decisions.

Kept free of Home Assistant imports so it can be unit tested on its own.
"""

from __future__ import annotations

import base64
from typing import Any

QUESTION_TYPES = ("predicate", "choice", "score")


class InvalidQuestion(ValueError):
    """A question the API would reject."""


def normalize_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate questions and expand shorthand.

    Choices and levels may be given as plain strings; the API wants objects with a
    description, so the string is used for both fields.
    """
    if not questions:
        raise InvalidQuestion("at least one question is required")
    out: list[dict[str, Any]] = []
    names: set[str] = set()
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise InvalidQuestion(f"question {i} is not a mapping")
        qtype = q.get("type", "predicate")
        name = q.get("name")
        instructions = q.get("instructions")
        if qtype not in QUESTION_TYPES:
            raise InvalidQuestion(f"question {i}: type must be one of {QUESTION_TYPES}")
        if not name or not isinstance(name, str):
            raise InvalidQuestion(f"question {i}: name is required")
        if name in names:
            raise InvalidQuestion(f"question {i}: duplicate name '{name}'")
        if not instructions or not isinstance(instructions, str):
            raise InvalidQuestion(f"question '{name}': instructions are required")
        names.add(name)
        nq: dict[str, Any] = {"type": qtype, "name": name, "instructions": instructions}
        if qtype == "choice":
            nq["choices"] = _options(q.get("choices"), "value", name, "choices", 2)
        elif qtype == "score":
            nq["levels"] = _options(q.get("levels"), "label", name, "levels", 2)
        out.append(nq)
    return out


def _options(raw: Any, key: str, name: str, field: str, minimum: int) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) < minimum:
        raise InvalidQuestion(f"question '{name}': {field} needs at least {minimum} entries")
    opts = []
    for opt in raw:
        if isinstance(opt, str):
            opts.append({key: opt, "description": opt})
        elif isinstance(opt, dict) and opt.get(key):
            opts.append({key: opt[key], "description": opt.get("description") or str(opt[key])})
        else:
            raise InvalidQuestion(f"question '{name}': each entry in {field} needs '{key}'")
    return opts


def image_part(content: bytes, content_type: str) -> dict[str, str]:
    """An input_image content part; the endpoint only takes inline base64."""
    data = base64.b64encode(content).decode("ascii")
    return {"type": "input_image", "image_url": f"data:{content_type};base64,{data}"}


def build_payload(
    model: str,
    questions: list[dict[str, Any]],
    text: str | None,
    images: list[dict[str, str]],
) -> dict[str, Any]:
    """Build the request body. Text-only input is sent as a plain string."""
    if not text and not images:
        raise InvalidQuestion("provide text, an image, or both")
    if images:
        content: list[dict[str, str]] = []
        if text:
            content.append({"type": "input_text", "text": text})
        content.extend(images)
        payload_input: Any = [{"role": "user", "content": content}]
    else:
        payload_input = text
    return {"model": model, "input": payload_input, "questions": questions}


def parse_answers(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Key the answers array by question name for easy templating.

    {"package": {"type": "predicate", "probability": 0.92}}
    """
    answers: dict[str, dict[str, Any]] = {}
    for ans in body.get("answers") or []:
        name = ans.get("name")
        if name:
            answers[name] = {k: v for k, v in ans.items() if k != "name"}
    return answers
