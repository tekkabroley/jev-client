import json

import pytest
from typesafe_sdk import Choice, Noul, Score

from jev_client.questions import (
    QuestionSpecError,
    assemble,
    ordered_question_args,
    parse_choice,
    parse_noul,
    parse_questions_json,
    parse_score,
)


def test_ordered_question_args_keeps_flag_order() -> None:
    args = [
        "--model",
        "jev-latest",
        "--choice",
        "department::Which team?::billing=Payments",
        "--json",
        "--noul=is_urgent::Does this convey urgency?",
        "--score",
        "frustration::How frustrated?::Calm::Angry",
    ]
    assert ordered_question_args(args) == [
        ("choice", "department::Which team?::billing=Payments"),
        ("noul", "is_urgent::Does this convey urgency?"),
        ("score", "frustration::How frustrated?::Calm::Angry"),
    ]


def test_noul_with_criteria() -> None:
    name, question = parse_noul(
        "is_urgent::Does this convey urgency?::true=Explicitly time-sensitive::false=No urgency"
    )
    assert name == "is_urgent"
    assert isinstance(question, Noul)
    assert question.instructions == "Does this convey urgency?"
    assert question.criteria == {
        "true": "Explicitly time-sensitive",
        "false": "No urgency",
    }


def test_noul_without_criteria() -> None:
    name, question = parse_noul("billing::Is this about billing?")
    assert name == "billing"
    assert question.criteria is None


def test_noul_rejects_unknown_criterion() -> None:
    with pytest.raises(QuestionSpecError, match="true= or false="):
        parse_noul("q::Is it?::maybe=yes")


def test_choice_null_and_empty_descriptions() -> None:
    name, question = parse_choice(
        "department::Which team should handle this?::billing=Payments, invoicing, refunds::technical::sales="
    )
    assert name == "department"
    assert isinstance(question, Choice)
    assert question.criteria == {
        "billing": "Payments, invoicing, refunds",
        "technical": None,
        "sales": "",
    }


def test_choice_requires_a_label() -> None:
    with pytest.raises(QuestionSpecError, match="at least one label"):
        parse_choice("department::Which team?")


def test_choice_rejects_more_than_255_labels() -> None:
    labels = "::".join(f"label{index}" for index in range(256))
    with pytest.raises(QuestionSpecError, match="maximum is 255"):
        parse_choice(f"topic::Pick one::{labels}")


def test_score_levels() -> None:
    name, question = parse_score(
        "frustration::How frustrated is the customer?::Calm::Frustrated::Very angry"
    )
    assert name == "frustration"
    assert isinstance(question, Score)
    assert question.criteria == ["Calm", "Frustrated", "Very angry"]


@pytest.mark.parametrize("count", [1, 11])
def test_score_level_count(count: int) -> None:
    levels = "::".join(f"level{index}" for index in range(count))
    with pytest.raises(QuestionSpecError, match="between 2 and 10"):
        parse_score(f"tone::How?::{levels}")


def test_questions_json_structured_instructions() -> None:
    raw = json.dumps(
        {
            "same_person": {
                "type": "noul",
                "instructions": {
                    "potential_duplicate": {"name": "John Smith"},
                    "question": "Is the resume for the same person as `potential_duplicate`?",
                },
            }
        }
    )
    parsed = parse_questions_json(raw)
    assert parsed[0][0] == "same_person"
    question = parsed[0][1]
    assert isinstance(question, Noul)
    assert question.instructions["potential_duplicate"]["name"] == "John Smith"


def test_questions_json_rejects_unknown_fields() -> None:
    with pytest.raises(QuestionSpecError, match="unknown fields"):
        parse_questions_json('{"q": {"type": "noul", "instructions": "Is it?", "weight": 2}}')


def test_assemble_rejects_duplicate_names() -> None:
    with pytest.raises(QuestionSpecError, match="duplicate question name: billing"):
        assemble(
            [
                ("noul", "billing::Is this about billing?"),
                ("questions", '{"billing": {"type": "noul", "instructions": "Again?"}}'),
            ]
        )


def test_assemble_requires_a_question() -> None:
    with pytest.raises(QuestionSpecError, match="at least one question"):
        assemble([])
