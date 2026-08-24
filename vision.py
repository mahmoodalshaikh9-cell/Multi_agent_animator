import base64
import json
import re
import requests
import cv2

MODEL = "qwen2.5vl:3b"
OLLAMA_URL = "http://localhost:11434/api/chat"


def is_blank_frame(image_path: str) -> bool:
    """True for frames with almost no contrast.

    The first frames of a render are usually still empty; they carry no
    evidence and their "nothing visible" notes confuse the evaluator.
    """
    image = cv2.imread(image_path)

    if image is None:
        return True

    return float(image.std()) < 2.0


def describe_frame(image_path: str) -> str:
    """Describe a single frame in plain words plus a strict position line.

    The tiny vision model describes one image far more reliably than it
    compares several images at once, so we collect per-frame notes first
    and hand them to the evaluator as evidence.
    """
    with open(image_path, "rb") as f:
        image = base64.b64encode(f.read()).decode("utf-8")

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "This is one frame of an animation. In one or two short "
                        "sentences: which objects and text are visible, and where "
                        "is each one (left side, center, right side)? Look "
                        "carefully, also at small or thin objects."
                    ),
                    "images": [image],
                }
            ],
            "options": {"temperature": 0},
            "stream": False,
        },
        timeout=300,
    )

    response.raise_for_status()

    return response.json()["message"]["content"].strip()


FILLER_WORDS = {
    "there", "is", "was", "are", "a", "an", "the", "this", "that",
    "it", "its", "single", "only", "one", "visible", "seen", "shown",
    "and", "with", "of", "in", "on", "at", "to", "frame", "image",
    "screen", "side", "background", "white", "black", "blue", "red",
    "green", "yellow", "rest", "indicating", "empty", "space", "blank",
    # position words themselves must never become object keys
    "left", "center", "centre", "centred", "centered", "middle", "right",
}

POSITION_PATTERN = r"\b(left|cent(?:er|re)(?:ed)?|middle|right)\b"


def normalize_position(word: str) -> str:
    return {
        "centre": "center",
        "middle": "center",
        "centered": "center",
        "centred": "center",
    }.get(word, word)


def parse_positions(note: str) -> dict[str, str]:
    """Pair every position mention with the nearest object noun.

    Notes read like '... blue circle ... on the right side of the frame',
    so the object key is the closest content word before the position
    word (or the first one after, e.g. 'In the center ... there is a
    blue circle').
    """
    positions: dict[str, str] = {}

    for sentence in re.split(r"[.;\n]", note):
        match = re.search(POSITION_PATTERN, sentence, re.IGNORECASE)

        if not match:
            continue

        tokens = [
            (token.group().lower(), token.start(), token.end())
            for token in re.finditer(r"[a-zA-Z']+", sentence)
        ]

        nouns_before = [
            t for t, start, _ in tokens if t not in FILLER_WORDS and start < match.start()
        ]
        nouns_after = [
            t for t, _, end in tokens if t not in FILLER_WORDS and end > match.end()
        ]

        if nouns_before:
            positions[nouns_before[-1]] = normalize_position(match.group(1).lower())
        elif nouns_after:
            positions[nouns_after[0]] = normalize_position(match.group(1).lower())

    return positions


def observe_frames(image_paths: list[str]) -> tuple[list[str], list[dict]]:
    """Turn the chronological frames into numbered textual observations
    plus per-frame object positions."""
    notes = []
    tables = []

    for index, path in enumerate(image_paths):
        if is_blank_frame(path):
            continue

        note = describe_frame(path)
        notes.append(f"Frame {index}: {note}")
        tables.append(parse_positions(note))

    return notes, tables


def track_main_object(tables: list[dict]) -> tuple[str | None, list[str]]:
    """Follow the object that appears most often across the frames."""
    counts: dict[str, int] = {}

    for table in tables:
        for name in table:
            counts[name] = counts.get(name, 0) + 1

    if not counts:
        return None, []

    name = max(counts, key=counts.get)

    return name, [table.get(name, "unknown") for table in tables]


