"""Parse one-shot question flags into TypeSafe question objects."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError
from typesafe_sdk import Choice, Noul, Score

Question = Noul | Choice | Score

QUESTION_FLAGS = ("--noul", "--choice", "--score", "--questions")
_MAX_CHOICE_LABELS = 255
_MIN_SCORE_LEVELS = 2
_MAX_SCORE_LEVELS = 10


class QuestionSpecError(Exception):
    """A question flag is missing, malformed, or inconsistent."""


def ordered_question_args(args: Sequence[str]) -> list[tuple[str, str]]:
    """Return ``(kind, value)`` pairs in command-line order.

    ``kind`` is ``noul``, ``choice``, ``score``, or ``questions``.
    """
    items: list[tuple[str, str]] = []
    index = 0
    while index < len(args):
        token = args[index]
        matched = False
        for flag in QUESTION_FLAGS:
            kind = flag.removeprefix("--")
            if token == flag:
                if index + 1 >= len(args):
                    raise QuestionSpecError(f"{flag} requires a value")
                items.append((kind, args[index + 1]))
                index += 2
                matched = True
                break
            prefix = f"{flag}="
            if token.startswith(prefix):
                items.append((kind, token[len(prefix) :]))
                index += 1
                matched = True
                break
        if not matched:
            index += 1
    return items


def assemble(items: Sequence[tuple[str, str]]) -> dict[str, Question]:
    """Build a name-ordered question map. Duplicate names are an error."""
    questions: dict[str, Question] = {}
    for kind, raw in items:
        for name, question in _parse_item(kind, raw):
            if name in questions:
                raise QuestionSpecError(f"duplicate question name: {name}")
            questions[name] = question
    if not questions:
        raise QuestionSpecError("at least one question is required")
    return questions


def _parse_item(kind: str, raw: str) -> list[tuple[str, Question]]:
    if kind == "noul":
        return [parse_noul(raw)]
    if kind == "choice":
        return [parse_choice(raw)]
    if kind == "score":
        return [parse_score(raw)]
    if kind == "questions":
        return parse_questions_json(raw)
    raise QuestionSpecError(f"unknown question flag: {kind}")


def parse_noul(spec: str) -> tuple[str, Noul]:
    parts = _split_spec(spec, "noul")
    name = _require_name(parts[0], "noul")
    instructions = parts[1]
    criteria: dict[str, str] = {}
    for part in parts[2:]:
        if "=" not in part:
            raise QuestionSpecError(
                f"noul criterion for {name} must be true=TEXT or false=TEXT"
            )
        key, value = part.split("=", 1)
        key = key.strip()
        if key not in {"true", "false"}:
            raise QuestionSpecError(
                f"noul criterion for {name} must be true= or false=, not {key!r}"
            )
        if key in criteria:
            raise QuestionSpecError(f"duplicate noul criterion {key} for {name}")
        criteria[key] = value.strip()
    return name, _model(name, Noul, instructions=instructions, criteria=criteria or None)


def parse_choice(spec: str) -> tuple[str, Choice]:
    parts = _split_spec(spec, "choice")
    name = _require_name(parts[0], "choice")
    instructions = parts[1]
    if len(parts) < 3:
        raise QuestionSpecError(f"choice question {name} needs at least one label")
    criteria: dict[str, str | None] = {}
    for part in parts[2:]:
        label, description = _split_label(part, name)
        if label in criteria:
            raise QuestionSpecError(f"duplicate choice label {label} for {name}")
        criteria[label] = description
    _check_choice_size(name, len(criteria))
    return name, _model(name, Choice, instructions=instructions, criteria=criteria)


def parse_score(spec: str) -> tuple[str, Score]:
    parts = _split_spec(spec, "score")
    name = _require_name(parts[0], "score")
    instructions = parts[1]
    levels = parts[2:]
    _check_score_size(name, len(levels))
    for level in levels:
        if level == "":
            raise QuestionSpecError(f"score question {name} has an empty level")
    return name, _model(name, Score, instructions=instructions, criteria=levels)


def parse_questions_json(raw: str) -> list[tuple[str, Question]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QuestionSpecError(f"questions JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise QuestionSpecError("questions JSON must be an object")
    parsed: list[tuple[str, Question]] = []
    for name, body in payload.items():
        question_name = _require_name(str(name), "questions")
        parsed.append((question_name, _question_from_json(question_name, body)))
    return parsed


def _question_from_json(name: str, body: object) -> Question:
    if not isinstance(body, dict):
        raise QuestionSpecError(f"question {name} must be a JSON object")
    unknown = set(body) - {"type", "instructions", "criteria"}
    if unknown:
        fields = ", ".join(sorted(unknown))
        raise QuestionSpecError(f"question {name} has unknown fields: {fields}")
    kind = body.get("type")
    if kind not in {"noul", "choice", "score"}:
        raise QuestionSpecError(f"question {name} type must be noul, choice, or score")
    instructions = body.get("instructions")
    if instructions is not None:
        _require_content(instructions, f"question {name} instructions")
    criteria = body.get("criteria")
    if kind == "noul":
        return _model(
            name,
            Noul,
            instructions=instructions,
            criteria=_noul_criteria(name, criteria),
        )
    if kind == "choice":
        return _model(
            name,
            Choice,
            instructions=instructions,
            criteria=_choice_criteria(name, criteria),
        )
    return _model(
        name,
        Score,
        instructions=instructions,
        criteria=_score_criteria(name, criteria),
    )


def _noul_criteria(name: str, criteria: object) -> dict[str, Any] | None:
    if criteria is None:
        return None
    if not isinstance(criteria, dict):
        raise QuestionSpecError(f"noul question {name} criteria must be an object")
    unknown = set(criteria) - {"true", "false"}
    if unknown:
        fields = ", ".join(sorted(str(key) for key in unknown))
        raise QuestionSpecError(
            f"noul question {name} criteria may only contain true and false, not {fields}"
        )
    parsed: dict[str, Any] = {}
    for key, value in criteria.items():
        if value is not None:
            _require_content(value, f"noul question {name} criteria {key}")
        parsed[str(key)] = value
    return parsed or None


def _choice_criteria(name: str, criteria: object) -> dict[str, Any]:
    if not isinstance(criteria, dict) or not criteria:
        raise QuestionSpecError(f"choice question {name} needs a criteria object with at least one label")
    _check_choice_size(name, len(criteria))
    parsed: dict[str, Any] = {}
    for label, description in criteria.items():
        label_name = str(label).strip()
        if not label_name:
            raise QuestionSpecError(f"choice question {name} has an empty label")
        if label_name in parsed:
            raise QuestionSpecError(f"duplicate choice label {label_name} for {name}")
        if description is not None:
            _require_content(description, f"choice question {name} label {label_name}")
        parsed[label_name] = description
    return parsed


def _score_criteria(name: str, criteria: object) -> list[Any]:
    if not isinstance(criteria, list):
        raise QuestionSpecError(f"score question {name} criteria must be an array")
    _check_score_size(name, len(criteria))
    for index, level in enumerate(criteria):
        _require_content(level, f"score question {name} level {index}")
    return list(criteria)


def _split_spec(spec: str, kind: str) -> list[str]:
    parts = [part.strip() for part in spec.split("::")]
    if len(parts) < 2:
        raise QuestionSpecError(f"{kind} spec must be NAME::INSTRUCTIONS")
    return parts


def _require_name(name: str, kind: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise QuestionSpecError(f"{kind} question name cannot be empty")
    return cleaned


def _split_label(part: str, name: str) -> tuple[str, str | None]:
    if "=" not in part:
        label = part.strip()
        if not label:
            raise QuestionSpecError(f"choice question {name} has an empty label")
        return label, None
    label, description = part.split("=", 1)
    label = label.strip()
    if not label:
        raise QuestionSpecError(f"choice question {name} has an empty label")
    return label, description.strip()


def _check_choice_size(name: str, count: int) -> None:
    if count > _MAX_CHOICE_LABELS:
        raise QuestionSpecError(
            f"choice question {name} has {count} labels; the maximum is {_MAX_CHOICE_LABELS}"
        )


def _check_score_size(name: str, count: int) -> None:
    if count < _MIN_SCORE_LEVELS or count > _MAX_SCORE_LEVELS:
        raise QuestionSpecError(
            f"score question {name} needs between {_MIN_SCORE_LEVELS} and {_MAX_SCORE_LEVELS} levels"
        )


def _require_content(value: object, what: str) -> None:
    if isinstance(value, (str, dict, list)):
        return
    raise QuestionSpecError(f"{what} must be a string, object, or array")


def _model(name: str, cls: type[Question], **kwargs: Any) -> Question:
    try:
        return cls(**kwargs)
    except ValidationError as exc:
        raise QuestionSpecError(f"question {name} is invalid: {exc}") from exc
