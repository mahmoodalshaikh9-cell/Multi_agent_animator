"""Numeric geometry validation for the scene_meta contract.

Severity model (hybrid):
  hard  - out-of-bounds, NaN/inf, malformed entries. These mean the render
          would contain invisible/broken content, so the pipeline should skip
          rendering and repair before spending a render.
  soft  - pairwise bounding-box overlap. Advisory; the render still happens
          and the warning is merged into the review's observed_defects.

Coordinates are Manim scene units. Default Manim frame is 14.222 x 8.0.
"""

FRAME_WIDTH = 14.222
FRAME_HEIGHT = 8.0
FRAME_MARGIN = 0.0

# Kinds treated as background containers: everything inside them is expected
# to overlap them, so they are excluded from soft-overlap detection.
CONTAINER_KINDS = {
    "axes", "axis", "grid", "path", "trajectory", "background",
    "rect", "rectangle", "box",
}

# Objects declared with a motion path are lines, not areas; skip them as
# overlap participants too.
def _is_container(entry):
    if entry.get("kind") in CONTAINER_KINDS:
        return True
    if entry.get("path") or entry.get("trajectory"):
        return True
    return False


def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def parse_frames(entry):
    raw = entry.get("frames")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return (int(raw), int(raw))
    if isinstance(raw, str):
        parts = raw.split("-")
        try:
            if len(parts) == 2:
                return (int(parts[0]), int(parts[1]))
            if len(parts) == 1:
                return (int(parts[0]), int(parts[0]))
        except ValueError:
            return None
    return None


def object_bbox(entry):
    """Return [xmin, ymin, xmax, ymax] for an object entry, or None."""
    kind = entry.get("kind")
    if kind == "arrow":
        start = entry.get("start")
        end = entry.get("end")
        if not start or not end:
            return None
        return [
            min(start[0], end[0]),
            min(start[1], end[1]),
            max(start[0], end[0]),
            max(start[1], end[1]),
        ]
    if entry.get("bbox") and len(entry["bbox"]) == 4:
        return list(entry["bbox"])
    center = entry.get("center")
    if not center:
        return None
    if kind in ("dot", "circle", "ball", "point") and entry.get("radius"):
        r = entry["radius"]
        return [center[0] - r, center[1] - r, center[0] + r, center[1] + r]
    width = entry.get("width", 1.0)
    height = entry.get("height", 1.0)
    return [
        center[0] - width / 2,
        center[1] - height / 2,
        center[0] + width / 2,
        center[1] + height / 2,
    ]


def _has_nan(vals):
    return any(
        v is None or (isinstance(v, float) and v != v) for v in vals
    )


def boxes_overlap(a, b, eps=0.05):
    return (
        a[0] + eps < b[2] - eps
        and b[0] + eps < a[2] - eps
        and a[1] + eps < b[3] - eps
        and b[1] + eps < a[3] - eps
    )


def frames_overlap(fa, fb):
    if fa is None or fb is None:
        return True
    return fa[0] <= fb[1] and fb[0] <= fa[1]


def validate(
    spec,
    frame_width=FRAME_WIDTH,
    frame_height=FRAME_HEIGHT,
    margin=FRAME_MARGIN,
):
    """Return a list of error dicts: {object, frames, problem, severity}."""
    errors = []
    objects = spec.get("objects", [])

    for entry in objects:
        oid = entry.get("id", "?")
        fr = entry.get("frames", "all")
        bbox = object_bbox(entry)
        if bbox is None:
            errors.append(
                {
                    "object": oid,
                    "frames": fr,
                    "problem": (
                        "malformed scene_meta entry: needs center(+width/height "
                        "or radius) or start/end"
                    ),
                    "severity": "hard",
                }
            )
            continue
        if _has_nan(bbox):
            errors.append(
                {
                    "object": oid,
                    "frames": fr,
                    "problem": f"NaN/None coordinate in bbox {bbox}",
                    "severity": "hard",
                }
            )
            continue

        xmin, ymin, xmax, ymax = bbox
        out = []
        if xmin < -frame_width / 2 + margin or xmax > frame_width / 2 - margin:
            out.append("x")
        if ymin < -frame_height / 2 + margin or ymax > frame_height / 2 - margin:
            out.append("y")
        if out:
            errors.append(
                {
                    "object": oid,
                    "frames": fr,
                    "problem": (
                        f"bbox {[round(v, 2) for v in bbox]} outside frame "
                        f"({frame_width}x{frame_height}, margin {margin}) "
                        f"on {'/'.join(out)} axis"
                    ),
                    "severity": "hard",
                }
            )

    n = len(objects)
    frame_area = frame_width * frame_height
    max_container_area = frame_area * 0.25

    for i in range(n):
        for j in range(i + 1, n):
            a, b = objects[i], objects[j]
            if not frames_overlap(parse_frames(a), parse_frames(b)):
                continue
            # Only label-vs-object collisions are meaningful defects; object-
            # vs-object adjacency (arrow on trajectory, ball in axes) is not.
            if not (
                a.get("kind") in ("text", "label")
                or b.get("kind") in ("text", "label")
            ):
                continue
            if _is_container(a) or _is_container(b):
                continue
            ba = object_bbox(a)
            bb = object_bbox(b)
            if ba is None or bb is None:
                continue
            if _has_nan(ba) or _has_nan(bb):
                continue
            area_a = _area(ba)
            area_b = _area(bb)
            if area_a > max_container_area or area_b > max_container_area:
                continue
            inter_w = min(ba[2], bb[2]) - max(ba[0], bb[0])
            inter_h = min(ba[3], bb[3]) - max(ba[1], bb[1])
            inter = max(0.0, inter_w) * max(0.0, inter_h)
            smaller = min(area_a, area_b)
            if smaller <= 0:
                continue
            if inter / smaller < 0.15:
                continue
            errors.append(
                {
                    "object": f"{a.get('id', '?')} & {b.get('id', '?')}",
                    "frames": a.get("frames", "all"),
                    "problem": (
                        f"label bbox {[round(v, 2) for v in ba]} intersects "
                        f"bbox {[round(v, 2) for v in bb]} "
                        f"({round(100 * inter / smaller)}% of smaller box)"
                    ),
                    "severity": "soft",
                }
            )

    return errors


def has_declared_motion(spec):
    """True if any object declares a path/trajectory with >=2 distinct points."""
    for entry in spec.get("objects", []):
        path = entry.get("path") or entry.get("trajectory")
        if isinstance(path, list) and len(path) >= 2:
            pts = [
                tuple(p)
                for p in path
                if isinstance(p, (list, tuple)) and len(p) >= 2
            ]
            if len(set(pts)) > 1:
                return True
    return False
