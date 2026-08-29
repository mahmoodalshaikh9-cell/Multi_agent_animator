import base64
import json
import re
import requests
import cv2
import toml
from pathlib import Path

import geometry as geom
with open("vision_guidelines.md", "r", encoding="utf-8") as file:
    vision_guidelines = file.read()

secrets_data = toml.load(Path(__file__).parent / "secrets.toml")
key = secrets_data.get("openrouter_cohere_key", "")

MODEL = "google/gemini-2.5-flash"
OLLAMA_URL = "https://openrouter.ai/api/v1/chat/completions"
URL = "https://openrouter.ai/api/v1/chat/completions"
zai = 'google/gemini-2.5-flash'
headers = {
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
}


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
        URL,
        headers=headers,
        json={
            "model": zai,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "This is one frame of an animation. In one or two short "
                                "sentences: which objects and text are visible, and where "
                                "is each one (left side, center, right side)? Look "
                                "carefully, also at small or thin objects."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
            "stream": False,
        },
        timeout=300,
    )

    response.raise_for_status()

    return (response.json()["choices"][0]["message"].get("content") or "").strip()


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
        headers=headers,
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": vision_guidelines ,
                },
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
            "stream": False,
        },
        timeout=300,
    )

    response.raise_for_status()

    content = response.json()["choices"][0]["message"].get("content")
    text = (content or "").strip()

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


CRITIQUE_SYSTEM_PROMPT = """You are an animation visual-quality critic.

You judge RENDERED STILL FRAMES of a Manim animation plus its source code.
The frames are in chronological order.

TASK 1 - REPORT ONLY OBSERVED DEFECTS.
A defect MUST name the offending object(s) and the frame range where it occurs
(example: "frames": "4-7"). If you cannot identify a concrete defect, report
none. An empty list is a valid answer. Never invent "possible" overlaps.

TASK 2 - SCORE each dimension from 1 to 5:
- hierarchy: Is there an obvious main object/concept?
- readability: Can labels/equations/objects be understood without collisions?
- composition: Is the scene balanced rather than randomly scattered?
- temporal_clarity: Does the animation reveal the idea in a sensible order?
- emphasis: Does the animation draw attention to the important change?
- economy: Are there unnecessary objects or movements?

TASK 3 - LIST what already works well and must be preserved (strengths).

TASK 4 - SUGGEST improvements (priority high/medium/low, area, suggestion).
An improvement is optional polish; do NOT list an improvement that is
required to satisfy a stated requirement.

Return ONLY valid JSON:
{
  "observed_defects": [
    {"object": "...", "frames": "4-7", "problem": "..."}
  ],
  "scores": {
    "hierarchy": 4,
    "readability": 5,
    "composition": 3,
    "temporal_clarity": 4,
    "emphasis": 2,
    "economy": 4
  },
  "strengths": ["..."],
  "improvements": [
    {"priority": "high", "area": "conceptual_clarity", "suggestion": "..."}
  ]
}
"""


def _run_critique(
    prompt: str,
    code: str,
    image_paths: list[str],
    max_frames: int = 6,
) -> dict:
    """Ask the vision model for a concrete, frame-anchored critique.

    The critique receives the RAW frames (not only text notes) because the
    model detects overlaps and collisions far more reliably from pixels.
    """
    content = [
        {
            "type": "text",
            "text": (
                "Original request:\n\n"
                f"{prompt}\n\n"
                "Source code:\n\n"
                f"{code}\n\n"
                "Frames below are in chronological order. Evaluate them."
            ),
        }
    ]

    sent = 0
    for i, path in enumerate(image_paths):
        if sent >= max_frames:
            break
        if is_blank_frame(path):
            continue
        with open(path, "rb") as f:
            image = base64.b64encode(f.read()).decode("utf-8")
        content.append({"type": "text", "text": f"Frame {i}:"})
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"},
            }
        )
        sent += 1

    if sent == 0:
        return {
            "observed_defects": [],
            "scores": {},
            "total": None,
            "strengths": [],
            "improvements": [],
        }

    response = requests.post(
        URL,
        headers=headers,
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0,
            "stream": False,
        },
        timeout=300,
    )
    response.raise_for_status()

    content = response.json()["choices"][0]["message"].get("content")
    text = (content or "").strip()
    if not text:
        return {
            "observed_defects": [],
            "scores": {},
            "total": None,
            "strengths": [],
            "improvements": [],
        }

    try:
        entry = parse_evaluation(text)
        if not isinstance(entry, dict):
            entry = {}
    except (json.JSONDecodeError, ValueError):
        entry = {}

    scores = entry.get("scores", {})
    if not isinstance(scores, dict):
        scores = {}

    total = None
    if scores:
        keys = (
            "hierarchy",
            "readability",
            "composition",
            "temporal_clarity",
            "emphasis",
            "economy",
        )
        vals = [scores[k] for k in keys if isinstance(scores.get(k), (int, float))]
        if vals:
            total = sum(vals)

    defects = entry.get("observed_defects", []) or []
    if not isinstance(defects, list):
        defects = []

    strengths = entry.get("strengths", []) or []
    if not isinstance(strengths, list):
        strengths = []

    improvements = entry.get("improvements", []) or []
    if not isinstance(improvements, list):
        improvements = []

    return {
        "observed_defects": defects,
        "scores": scores,
        "total": total,
        "strengths": strengths,
        "improvements": improvements,
    }


