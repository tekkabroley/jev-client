"""Load evaluation state from an argument, a file, or stdin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO


class StateError(Exception):
    """State was missing, conflicting, or unreadable."""


def load_state(
    positional: str | None,
    state_file: str | None,
    stdin: TextIO,
) -> Any:
    """Resolve state text and coerce JSON objects and arrays.

    A positional argument wins over stdin. Passing both a positional argument
    and ``--state-file`` is an error. Stdin is read only when it is not a terminal.
    """
    if positional is not None and state_file is not None:
        raise StateError("pass state as an argument or --state-file, not both")
    if positional is not None:
        return coerce_state(positional)
    if state_file is not None:
        if state_file == "-":
            return coerce_state(stdin.read())
        return coerce_state(_read_file(state_file))
    if stdin.isatty():
        raise StateError("missing state; pass it as an argument, --state-file, or stdin")
    return coerce_state(stdin.read())


def coerce_state(text: str) -> Any:
    """Return a dict or list when the text is a JSON object or array.

    Every other value, including invalid JSON, is returned as the original string.
    """
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return text
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    if isinstance(value, (dict, list)):
        return value
    return text


def _read_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StateError(f"cannot read state file {path}: {exc}") from exc