def parse_evaluation(text: str) -> dict:
    """Parse the evaluator's answer leniently.

    Small models often emit almost-valid JSON (a missing comma between
    list items, or prose around the object), so repair before giving up.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Insert the comma small models forget between adjacent quoted
    # strings split across lines: "a"\n"b" -> "a",\n"b"
    repaired = re.sub(r'"\s*\n\s*"', '",\n"', text)

    return json.loads(repaired)


def evaluate_requirement(
    requirement: dict,
    observations: str,
    measured: str = "",
    previous_result: dict | None = None,
) -> dict:
    """Judge ONE requirement against the frame observations.

    One small question per call is far more reliable with a tiny model
    than one big call judging everything at once.
    """
    user_content = (
        f"REQUIREMENT {requirement['id']}:\n"
        + requirement["description"]
        + "\n\nFRAME-BY-FRAME OBSERVATIONS:\n"
        + observations
        + "\n\n"
    )

    if measured:
        user_content += measured + "\n"

    if previous_result:
        # Mention only what this specific requirement scored last time.
        old = [
            entry
            for entry in previous_result.get("requirements", [])
            if entry.get("id") == requirement["id"]
        ]
        if old:
            user_content += (
                "PREVIOUS ITERATION (same requirement):\n"
                + json.dumps(old[0])
                + "\n\n"
            )

    user_content += "Decide: is this one requirement satisfied?"

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": """
You verify ONE requirement against FRAME-BY-FRAME OBSERVATIONS of an
animation. The observations were written while looking at each frame
individually and are ordered chronologically.

Base your decision ONLY on the observations:
- clearly satisfied -> "pass": true
- clearly violated  -> "pass": false
- uncertain or not verifiable -> "pass": false

Uncertainty counts as failure. Never assume something happened just
because the request suggests it.
If a MEASURED OBJECT POSITIONS block is present, it was extracted
programmatically from the same observations. For any requirement about
movement or position, your decision MUST agree with that measurement.
Quote the relevant observation text in "evidence".
If a PREVIOUS ITERATION note is present, say in the evidence whether
the problem was fixed.

Return ONLY valid JSON:

{"id": "<the requirement id>", "pass": true, "confidence": 0.95, "evidence": "what the observations show"}
""",
                },
                {"role": "user", "content": user_content},
            ],
            "options": {"temperature": 0},
            "stream": False,
        },
        timeout=300,
    )

    response.raise_for_status()

    text = response.json()["message"]["content"].strip()

    try:
        entry = parse_evaluation(text)
    except json.JSONDecodeError:
        # Conservative fallback: no readable verdict means not verified.
        entry = {}

    return {
        "id": requirement["id"],
        "pass": entry.get("pass") is True,
        "confidence": entry.get("confidence", 0.0),
        "evidence": entry.get("evidence", "Evaluator returned unparseable output."),
    }


MOVEMENT_WORDS = (
    "move", "moves", "moving", "movement", "across", "travel",
    "travels", "slide", "slides", "shift", "shifts",
)


def is_movement_requirement(description: str) -> bool:
    return any(word in description.lower() for word in MOVEMENT_WORDS)


def review_animation(
    prompt: str,
    requirements: list[dict],
    image_paths: list[str],
    previous_result: dict | None = None,
) -> dict:
    """Evaluate every requirement independently against the rendered frames.

    previous_result (if given) lets the evaluator judge improvement over
    the previous iteration, requirement by requirement.
    """
    # Per-frame notes ARE the visual evidence: qwen2.5vl:3b describes one
    # image reliably but cannot compare several attached images at once,
    # so all judging happens over these notes.
    frame_notes, position_tables = observe_frames(image_paths)
    observations = "\n".join(frame_notes)

    # A deterministic position summary grounds movement decisions; without
    # it the tiny judge tends to deny visible movement.
    measured = ""
    object_name, positions = track_main_object(position_tables)

    if object_name:
        listed = ", ".join(
            f"Frame {i}: {p}" for i, p in enumerate(positions)
        )
        changed = len({p for p in positions if p != "unknown"}) > 1
        measured = (
            f"MEASURED OBJECT POSITIONS for '{object_name}': {listed}. "
            f"Position changed across frames: {'YES' if changed else 'NO'}."
        )

    results = []

    for requirement in requirements:
        entry = evaluate_requirement(
            requirement, observations, measured, previous_result
        )

        # The tiny judge occasionally denies movement it just measured.
        # When we have real tracked positions, the measurement decides:
        # changed=YES means a movement requirement cannot fail here.
        if (
            measured
            and is_movement_requirement(requirement["description"])
        ):
            moved = "YES" in measured
            if moved and not entry["pass"]:
                entry["pass"] = True
                entry["confidence"] = 1.0
                entry["evidence"] = (
                    f"Measured object positions confirm movement: {measured}"
                )
            elif not moved and entry["pass"]:
                entry["pass"] = False
                entry["confidence"] = 1.0
                entry["evidence"] = (
                    f"Measured object positions show no change: {measured}"
                )

        results.append(entry)

    failed = [entry for entry in results if not entry["pass"]]

    # Concrete repair instructions assembled from the failures themselves,
    # so a failure always produces something actionable for the coder.
    repair_instructions = [
        (
            f"{entry['id']} FAILED: make the animation satisfy this requirement "
            f"clearly. Evaluator evidence: {entry['evidence']}"
        )
        for entry in failed
    ]

    return {
        "requirements": results,
        "repair_instructions": repair_instructions,
    }