def review_animation_v2(
    prompt: str,
    requirements: list[dict],
    image_paths: list[str],
    code: str,
    previous_result: dict | None = None,
    geometry: dict | None = None,
) -> dict:
    """Two-branch evaluation: strict requirement verification PLUS a visual/
    conceptual critique.

    Unlike review_animation(), the critique reports concrete defects (object +
    frame range), scores a six-dimension rubric, and lists strengths to
    preserve, so the repair loop gets surgical instructions instead of
    free-text failure walls. The original review_animation() is unchanged.

    geometry (optional): the scene_meta spec. When present, its numeric
    validation errors are merged into the critique's observed_defects, and
    declared motion (a path with >=2 points) can confirm movement
    requirements that the frame descriptions deny.

    Output:
        requirements         per-requirement PASS/FAIL (same shape as v1)
        repair_instructions  targeted: failed reqs, then DEFECT/PRESERVE/IMPROVE
        visual_critique      {observed_defects, scores, total, strengths, improvements}
        preserve             strengths list (what must not change)
        failed_ids           ids of failed required requirements
    """
    geometry_errors = []
    declared_motion = False
    if geometry:
        geometry_errors = geom.validate(geometry)
        declared_motion = geom.has_declared_motion(geometry)

    frame_notes, position_tables = observe_frames(image_paths)
    observations = "\n".join(frame_notes)

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

        # Conservative movement override. Coarse left/center/right positions
        # can confirm movement, but they CANNOT prove it did not happen, so
        # only upgrade to PASS; never force a FAIL on measured no-change.
        if (
            measured
            and is_movement_requirement(requirement["description"])
            and "YES" in measured
            and not entry["pass"]
        ):
            entry["pass"] = True
            entry["confidence"] = 1.0
            entry["evidence"] = (
                f"Measured object positions confirm movement: {measured}"
            )

        # Declared geometry is ground truth: a path with >=2 distinct points
        # proves the object moves, regardless of what the frame notes say.
        if (
            declared_motion
            and is_movement_requirement(requirement["description"])
            and not entry["pass"]
        ):
            entry["pass"] = True
            entry["confidence"] = 1.0
            entry["evidence"] = (
                "Declared geometry in scene_meta confirms motion "
                "(path with distinct positions)."
            )

        results.append(entry)

    critique = _run_critique(prompt, code, image_paths)

    if geometry_errors:
        for err in geometry_errors:
            critique.setdefault("observed_defects", []).append(
                {
                    "object": err["object"],
                    "frames": err["frames"],
                    "problem": (
                        f"[{err['severity']}] {err['problem']}"
                    ),
                }
            )

    failed = [entry for entry in results if not entry["pass"]]

    repair_instructions = [
        (
            f"{entry['id']} FAILED: make the animation satisfy this requirement "
            f"clearly. Evaluator evidence: {entry['evidence']}"
        )
        for entry in failed
    ]

    for defect in critique.get("observed_defects", []):
        repair_instructions.append(
            f"DEFECT: '{defect.get('object')}' in frames "
            f"{defect.get('frames')}: {defect.get('problem')}. "
            f"Fix this specific overlap/obstruction."
        )

    for strength in critique.get("strengths", [])[:3]:
        repair_instructions.append(f"PRESERVE: {strength}")

    for improvement in critique.get("improvements", []):
        if improvement.get("priority") in ("high", "medium"):
            repair_instructions.append(
                f"IMPROVE ({improvement.get('priority')}, "
                f"{improvement.get('area')}): "
                f"{improvement.get('suggestion')}"
            )

    failed_ids = [entry["id"] for entry in failed]

    return {
        "requirements": results,
        "repair_instructions": repair_instructions,
        "visual_critique": critique,
        "preserve": critique.get("strengths", []),
        "failed_ids": failed_ids,
    }