"""Deterministic temporal analysis of the rendered animation (OpenCV).

Ground-truth evidence (no hallucination) about:
- motion: frame-to-frame change ratio + active runs
- appearance / disappearance / persistence of content
- pacing: change bursts vs stillness, total duration

Events are reported in seconds. This is merged like geometry.py: it can
confirm movement requirements deterministically and add temporal observations
the vision model cannot fabricate.
"""
import cv2
import numpy as np

CONTENT_DARK = 200        # pixel brightness below this counts as content on white bg
CONTENT_COLOR = 40        # channel spread above this counts as colored content
MOTION_THRESHOLD_PCT = 0.4
ACTIVE_RUN_PCT = 0.5      # fraction of changed pixels to call a frame active
MAX_FRAMES = 600
PROBE_W = 320
PROBE_H = 180


def _content_mask(gray):
    return gray < CONTENT_DARK


def _is_content_pixel(bgr):
    mx = int(bgr.max())
    mn = int(bgr.min())
    return (int(bgr[0]) < CONTENT_DARK or mx - mn > CONTENT_COLOR)


def analyze(video_path, max_frames=MAX_FRAMES):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    n = min(total, max_frames) if total > 0 else 0

    if n < 2:
        cap.release()
        return {
            "available": False,
            "duration_s": 0.0,
            "fps": fps,
            "frames": n,
        }

    prev_gray = None
    motion_pct = []
    content_pct = []
    for _ in range(n):
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.resize(frame, (PROBE_W, PROBE_H))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        content = _content_mask(gray).mean() * 100.0
        content_pct.append(content)
        if prev_gray is not None:
            diff = cv2.absdiff(prev_gray, gray)
            motion_pct.append(float((diff > MOTION_THRESHOLD_PCT).mean()) * 100.0)
        else:
            motion_pct.append(0.0)
        prev_gray = gray
    cap.release()

    n_frames = len(motion_pct)
    if n_frames < 2:
        return {
            "available": False,
            "duration_s": 0.0,
            "fps": fps,
            "frames": n_frames,
        }

    active = [m >= ACTIVE_RUN_PCT for m in motion_pct]

    # Active runs (motion phases) -> (start_idx, end_idx)
    runs = []
    in_run = False
    start = 0
    for i, a in enumerate(active):
        if a and not in_run:
            start, in_run = i, True
        elif not a and in_run:
            runs.append((start, i - 1))
            in_run = False
    if in_run:
        runs.append((start, n_frames - 1))

    def t(i):
        return round(i / fps, 2)

    # Content appearance / disappearance (coarse: near-empty vs present)
    present = [c > 1.0 for c in content_pct]
    appearances = []
    disappearances = []
    for i in range(1, n_frames):
        if not present[i - 1] and present[i]:
            appearances.append({"t": t(i), "event": "content appears on screen"})
        if present[i - 1] and not present[i]:
            disappearances.append({"t": t(i), "event": "content disappears"})

    present_frames = [i for i, p in enumerate(present) if p]

    motion_fraction = round(sum(motion_pct) / n_frames, 2)
    has_motion = bool(runs) and motion_fraction >= 0.05

    # Pacing heuristic
    if not has_motion:
        pacing = "static: no significant motion detected"
    elif len(runs) <= 1:
        pacing = "single continuous motion phase"
    elif len(runs) >= 6:
        pacing = "crowded: many short bursts of activity"
    else:
        pacing = f"{len(runs)} distinct motion phases"

    return {
        "available": True,
        "duration_s": round((n_frames - 1) / fps, 2),
        "fps": round(fps, 2),
        "frames": n_frames,
        "has_motion": has_motion,
        "motion_fraction": motion_fraction,
        "motion_phases": [
            {"t": f"{t(s)}-{t(e)}"} for s, e in runs
        ],
        "appearances": appearances,
        "disappearances": disappearances,
        "persistence": {
            "present_fraction": round(len(present_frames) / n_frames, 3)
            if present_frames else 0.0,
            "first_t": t(present_frames[0]) if present_frames else None,
            "last_t": t(present_frames[-1]) if present_frames else None,
        },
        "pacing": pacing,
    }
