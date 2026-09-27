# jev-client

One-shot command-line client for the [TypeSafe Jev API](https://docs.typesafe.ai/api). Jev answers typed questions about a piece of state. It does not generate text. You send a state and a map of questions. You get one calibrated answer per question, plus token usage.

This tool wraps the official [`typesafe-sdk`](https://docs.typesafe.ai/sdk/python) synchronous client. One `jev eval` invocation is one `POST /v1/systemone` call, so every question on the command shares the same state. `jev models` calls `GET /v1/models`.

The official Rust binary `jevon` also installs a command named `jev`. Keep only one of them on `PATH`.

## Requirements

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/)
- A TypeSafe API key

## Install

```sh
git clone git@github.com:tekkabroley/jev-client.git
cd jev-client
uv sync
```

`uv sync` creates a virtualenv and installs the `jev` command. Run it with `uv run jev`, or activate `.venv` and call `jev` directly. `python -m jev_client` works the same way.

## Configuration

The SDK reads these environment variables. A flag on the command overrides the variable for that invocation.

| Variable | Purpose | Default |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | Bearer token. Required. | none |
| `TYPESAFE_BASE_URL` | API root | `https://api.typesafe.ai` |
| `TYPESAFE_DEFAULT_MODEL` | Model used when `--model` is omitted | `jev-latest` |
| `TYPESAFE_LOG_LEVEL` | SDK log level: `debug`, `info`, `warning`, `error`, or `off` | unset |

```sh
export TYPESAFE_API_KEY=...
```

Create a key in the TypeSafe console. The SDK strips leading and trailing whitespace. It rejects an empty key, internal whitespace, and non-ASCII characters before sending a request.

## Evaluate

```sh
uv run jev eval "Help! My payouts have been failing for 3 days." \
  --noul 'is_urgent::Does this convey urgency?::true=Explicitly time-sensitive::false=No urgency' \
  --choice 'department::Which team should handle this?::billing=Payments, invoicing, refunds::technical=Bugs, outages::sales=Pricing, upgrades' \
  --score 'frustration::How frustrated is the customer?::Calm::Frustrated::Very angry'
```

That prints the resolved model, then each answer in the order the flags were given:

```text
model: jev-1.13.0
is_urgent  noul  0.95
department  choice  billing  confidence  0.81
  billing  0.88
  technical  0.12
  sales  0
frustration  score  1.05  confidence  0.92
  0  Calm  0
  1  Frustrated  0.95
  2  Very angry  0.05
usage: 296 in / 20 out
request_id: req_123
```

`request_id` is the `x-typesafe-request-id` response header, and it is omitted when the response has none. Add `--json` to print the response body (`model`, `answers`, and `usage`) as JSON on stdout. Errors always go to stderr.

### State

State is the content the questions are about. Pass it in one of these ways. The first match wins:

1. A positional argument.
2. `--state-file PATH`. Use `-` to read stdin.
3. Stdin, when it is not a terminal.

Passing both a positional argument and `--state-file` is an error. Omitting state at a terminal is an error.

```sh
uv run jev eval --state-file ticket.txt --noul 'billing::Is this about billing?'
cat ticket.json | uv run jev eval --noul 'billing::Is this about billing?'
```

If the text, after stripping whitespace, parses as a JSON object or array, that value is sent as structured state. Anything else, including invalid JSON, a JSON string, or a JSON number, is sent as a string.

### Questions

Question flags are repeatable. At least one is required. `::` separates fields, so a single colon or a comma can appear in instructions and rubrics. A repeated question name is an error. Names and fields are stripped of surrounding whitespace.

**Noul** is a yes/no question. The answer is `noul`, a probability from 0 (no) to 1 (yes).

```text
--noul 'NAME::INSTRUCTIONS'
--noul 'NAME::INSTRUCTIONS::true=YES::false=NO'
```

`true=` and `false=` are optional descriptions of the two outcomes. Either one may be omitted.

**Choice** picks one label. The answer is the winning label, a probability for every label, and a confidence from 0 to 1. Provide at least one label and at most 255.

```text
--choice 'NAME::INSTRUCTIONS::label=description::bare'
```

A label with no `=` sends a null description. `label=` sends an empty string. Split on the first `=` only, so a description may contain `=`.

**Score** rates the state on an ordered rubric. Provide 2 to 10 level descriptions. The answer is a probability-weighted score that can fall between levels, a confidence, the legend, and a probability per level.

```text
--score 'NAME::INSTRUCTIONS::Calm::Frustrated::Very angry'
```

**`--questions`** is a JSON object for instructions or criteria that need nested structure. It merges with the other flags, in command-line order. It is a flag value, not a path.

```sh
uv run jev eval --state-file resume.txt --questions '{
  "same_person": {
    "type": "noul",
    "instructions": {
      "potential_duplicate": {"name": "John Smith", "location": "Oakland, California"},
      "question": "Is the resume for the same person as `potential_duplicate`?"
    }
  }
}'
```

Each object needs `"type"` of `noul`, `choice`, or `score`. `instructions` may be a string, object, or array. Choice `criteria` is an object of label to description (`null` leaves a label undescribed). Score `criteria` is an array of 2 to 10 level descriptions.

### Flags

`eval` and `models` both accept:

| Flag | Meaning |
| --- | --- |
| `--api-key` | Overrides `TYPESAFE_API_KEY` for this command |
| `--base-url` | Overrides `TYPESAFE_BASE_URL` |
| `--timeout SECONDS` | HTTP timeout. The SDK default is 10 seconds |
| `--no-retry` | Disables retries. By default the SDK retries `429` and `529` with backoff |
| `--json` | Print the API body as JSON |

`eval` also accepts `--model`. Omit it to use `TYPESAFE_DEFAULT_MODEL`, or `jev-latest` when that variable is unset. The response `model` field is the version that answered, which can differ from an alias such as `jev-latest`.

## Models

```sh
uv run jev models
uv run jev models --json
```

Text output is one model per line: name, release date (`YYYY-MM-DD`), and description. `--json` prints the list response.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | The request succeeded |
| 2 | The command line or local input was invalid: missing state, no questions, a bad spec, a duplicate name, or an unreadable file |
| 1 | The SDK rejected the key, the connection failed, or the API returned an error such as `401` or `422` after retries |

API errors include the HTTP status and `request_id` when the SDK provides them.

## Development

```sh
uv sync
uv run pytest
```

Tests use a fake client. They do not call the network and do not need an API key.
