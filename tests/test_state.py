import io

import pytest

from jev_client.state import StateError, coerce_state, load_state


class _Stdin(io.StringIO):
    def __init__(self, text: str, *, tty: bool) -> None:
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_plain_text_stays_a_string() -> None:
    assert coerce_state("Help! My payouts have been failing.") == "Help! My payouts have been failing."


def test_json_object_and_array_are_parsed() -> None:
    assert coerce_state('  {"document": "I was charged twice."} ') == {
        "document": "I was charged twice."
    }
    assert coerce_state('["line one", "line two"]') == ["line one", "line two"]


def test_invalid_or_scalar_json_stays_a_string() -> None:
    assert coerce_state("{not json") == "{not json"
    assert coerce_state('"hello"') == '"hello"'
    assert coerce_state("42") == "42"
    assert coerce_state("true") == "true"


def test_positional_state_wins_over_stdin() -> None:
    stdin = _Stdin('{"from": "stdin"}', tty=False)
    assert load_state("from the argument", None, stdin) == "from the argument"
    assert stdin.read() == '{"from": "stdin"}'


def test_state_file_and_stdin_dash(tmp_path) -> None:
    path = tmp_path / "ticket.json"
    path.write_text('["a", "b"]\n', encoding="utf-8")
    assert load_state(None, str(path), _Stdin("", tty=True)) == ["a", "b"]
    assert load_state(None, "-", _Stdin("piped text", tty=False)) == "piped text"


def test_missing_state_on_a_tty() -> None:
    with pytest.raises(StateError, match="missing state"):
        load_state(None, None, _Stdin("", tty=True))


def test_empty_stdin_is_an_empty_string() -> None:
    assert load_state(None, None, _Stdin("", tty=False)) == ""


def test_positional_and_file_conflict() -> None:
    with pytest.raises(StateError, match="not both"):
        load_state("hello", "ticket.txt", _Stdin("", tty=True))


def test_missing_file() -> None:
    with pytest.raises(StateError, match="cannot read state file"):
        load_state(None, "does-not-exist.txt", _Stdin("", tty=True))
