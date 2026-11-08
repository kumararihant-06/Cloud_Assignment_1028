"""Strict output extraction and validation against the assignment schema."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "data" / "schema.json").read_text(encoding="utf-8"))
EXPECTED_KEYS = set(SCHEMA["keys"])
VALID_INTENTS = set(SCHEMA["intents"])


class InvalidModelOutput(ValueError):
    pass


def first_json_object(raw: str) -> str:
    start = raw.find("{")
    if start < 0:
        raise InvalidModelOutput("No JSON object found")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(raw)):
        character = raw[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return raw[start : index + 1]
    raise InvalidModelOutput("Unterminated JSON object")


def validated_output(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        try:
            value = json.loads(first_json_object(raw))
        except (json.JSONDecodeError, InvalidModelOutput) as error:
            raise InvalidModelOutput("Output is not valid JSON") from error
    if not isinstance(value, dict) or set(value) != EXPECTED_KEYS:
        raise InvalidModelOutput("Output keys do not match the schema")
    if not isinstance(value["intent"], str) or value["intent"] not in VALID_INTENTS:
        raise InvalidModelOutput("Invalid intent")
    for slot in ("date", "time", "place"):
        if value[slot] is not None and not isinstance(value[slot], str):
            raise InvalidModelOutput(f"Invalid {slot} slot")
    return {key: value[key] for key in SCHEMA["keys"]}

