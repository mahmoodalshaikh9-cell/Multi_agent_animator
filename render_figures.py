"""Render matplotlib figures from scene_meta into PNGs and register their
scene-unit bounding boxes so the geometry layer can validate them.

Figure code runs in a subprocess (mirroring render()) with a timeout. The
scene then embeds each figure with ImageMobject("figures/<id>.png"); the
harness rewrites those calls to absolute paths with enforced placement so the
geometry matches the declared scene_meta.
"""

import re
import subprocess
import sys

import cv2
from pathlib import Path

FIG_TIMEOUT = 120
FIG_DPI = 100

_WRAPPER = '''import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

{code}

fig.savefig(r"{png}", dpi={dpi}, bbox_inches="tight")
'''

_EMBED_RE = re.compile(r'ImageMobject\(\s*["\']figures/([\w.\-]+)\.png["\']\s*\)')


def _png_size(path):
    img = cv2.imread(str(path))
    if img is None:
        raise RuntimeError(f"Figure not produced: {path}")
    h, w = img.shape[:2]
    return w, h


def render_figures(spec, run_dir: Path):
    """Execute each figure's matplotlib code, write PNGs to run_dir/figures/,
    and register an 'image' object (with scene-unit bbox) into spec.

    Returns dict {fig_id: {"png", "bbox", "center", "width"}}.
    """
    fig_dir = run_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    info = {}
    for fig in spec.get("figures", []):
        fig_id = fig.get("id", f"fig_{len(info)}")
        out_png = fig_dir / f"{fig_id}.png"
        code = fig.get("code", "")
        center = fig.get("center", [0, 0])
        width = float(fig.get("width", 4.0))

        script = _WRAPPER.format(code=code, png=out_png, dpi=FIG_DPI)
        script_path = fig_dir / f"{fig_id}.py"
        script_path.write_text(script, encoding="utf-8")

        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(run_dir),
                capture_output=True,
                text=True,
                timeout=FIG_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Figure {fig_id} timed out after {FIG_TIMEOUT}s")
        if result.returncode != 0:
            raise RuntimeError(
                f"Figure {fig_id} failed:\n{result.stderr[-2000:]}"
            )

        w_px, h_px = _png_size(out_png)
        height = width * (h_px / w_px) if w_px else 1.0
        bbox = [
            center[0] - width / 2,
            center[1] - height / 2,
            center[0] + width / 2,
            center[1] + height / 2,
        ]

        spec.setdefault("objects", []).append(
            {
                "id": fig_id,
                "kind": "image",
                "bbox": bbox,
                "frames": "all",
                "figure": True,
            }
        )
        info[fig_id] = {"png": out_png, "bbox": bbox, "center": center, "width": width}

    return info


def embed_figures(code: str, spec: dict, info: dict) -> str:
    """Rewrite ImageMobject("figures/<id>.png") calls to absolute paths with
    enforced placement, so geometry matches the declared scene_meta."""
    def _repl(match):
        fig_id = match.group(1)
        if fig_id not in info:
            return match.group(0)
        png = info[fig_id]["png"]
        cx, cy = info[fig_id]["center"]
        width = info[fig_id]["width"]
        return (
            f'ImageMobject(r"{png}")'
            f'.move_to([{cx}, {cy}, 0])'
            f'.scale_to_fit_width({width})'
        )

    return _EMBED_RE.sub(_repl, code)
