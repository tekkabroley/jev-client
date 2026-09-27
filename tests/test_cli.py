import json

import httpx2
import pytest
from typer.testing import CliRunner
from typesafe_sdk import (
    NoulAnswer,
    SystemOneResponse,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeError,
    Usage,
)

from jev_client.cli import app
from jev_client import cli


runner = CliRunner()


class FakeModels:
    def __init__(self, response) -> None:
        self._response = response

    def list(self):
        return self._response


class FakeClient:
    response = None
    models_response = None
    error: Exception | None = None
    init_error: Exception | None = None

    def __init__(self, **kwargs) -> None:
        if FakeClient.init_error is not None:
            raise FakeClient.init_error
        self.kwargs = kwargs
        self.calls = []
        self.models = FakeModels(FakeClient.models_response)
        FakeClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def system_one(self, state, questions, **kwargs):
        self.calls.append((state, questions, kwargs))
        if FakeClient.error is not None:
            raise FakeClient.error
        return FakeClient.response


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    FakeClient.instances = []
    FakeClient.response = SystemOneResponse(
        model="jev-1.13.0",
        usage=Usage(input_tokens=10, output_tokens=2),
        answers={"billing": NoulAnswer(noul=0.25)},
    )
    FakeClient.models_response = None
    FakeClient.error = None
    FakeClient.init_error = None
    monkeypatch.setattr(cli, "TypeSafeClient", FakeClient)


def test_eval_sends_one_request_and_prints_text() -> None:
    result = runner.invoke(
        app,
        [
            "eval",
            "Help! My payouts have been failing for 3 days.",
            "--noul",
            "is_urgent::Does this convey urgency?",
            "--choice",
            "department::Which team?::billing=Payments::technical",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "model: jev-1.13.0" in result.stdout
    assert result.stdout.index("is_urgent") < result.stdout.index("department")
    client = FakeClient.instances[-1]
    state, questions, kwargs = client.calls[-1]
    assert state == "Help! My payouts have been failing for 3 days."
    assert list(questions) == ["is_urgent", "department"]
    assert questions["department"].criteria["technical"] is None
    assert kwargs == {}


def test_repeated_question_flags_keep_cli_order() -> None:
    result = runner.invoke(
        app,
        [
            "eval",
            "hello",
            "--score",
            "tone::How does this sound?::Calm::Angry",
            "--noul",
            "billing::Is this about billing?",
            "--noul",
            "urgent::Does this convey urgency?",
        ],
    )
    assert result.exit_code == 0, result.output
    questions = FakeClient.instances[-1].calls[-1][1]
    assert list(questions) == ["tone", "billing", "urgent"]
    assert result.stdout.index("tone") < result.stdout.index("billing") < result.stdout.index("urgent")


def test_eval_json_and_structured_state() -> None:
    result = runner.invoke(
        app,
        ["eval", "--json", '{"document": "I was charged twice."}', "--noul", "billing::Is this about billing?"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["model"] == "jev-1.13.0"
    assert payload["answers"]["billing"]["noul"] == 0.25
    state, _, _ = FakeClient.instances[-1].calls[-1]
    assert state == {"document": "I was charged twice."}


def test_eval_reads_stdin_and_state_file(tmp_path) -> None:
    piped = runner.invoke(app, ["eval", "--noul", "billing::Is this about billing?"], input="piped")
    assert piped.exit_code == 0, piped.output
    assert FakeClient.instances[-1].calls[-1][0] == "piped"

    path = tmp_path / "ticket.json"
    path.write_text('["one", "two"]\n', encoding="utf-8")
    from_file = runner.invoke(
        app,
        ["eval", "--state-file", str(path), "--noul", "billing::Is this about billing?"],
    )
    assert from_file.exit_code == 0, from_file.output
    assert FakeClient.instances[-1].calls[-1][0] == ["one", "two"]


def test_local_errors_exit_2() -> None:
    missing = runner.invoke(app, ["eval", "hello"])
    assert missing.exit_code == 2
    assert "at least one question" in missing.stderr

    both = runner.invoke(app, ["eval", "hello", "--state-file", "ticket.txt", "--noul", "q::Is it?"])
    assert both.exit_code == 2
    assert "not both" in both.stderr

    bad = runner.invoke(app, ["eval", "hello", "--score", "tone::How?::Only one"])
    assert bad.exit_code == 2
    assert "between 2 and 10" in bad.stderr
    assert FakeClient.instances == []


def test_model_and_no_retry_are_passed_through() -> None:
    result = runner.invoke(
        app,
        ["eval", "hello", "--noul", "q::Is it?", "--model", "jev-1.13.0", "--no-retry", "--timeout", "3"],
    )
    assert result.exit_code == 0, result.output
    client = FakeClient.instances[-1]
    assert client.kwargs["model"] == "jev-1.13.0"
    assert client.kwargs["timeout"] == 3
    assert client.kwargs["retry"].max_retries == 0
    assert client.calls[-1][2] == {"model": "jev-1.13.0"}


def test_api_error_exits_1() -> None:
    FakeClient.error = TypeSafeAPIError(
        401,
        {"detail": "missing or invalid API key"},
        httpx2.Headers({"x-typesafe-request-id": "req_9"}),
    )
    result = runner.invoke(app, ["eval", "hello", "--noul", "q::Is it?"])
    assert result.exit_code == 1
    assert "401" in result.stderr
    assert "req_9" in result.stderr
    assert result.stdout == ""


def test_connection_and_client_errors_exit_1() -> None:
    FakeClient.error = TypeSafeAPIConnectionError("connection timed out")
    result = runner.invoke(app, ["eval", "hello", "--noul", "q::Is it?"])
    assert result.exit_code == 1
    assert "connection timed out" in result.stderr

    FakeClient.error = None
    FakeClient.init_error = TypeSafeError("API key is missing")
    created = runner.invoke(app, ["models"])
    assert created.exit_code == 1
    assert "API key is missing" in created.stderr


def test_models_list() -> None:
    from typesafe_sdk import ListModelsResponse, ModelMetadata

    FakeClient.models_response = ListModelsResponse(
        models=(
            ModelMetadata(name="jev-latest", release_date="2026-09-15", description="Stable release."),
        )
    )
    text = runner.invoke(app, ["models"])
    assert text.exit_code == 0, text.output
    assert text.stdout == "jev-latest  2026-09-15  Stable release.\n"

    payload = runner.invoke(app, ["models", "--json"])
    assert payload.exit_code == 0, payload.output
    assert json.loads(payload.stdout)["models"][0]["name"] == "jev-latest"
