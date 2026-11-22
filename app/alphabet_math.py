"""A bounded written alphabet representation, independent of Alien's native time.

The scalar mapping is an owner-selected representation. It establishes no
semantic evidence. Millisecond fields retain reference arithmetic only; this
module neither schedules work nor performs any input/output.
"""
import math


PROFILE_ID = "az-log-220-880-v1"
MAX_TEXT = 512
_VALUES = tuple(220 * 2 ** (2 * index / 25) for index in range(26))
_TOKENS = {f"[{index}]": chr(65 + index) for index in range(26)}
_TOKENS["/"] = " "


def _finite_number(value):
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def index_to_value(index):
    """Return the unquantized scalar 220 * 2^(2*index/25)."""
    if type(index) is not int or not 0 <= index <= 25:
        raise ValueError("Letter index must be an integer from 0 to 25.")
    return _VALUES[index]


def value_to_index(value, tolerance_cents=25):
    """Return the nearest index within a finite, non-overlapping tolerance.

    Invalid/outside scalar values return None. Invalid tolerances raise
    ValueError; adjacent indices are 96 cents apart, so tolerance must be
    strictly below 48. Zero tolerance accepts an exact computed scalar only.
    """
    tolerance = _finite_number(tolerance_cents)
    if tolerance is None or not 0 <= tolerance < 48:
        raise ValueError("Tolerance must be finite and at least 0 but below 48 cents.")
    number = _finite_number(value)
    if number is None or number <= 0:
        return None
    for index, scalar in enumerate(_VALUES):
        if number == scalar:
            return index
    if tolerance == 0:
        return None
    # Subtract logarithms rather than dividing first: tiny positive inputs
    # must be rejected without an intermediate underflow to zero.
    nearest = round((math.log2(number) - math.log2(220)) * 25 / 2)
    if not 0 <= nearest <= 25:
        return None
    distance = abs(1200 * math.log2(number / _VALUES[nearest]))
    return nearest if distance <= tolerance else None


def _validate_source(source_text):
    if type(source_text) is not str:
        raise ValueError("Source text must be a string.")
    if len(source_text) > MAX_TEXT:
        raise ValueError(f"Source text exceeds the {MAX_TEXT}-character limit.")
    for position, char in enumerate(source_text, 1):
        if not ("A" <= char <= "Z" or "a" <= char <= "z" or char == " "):
            raise ValueError(
                "Use ASCII A-Z/a-z and literal spaces only "
                f"(unsupported character at position {position})."
            )


def encode(source_text):
    """Encode validated ASCII text without dropping case, spaces or repeats."""
    _validate_source(source_text)
    events = []
    tokens = []
    offset = 0
    for char in source_text:
        if char == " ":
            events.append({
                "type": "space", "char": char, "start_ms": offset,
                "duration_ms": 300,
            })
            tokens.append("/")
            offset += 300
            continue
        index = ord(char.upper()) - 65
        events.append({
            "type": "letter", "char": char, "index": index,
            "value": _VALUES[index], "exponent": [2 * index, 25],
            "start_ms": offset, "duration_ms": 120, "gap_ms": 30,
        })
        tokens.append(f"[{index}]")
        offset += 150
    return {
        "profile": PROFILE_ID,
        "source_text": source_text,
        "normalized_text": source_text.upper(),
        "notation": " ".join(tokens),
        "duration_ms": offset,
        "events": events,
    }


def _same_typed(actual, expected):
    """Compare against a canonical bounded shape, keeping bool distinct from int."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(
            _same_typed(actual[key], value) for key, value in expected.items()
        )
    if type(expected) is list:
        return len(actual) == len(expected) and all(
            _same_typed(value, wanted) for value, wanted in zip(actual, expected)
        )
    return actual == expected


def decode_events(events):
    """Recover source case only from a strictly canonical, bounded event list."""
    if type(events) is not list or len(events) > MAX_TEXT:
        raise ValueError(f"Events must be a list of at most {MAX_TEXT} items.")
    chars = []
    for event in events:
        if type(event) is not dict or type(event.get("char")) is not str:
            raise ValueError("Each event must contain one source character.")
        char = event["char"]
        if len(char) != 1:
            raise ValueError("Each event must contain one source character.")
        chars.append(char)
    source_text = "".join(chars)
    expected = encode(source_text)["events"]
    if not _same_typed(events, expected):
        raise ValueError("Events do not match the canonical alphabet representation.")
    return source_text


def decode_notation(notation):
    """Decode canonical [0]..[25] and / tokens to uppercase ASCII text."""
    if type(notation) is not str:
        raise ValueError("Written notation must be a string.")
    if len(notation) > MAX_TEXT * 5 - 1:
        raise ValueError(f"Written notation exceeds the {MAX_TEXT}-character output limit.")
    if notation == "":
        return ""
    tokens = notation.split(" ")
    if len(tokens) > MAX_TEXT:
        raise ValueError(f"Written notation exceeds the {MAX_TEXT}-character output limit.")
    if any(token not in _TOKENS for token in tokens):
        raise ValueError("Use [0] through [25] and /, separated by one literal space.")
    return "".join(_TOKENS[token] for token in tokens)


def format_plan(plan):
    """Render a validated plan as selectable written mathematics."""
    if type(plan) is not dict:
        raise ValueError("Alphabet plan must be a canonical encoded plan.")
    expected = encode(plan.get("source_text"))
    if not _same_typed(plan, expected):
        raise ValueError("Alphabet plan does not match its source text.")
    lines = [
        f"Alphabet maths: {PROFILE_ID}",
        f"Source text: {plan['source_text']!r}",
        f"Normalized text: {plan['normalized_text']!r}",
        f"Written sequence: {plan['notation'] or '(empty)'}",
        "Scalar(i) = 220 * 2^(2*i/25); ratio(i) = 2^(2*i/25).",
        "Exact expressions; decimal approximations are marked ≈.",
        "This chosen representation is not semantic evidence.",
        "",
        "Ordered expressions:",
    ]
    for position, event in enumerate(plan["events"], 1):
        if event["type"] == "space":
            lines.append(f"{position}. / = literal space")
            continue
        numerator, denominator = event["exponent"]
        exponent = f"{numerator}/{denominator}"
        lines.append(
            f"{position}. {event['char']!r}: index {event['index']}; "
            f"ratio = 2^({exponent}); "
            f"220 * 2^({exponent}) ≈ {event['value']!r}"
        )
    if not plan["events"]:
        lines.append("(empty)")
    lines.extend([
        "",
        "Reference timing arithmetic only; not native ticks or an execution schedule.",
        "Letter 120 ms + gap 30 ms; literal space 300 ms.",
        f"Reference sequence duration: {plan['duration_ms']} ms.",
    ])
    return "\n".join(lines)
