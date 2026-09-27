"""Format TypeSafe responses for a terminal or as JSON."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from typesafe_sdk import Choice, Score, TypeSafeError

from jev_client.questions import Question


def render_eval(
    response: Any,
    questions: Mapping[str, Question],
    *,
    as_json: bool,
) -> str:
    if as_json:
        return json.dumps(response.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    return _render_eval_text(response, questions)


def render_models(response: Any, *, as_json: bool) -> str:
    if as_json:
        return json.dumps(response.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    lines = [
        f"{model.name}  {model.release_date}  {model.description}"
        for model in response.models
    ]
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _render_eval_text(response: Any, questions: Mapping[str, Question]) -> str:
    lines = [f"model: {response.model}"]
    answers = response.answers
    for name, question in questions.items():
        answer = answers.get(name)
        if answer is None:
            lines.append(f"{name}  missing")
            continue
        lines.extend(_render_answer(name, question, answer))
    usage = response.usage
    lines.append(
        f"usage: {_token(usage.input_tokens)} in / {_token(usage.output_tokens)} out"
    )
    request_id = _request_id(response)
    if request_id:
        lines.append(f"request_id: {request_id}")
    return "\n".join(lines) + "\n"


def _render_answer(name: str, question: Question, answer: Any) -> list[str]:
    kind = getattr(answer, "type", None)
    if kind == "noul":
        return [f"{name}  noul  {format_number(answer.noul)}"]
    if kind == "choice":
        return _render_choice(name, question, answer)
    if kind == "score":
        return _render_score(name, question, answer)
    return [f"{name}  {kind}"]


def _render_choice(name: str, question: Question, answer: Any) -> list[str]:
    lines = [
        f"{name}  choice  {answer.choice}  confidence  {format_number(answer.confidence)}"
    ]
    labels = list(question.criteria) if isinstance(question, Choice) else []
    for label in _with_extras(labels, answer.probabilities):
        probability = answer.probabilities.get(label)
        shown = "-" if probability is None else format_number(probability)
        lines.append(f"  {label}  {shown}")
    return lines


def _render_score(name: str, question: Question, answer: Any) -> list[str]:
    lines = [
        f"{name}  score  {format_number(answer.score)}  confidence  {format_number(answer.confidence)}"
    ]
    if isinstance(question, Score):
        indexes = [str(index) for index in range(len(question.criteria))]
    else:
        indexes = []
    for index in _with_extras(indexes, answer.probabilities):
        probability = answer.probabilities.get(index)
        if probability is None and index.isdigit():
            probability = answer.probabilities.get(int(index))
        shown = "-" if probability is None else format_number(probability)
        lines.append(f"  {index}  {_legend_text(answer.legend, index)}  {shown}")
    return lines


def _with_extras(ordered: Sequence[str], probabilities: Mapping[Any, Any]) -> list[str]:
    seen = set(ordered)
    extras = [str(key) for key in probabilities if str(key) not in seen]
    return [*ordered, *extras]


def _legend_text(legend: Mapping[Any, Any], index: str) -> str:
    if index in legend:
        value = legend[index]
    elif index.isdigit() and int(index) in legend:
        value = legend[int(index)]
    else:
        value = ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _token(value: int | None) -> str:
    if value is None:
        return "-"
    return str(value)


def _request_id(response: Any) -> str | None:
    try:
        request_id = response.request_id
    except (TypeSafeError, AttributeError):
        return None
    if isinstance(request_id, str) and request_id:
        return request_id
    return None


def format_number(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text
