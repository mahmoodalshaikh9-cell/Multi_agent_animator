
import base64
import json
from pathlib import Path

import requests

import metrics
import secrets_loader

KEY = secrets_loader.get("openrouter_cohere_key")

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-flash"
VIDEO_TIMEOUT = 300
MAX_VIDEO_BYTES = 12_000_000

TEMPORAL_SYSTEM_PROMPT = """You are an animation temporal-behavior analyst.

You watch a rendered animation VIDEO directly. Your job is to reason about
things that still frames cannot show: actual motion, timing/order, transitions,
whether objects stay on screen, cause->effect relationships, pacing, objects
appearing/disappearing, and temporary overlaps.

Observe the video as it plays. Report events with timestamps in seconds
(e.g. "t": "2.1-4.3").

Return ONLY valid JSON:
{
  "temporal_events": [
    {"t": "2.1-4.3", "event": "the blue circle moves from left to right"}
  ],
  "requirement_verdicts": [
    {"id": "R2", "pass": true, "confidence": 0.9,
     "evidence": "observed the ball translating left->right between 2.1s and 4.3s"}
  ],
  "temporal_defects": [
    {"object": "equation", "t": "5.2-5.4",
     "problem": "fades out before it can be read"}
  ],
  "pacing": "brief overall assessment, e.g. fast intro, slow middle",
  "sequence_notes": "notes about order/transitions/cause-effect, if any"
}

Rules:
- Judge each requirement in the list given by the user: give the id, a pass
  boolean, confidence 0-1, and evidence from what you saw in the VIDEO.
- Only report a temporal_defect if you actually observe it with a time range;
  do not invent problems.
- Timestamps are seconds from the start of the video.
"""


def _parse(text):
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    try:
        entry = json.loads(text)
        return entry if isinstance(entry, dict) else {}
    except json.JSONDecodeError:
        pass
    # Repair the comma small models forget between adjacent quoted strings.
    repaired = __import__("re").sub(r'"\s*\n\s*"', '",\n"', text)
    try:
        entry = json.loads(repaired)
        return entry if isinstance(entry, dict) else {}
    except json.JSONDecodeError:
        return {}


def evaluate_video(video_path, requirements, prompt):
    """Return a temporal-review dict (with "available": true/false)."""
    video_path = Path(video_path)
    if not video_path.exists():
        return {"available": False, "reason": "video missing"}
    size = video_path.stat().st_size
    if size > MAX_VIDEO_BYTES:
        return {"available": False, "reason": f"video too large ({size} bytes)"}

    with open(video_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    data_url = f"data:video/mp4;base64,{b64}"

    req_text = "\n".join(
        f"{r['id']}: {r['description']}" for r in requirements
    )

    content = [
        {
            "type": "text",
            "text": (
                "Original request:\n\n"
                f"{prompt}\n\n"
                "Requirements to verify from the video:\n\n"
                f"{req_text}\n\n"
                "Watch the video and produce the JSON output."
            ),
        },
        {"type": "video_url", "video_url": {"url": data_url}},
    ]

    try:
        response = requests.post(
            URL,
            headers={
                "Authorization": f"Bearer {KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": TEMPORAL_SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                "temperature": 0,
                "stream": False,
            },
            timeout=VIDEO_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as err:
        return {"available": False, "reason": f"{type(err).__name__}: {err}"}

    try:
        payload = response.json()
    except ValueError as err:
        return {"available": False, "reason": f"bad response: {err}"}
    metrics.record_llm(MODEL, prompt + "\n" + req_text, payload.get("usage"))
    try:
        content = payload["choices"][0]["message"].get("content")
        text = (content or "").strip()
    except (KeyError, IndexError, ValueError, AttributeError) as err:
        return {"available": False, "reason": f"bad response: {err}"}
    if not text:
        return {"available": False, "reason": "empty model response"}

    entry = _parse(text)
    if not entry:
        return {"available": False, "reason": "unparseable model response"}

    return {"available": True, **entry}
