"""Command-line interface for one-shot Jev evaluations."""

from __future__ import annotations

import sys
from typing import Annotated, Any, NoReturn

import typer
from typesafe_sdk import (
    RetryPolicy,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeClient,
    TypeSafeError,
)

from jev_client.questions import QuestionSpecError, assemble, ordered_question_args
from jev_client.render import render_eval, render_models
from jev_client.state import StateError, load_state

app = typer.Typer(
    name="jev",
    help="Ask Jev typed questions about one piece of state.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

ApiKeyOpt = Annotated[
    str | None,
    typer.Option("--api-key", help="API key. Defaults to the TYPESAFE_API_KEY environment variable."),
]
BaseUrlOpt = Annotated[
    str | None,
    typer.Option(
        "--base-url",
        help="API root. Defaults to TYPESAFE_BASE_URL or https://api.typesafe.ai.",
    ),
]
TimeoutOpt = Annotated[
    float | None,
    typer.Option("--timeout", help="HTTP timeout in seconds. The SDK default is 10."),
]
NoRetryOpt = Annotated[
    bool,
    typer.Option("--no-retry", help="Disable the SDK's retries for 429 and 529 responses."),
]
JsonOpt = Annotated[
    bool,
    typer.Option("--json", help="Print the API response as JSON."),
]


class _RememberArgs(typer.core.TyperCommand):
    """Keep the raw command arguments so question flags stay in the order given."""

    def parse_args(self, ctx: typer.Context, args: list[str]) -> list[str]:
        ctx.meta["argv"] = list(args)
        return super().parse_args(ctx, args)


@app.command("eval", cls=_RememberArgs)
def eval_command(
    ctx: typer.Context,
    state: Annotated[
        str | None,
        typer.Argument(help="Text or JSON to evaluate. Omit to read --state-file or stdin."),
    ] = None,
    state_file: Annotated[
        str | None,
        typer.Option("--state-file", help="Read state from PATH. Use - to read stdin."),
    ] = None,
    noul: Annotated[
        list[str] | None,
        typer.Option(
            "--noul",
            help="Yes/no question: NAME::INSTRUCTIONS[::true=YES][::false=NO]. Repeatable.",
        ),
    ] = None,
    choice: Annotated[
        list[str] | None,
        typer.Option(
            "--choice",
            help=(
                "Choice question: NAME::INSTRUCTIONS::label=description[::bare]. "
                "A label without '=' sends a null description. Repeatable."
            ),
        ),
    ] = None,
    score: Annotated[
        list[str] | None,
        typer.Option(
            "--score",
            help="Score question: NAME::INSTRUCTIONS::level::level. Between 2 and 10 levels. Repeatable.",
        ),
    ] = None,
    questions: Annotated[
        list[str] | None,
        typer.Option(
            "--questions",
            help="JSON object of questions, for structured instructions. Merges with the other flags.",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Model name. Defaults to TYPESAFE_DEFAULT_MODEL or jev-latest."),
    ] = None,
    api_key: ApiKeyOpt = None,
    base_url: BaseUrlOpt = None,
    timeout: TimeoutOpt = None,
    no_retry: NoRetryOpt = False,
    json_output: JsonOpt = False,
) -> None:
    """Evaluate one state with one or more typed questions."""
    del noul, choice, score, questions
    try:
        parsed = assemble(ordered_question_args(ctx.meta.get("argv", [])))
        loaded = load_state(state, state_file, sys.stdin)
    except (QuestionSpecError, StateError) as exc:
        _fail(str(exc), 2)

    try:
        with _client(api_key, base_url, timeout, no_retry, model) as client:
            response = client.system_one(loaded, parsed, **_model_kwargs(model))
    except (TypeSafeAPIError, TypeSafeAPIConnectionError, TypeSafeError) as exc:
        _fail(_format_client_error(exc), 1)

    typer.echo(render_eval(response, parsed, as_json=json_output), nl=False)


@app.command("models")
def models_command(
    api_key: ApiKeyOpt = None,
    base_url: BaseUrlOpt = None,
    timeout: TimeoutOpt = None,
    no_retry: NoRetryOpt = False,
    json_output: JsonOpt = False,
) -> None:
    """List the models available to this account."""
    try:
        with _client(api_key, base_url, timeout, no_retry, model=None) as client:
            response = client.models.list()
    except (TypeSafeAPIError, TypeSafeAPIConnectionError, TypeSafeError) as exc:
        _fail(_format_client_error(exc), 1)
    typer.echo(render_models(response, as_json=json_output), nl=False)


def _client(
    api_key: str | None,
    base_url: str | None,
    timeout: float | None,
    no_retry: bool,
    model: str | None,
) -> TypeSafeClient:
    kwargs: dict[str, Any] = {}
    if api_key is not None:
        kwargs["api_key"] = api_key
    if base_url is not None:
        kwargs["base_url"] = base_url
    if timeout is not None:
        kwargs["timeout"] = timeout
    if model is not None:
        kwargs["model"] = model
    if no_retry:
        kwargs["retry"] = RetryPolicy(max_retries=0)
    return TypeSafeClient(**kwargs)


def _model_kwargs(model: str | None) -> dict[str, str]:
    if model is None:
        return {}
    return {"model": model}


def _format_client_error(exc: Exception) -> str:
    text = str(exc)
    status = getattr(exc, "status", None)
    if status is not None and str(status) not in text:
        text = f"status: {status}\n{text}"
    request_id = getattr(exc, "request_id", None)
    if isinstance(request_id, str) and request_id and request_id not in text:
        text = f"{text}\nrequest_id: {request_id}"
    return text


def _fail(message: str, code: int) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code)
