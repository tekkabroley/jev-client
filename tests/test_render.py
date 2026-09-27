from typesafe_sdk import (
    Choice,
    ChoiceAnswer,
    ListModelsResponse,
    ModelMetadata,
    Noul,
    NoulAnswer,
    Score,
    ScoreAnswer,
    SystemOneResponse,
    Usage,
)

from jev_client.render import render_eval, render_models


def _response() -> SystemOneResponse:
    return SystemOneResponse(
        model="jev-1.13.0",
        usage=Usage(input_tokens=296, output_tokens=20),
        answers={
            "department": ChoiceAnswer(
                choice="billing",
                confidence=0.81,
                probabilities={"sales": 0.0, "billing": 0.88, "technical": 0.12},
            ),
            "is_urgent": NoulAnswer(noul=0.95),
            "frustration": ScoreAnswer(
                score=1.05,
                confidence=0.92,
                legend={0: "Calm", 1: "Frustrated", 2: "Very angry"},
                probabilities={2: 0.05, 0: 0.0, 1: 0.95},
            ),
        },
    )


def _questions() -> dict:
    return {
        "is_urgent": Noul(
            instructions="Does this convey urgency?",
            criteria={"true": "Explicitly time-sensitive", "false": "No urgency"},
        ),
        "department": Choice(
            instructions="Which team should handle this?",
            criteria={
                "billing": "Payments, invoicing, refunds",
                "technical": "Bugs, outages",
                "sales": "Pricing, upgrades",
            },
        ),
        "frustration": Score(
            instructions="How frustrated is the customer?",
            criteria=["Calm", "Frustrated", "Very angry"],
        ),
    }


def test_human_eval_follows_question_order() -> None:
    text = render_eval(_response(), _questions(), as_json=False)
    assert text == (
        "model: jev-1.13.0\n"
        "is_urgent  noul  0.95\n"
        "department  choice  billing  confidence  0.81\n"
        "  billing  0.88\n"
        "  technical  0.12\n"
        "  sales  0\n"
        "frustration  score  1.05  confidence  0.92\n"
        "  0  Calm  0\n"
        "  1  Frustrated  0.95\n"
        "  2  Very angry  0.05\n"
        "usage: 296 in / 20 out\n"
    )


def test_human_eval_includes_request_id_when_present() -> None:
    response = _response()
    response.__dict__["_request_id"] = "req_123"
    text = render_eval(response, _questions(), as_json=False)
    assert text.endswith("request_id: req_123\n")


def test_json_eval_matches_the_response_body() -> None:
    text = render_eval(_response(), _questions(), as_json=True)
    assert '"model": "jev-1.13.0"' in text
    assert '"noul": 0.95' in text
    assert "request_id" not in text


def test_models_text_and_json() -> None:
    response = ListModelsResponse(
        models=(
            ModelMetadata(
                name="jev-latest",
                release_date="2026-09-15",
                description="The most recent stable release.",
            ),
        )
    )
    assert render_models(response, as_json=False) == (
        "jev-latest  2026-09-15  The most recent stable release.\n"
    )
    assert '"name": "jev-latest"' in render_models(response, as_json=True)
