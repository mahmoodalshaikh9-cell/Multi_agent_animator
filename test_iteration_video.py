"""Iteration harness for the hybrid video-level evaluator.

Recreates the pipeline loop (pipeline_deepseek.py is untouched) with a
lean, cheap-first structure so the expensive steps never repeat needlessly:

  scene_meta codegen -> cheap static gates (syntax / unknown symbols /
    undefined self.<attr> reads / loops / hallucinated methods) -> geometry
    validation + figure rendering (hard errors repair WITHOUT rendering) ->
    Manim render once -> deterministic temporal analysis -> frame vision
    branch on SELECTED frames -> gated video-level temporal evaluation (forced
    on the final/polish attempt) -> merge (pass-if-any-confirm) -> INCREMENTAL
    repair seeded from the running best code -> stop when everything passes at
    or above the polish threshold.

Iteration compounds instead of restarting: a running best (highest req-pass,
then highest rubric) is kept, every repair edits the best code in place with
an explicit 'modify ONLY these failing parts' directive, and a candidate is
adopted only if it does not regress a previously-passing requirement.

All iteration-specific logic lives here and in static_checks.py; the core
pipeline modules are not modified.

Usage: python test_iteration_video.py [slug] [--consume]
Slugs: streamlit_ui, projectile_motion, vectors_weak, dense_labels, iron_atom
--consume keeps consuming all 6 attempts even when everything passes, driving
polish from the visual-quality critique (for experiments).
"""
import json
import re
import requests
import shutil
import subprocess
import sys
import time
import toml
from pathlib import Path

from extract_frame import extract_frames
from local_agent import clean_code, extract_requirements, find_unknown_symbols, planning
from pipeline_deepseek import (
    RENDER_TIMEOUT,
    SYSTEM_PROMPT,
    _render_error_prompt,
    _syntax_repair_prompt,
    _timeout_repair_prompt,
    render,
    system_prompt,
    validate_python,
)
from vision import review_animation_v2

import geometry
import merge_evaluation
import render_figures
import scene_meta
import static_checks
import temporal
import video_eval

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).parent
MAX_PIPELINE_TIME = 1500

# Cheap-and-lean production mode: stop as soon as every requirement passes.
# Set CONSUME_ATTEMPTS=True (or pass --consume) to keep consuming all attempts
# even when nothing fails, driving repairs from the visual-quality critique.
CONSUME_ATTEMPTS = False

# The frame vision branch is the most expensive part (one vision call per
# frame). Subsample to this many evenly-spaced frames instead of the full 10.
FRAME_SAMPLE_COUNT = 6

# Rubric gate: when all requirements pass but the visual/temporal score is
# below this, run exactly one focused polish pass (targeted at defects, not a
# rewrite) before stopping.
POLISH_THRESHOLD = 22

PROMPTS = {
    "streamlit_ui": "explain how streamlit compiles python into UI",
    "projectile_motion": """Create a polished, cinematic educational Manim animation illustrating projectile motion. Use a clean 2D coordinate system with clearly visible horizontal and vertical axes, and keep the entire composition inside the frame.

A ball is launched from the origin at an upward angle and follows a realistic parabolic trajectory under constant gravitational acceleration. The ball should visibly travel along the curved trajectory rather than simply appearing at different positions.

At the launch point, display a launch-angle indicator labeled θ. Attach a velocity arrow to the ball showing its initial velocity direction. Visually decompose the velocity into horizontal and vertical components, with separate arrows and labels for the horizontal component vₓ and vertical component vᵧ. Make the vector directions and labels remain spatially associated with the ball as it moves.

The projectile should initially have a clearly upward and forward velocity. As the ball travels upward, reaches its maximum height, and descends, the vertical velocity component should visually decrease to zero at the apex and then reverse direction during the descent, while the horizontal component remains constant.

Also display the projectile-motion equation

y = v₀ sin(θ)t − ½gt²

on screen throughout the main portion of the animation. The equation should be visually separated from the trajectory and should not overlap the axes, ball, or velocity vectors.

Structure the animation progressively: first establish the axes and launch point, then introduce the launch angle and initial velocity, then reveal the velocity components and equation, and finally animate the complete projectile trajectory.

Use a consistent color scheme to distinguish the projectile, trajectory, velocity vectors, velocity components, angle indicator, axes, and equation. Keep the visual style clean and cinematic rather than cluttered.

The final few seconds should show the completed projectile motion simultaneously: the ball moving along the trajectory, the trajectory visible, the velocity/vector components visible, the launch angle identifiable, the equation readable, and the axes remaining visible.

The animation should be under 8 seconds, use smooth transitions, and avoid unnecessary objects or decorative elements.""",
    "vectors_weak": "Make an animation about vectors and what magnitude and direction mean.",
    "dense_labels": """Create an animation with 14 small labeled objects clustered tightly together near the center of the frame: seven circles and seven arrows, each with a short text label right next to it (label the circles "A" through "G" and the arrows "u" through "z"). Put every object within 2 scene units of the center so the labels and shapes are packed close to each other. Use a different color for each object. Keep the labels small but readable. Introduce all objects at once, hold them, then fade them out together.""",
    "iron_atom": """Create an elegant, cinematic 3D visualization of an iron (Fe) atom on a completely black background, with no text, labels, numbers, axes, or UI elements.

The scene should depict a stylized atomic nucleus at the center, surrounded by three distinct electron shells. Represent the electrons as small glowing dots moving continuously along orbital paths around the nucleus.

The electron configuration should visually correspond to an iron atom: 2 electrons in the first shell, 8 in the second shell, and 14 in the third shell, for a total of 24 electrons. Distribute the electrons around their respective orbital paths rather than clustering them in one location.

Make the three shells clearly distinguishable through different orbital radii, while keeping their visual treatment consistent. The orbital paths should appear as thin, subtle luminous curves, and the electrons should remain clearly visible as brighter points moving along those paths.

Use a restrained cinematic color palette: a warm orange/gold nucleus, cool blue-white electrons, and faint blue/cyan orbital paths. Keep these colors consistent throughout the animation.

The nucleus should have a slightly more complex appearance than a single sphere, suggesting a dense collection of particles, but it should remain visually simple enough for real-time preview rendering.

The animation should begin with the nucleus alone, then progressively reveal the orbital shells, followed by the electrons appearing on their respective paths. Once everything is established, show the electrons continuously orbiting for several seconds.

Use a slow, smooth camera movement around the atom so the three-dimensional structure and different orbital planes are clearly visible. The camera should not rotate so quickly that the electron paths become difficult to follow.

The final composition should feel like a polished scientific visualization rather than a literal textbook diagram: dark, minimal, cinematic, spatially layered, and visually coherent.

Keep the entire animation under 8 seconds and ensure that all elements remain inside the camera frame throughout the animation.""",
    "kmeans": """on a black backgeound draw a grid. use complemntary colors to represent K means. draw three circles that reposition between clusters to find the right centroid divison draw lines represnting grouping between the centroid and the dot. add the proper text to explain each step, take care of proxmity and readability""",
    "la_espada": """the words 'la espada' appear in a deep red color (a strong, readable crimson-red, not pale and not orange) on a pure black background, slowly blinking into view letter by letter, one letter at a time. After all the letters are visible, the red writing breaks apart into many small particles that scatter briefly. The particles then rush back across the screen, rejoin, and coalesce into ONE single solid, connected sword: a complete sword with a long pointed blade, a crossguard and a hilt, rendered as one continuous filled silhouette (with no gaps between particles, not a scattered cloud of dots). The finished sword is placed diagonally on the screen, clearly visible in one piece, and holds that shape for the final seconds.""",
}


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


_DARK_BACKGROUND_RE = re.compile(
    r"\bblack\s*(?:background|screen|backdrop)\b|\bdark\s*(?:background|screen)\b",
    re.IGNORECASE,
)


def background_color_for(prompt: str) -> str:
    return "BLACK" if _DARK_BACKGROUND_RE.search(prompt) else "WHITE"


# OpenRouter codegen backend for THIS video pipeline only. Every codegen call
# in test_iteration_video.py goes through GPT-5.6 Luna instead of DeepSeek;
# all other harnesses/pipelines keep their existing backends untouched.
OR_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
OR_MODEL = "openai/gpt-5.6-luna"
OR_TIMEOUT = 300


def _or_headers() -> dict:
    secrets_data = toml.load(BASE_DIR / "secrets.toml")
    key = secrets_data.get("openrouter_cohere_key", "")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _or_chat(prompt: str, system_prompt: str, temperature: float) -> str:
    response = requests.post(
        OR_BASE_URL,
        headers=_or_headers(),
        json={
            "model": OR_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": 4096,
            "stream": False,
        },
        timeout=OR_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def ask_coder_luna(prompt: str, temperature: float = 0.2, three_d: bool = False) -> str:
    """Plain codegen (no scene_meta) via OpenRouter GPT-5.6 Luna."""
    return _or_chat(prompt, system_prompt(three_d), temperature)


def ask_coder_meta_luna(prompt: str, temperature: float = 0.2, three_d: bool = False) -> str:
    """Codegen + scene_meta via OpenRouter GPT-5.6 Luna."""
    return _or_chat(prompt, scene_meta.codegen_meta_system_prompt(three_d), temperature)


def generate(prompt: str, scene_plan: dict, temperature: float = 0.2, three_d: bool = False):
    raw = ask_coder_meta_luna(
        scene_meta.build_codegen_prompt(prompt, scene_plan), temperature, three_d=three_d
    )
    scene_part, meta, has_meta = scene_meta.extract_scene_meta(raw)
    return clean_code(scene_part), meta, has_meta


def generate_repair(repair_prompt: str, temperature: float = 0.2, three_d: bool = False):
    """Meta-aware codegen FROM an already-built repair/polish prompt.

    The repair prompts embed the best previous code plus targeted directives,
    so this is how iteration compounds instead of restarting: the model edits
    the seeded code rather than regenerating from the scene plan alone.
    """
    raw = ask_coder_meta_luna(repair_prompt, temperature, three_d=three_d)
    scene_part, meta, has_meta = scene_meta.extract_scene_meta(raw)
    return clean_code(scene_part), meta, has_meta


def print_table(out: Path, attempts: list[dict]) -> None:
    print(f"\n--- TABLE {out.name} ---")
    header = f"{'Attempt':<8}{'Stage':<18}{'Reqs':<8}{'Video':<7}{'Temporal':<8}{'Total'}"
    print(header)
    print("-" * len(header))
    for a in attempts:
        reqs = (
            f"{a['requirements_pass']}/{a['requirements_total']}"
            if a["requirements_pass"] is not None
            else "-"
        )
        total = a.get("quality_total")
        total = total if total is not None else "-"
        print(
            f"{a['attempt']:<8}{a['stage']:<18}{reqs:<8}"
            f"{'Y' if a.get('video_available') else 'N':<7}"
            f"{'Y' if a.get('temporal_available') else 'N':<8}"
            f"{total:<8}"
        )


# Budget safety valve for the video branch. When True, video_eval only runs
# on failed attempts in the back half (attempt >= 3), so up to 6 x 300s
# MP4 uploads cannot burn the 1500s pipeline budget before later attempts
# ever render. Leave False: run video_eval on every failed attempt and only
# flip this if a chunk-3 run shows the budget is being blown.
VIDEO_EVAL_BACK_HALF_ONLY = False


def _should_run_video_eval(
    frame_result, requirements, consume, attempt, force_video=False
) -> str | None:
    """Run the expensive MP4 upload whenever anything failed; skip only on a
    full pass (except in consume mode, or when force_video is set on the
    final/polish attempt).

    The video branch is the only one that can observe temporal/equation
    content the still-frame branch misses, so a FAIL without it is
    under-evaluated (e.g. the equation-detection miss R4/R6). On a polish
    attempt the frames may all pass while pacing/motion continuity are still
    defective - only the video branch can produce that temporal defect list.
    """
    failed_ids = set(frame_result.get("failed_ids", []))
    if not failed_ids and not force_video and consume:
        return "quality mode: all frame requirements pass, want pacing critique"
    if not failed_ids and not force_video:
        return None
    if VIDEO_EVAL_BACK_HALF_ONLY and attempt < 3 and not force_video:
        return None
    if failed_ids:
        return "video can add a vote on failed requirement(s): " + ", ".join(
            sorted(failed_ids)
        )
    if force_video:
        return "final/polish attempt: want the video temporal defect list for the critique"
    return None


def _map_frames_to_time(frames, fps):
    """Map a vision frame-index range like '1-4' to wall-clock seconds."""
    if not frames or not fps:
        return frames
    parts = str(frames).split("-")
    try:
        start = int(parts[0])
        end = int(parts[1]) if len(parts) > 1 else start
    except ValueError:
        return frames
    return f"~t={round(start / fps, 2)}s-{round(end / fps, 2)}s (frames {start}-{end})"


def enrich_result(result, requirements, meta, temporal_result):
    """Make the critique actionable before it becomes a repair prompt.

    Cheap post-merge transform (review.json on disk stays canonical; this
    deep-copies and enriches only what the repair/polish prompt sees):
      - each failed requirement gets 'TARGET <id>: <description>' plus any
        deterministic temporal / declared-motion signal;
      - each observed defect gets the declared scene_meta bbox (when the
        defect names a known object) and a wall-clock time for its frame range.
    It cannot measure quantities (e.g. an angle) - that would need pixel
    analysis; it names the object, the time, and what correct looks like.
    """
    import copy

    enriched = copy.deepcopy(result)
    req_by_id = {r["id"]: r for r in requirements}

    for entry in enriched.get("requirements", []):
        rid = entry.get("id")
        req = req_by_id.get(rid)
        if not req or entry.get("pass") is True:
            continue
        extra = f"TARGET {rid}: {req.get('description')}."
        if temporal_result and temporal_result.get("available"):
            if temporal_result.get("has_motion"):
                phases = ", ".join(
                    p.get("t", "?")
                    for p in temporal_result.get("motion_phases", [])[:4]
                )
                extra += f" Temporal signal: motion at t={phases}."
            else:
                extra += " Temporal signal: NO motion detected."
        if meta:
            if any(
                isinstance(o.get("path") or o.get("trajectory"), list)
                for o in meta.get("objects", [])
            ):
                extra += " scene_meta declares motion paths."
        entry["evidence"] = (entry.get("evidence", "") + " " + extra).strip()

    fps = temporal_result.get("fps") if temporal_result and temporal_result.get("available") else None

    for d in enriched.get("visual_critique", {}).get("observed_defects", []) or []:
        oid = d.get("object", "")
        name = str(oid).split(" & ")[0].strip()
        ctx = []
        if meta:
            for o in meta.get("objects", []):
                if o.get("id") == name:
                    bbox = geometry.object_bbox(o)
                    if bbox:
                        ctx.append(f"declared bbox {[round(v, 2) for v in bbox]}")
                    if o.get("frames"):
                        ctx.append(f"declared frames {o['frames']}")
                    break
        time_note = _map_frames_to_time(d.get("frames"), fps)
        if time_note and time_note != d.get("frames"):
            ctx.append(time_note)
        if ctx:
            d["problem"] = (
                f"{d.get('problem', '')} CONTEXT: " + "; ".join(ctx)
            ).strip()

    return enriched


def run(slug: str, consume: bool = CONSUME_ATTEMPTS, out_dir: Path | None = None,
        prompts: dict | None = None) -> None:
    prompt = (prompts or PROMPTS)[slug]
    background_color = background_color_for(prompt)
    out = (out_dir or (BASE_DIR / "baseline_runs" / "video_iteration")) / slug
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("attempt_*"):
        shutil.rmtree(stale, ignore_errors=True)
    _write(out / "prompt.txt", prompt)

    print(f"\n{'=' * 70}\nVIDEO ITERATION [{slug}]: {prompt}\n{'=' * 70}")

    requirements = extract_requirements(prompt)
    _write(out / "requirements.json", json.dumps(requirements, indent=2))
    scene_plan = planning(prompt, requirements)
    _write(out / "scene_plan.json", json.dumps(scene_plan, indent=2))
    three_d = scene_meta.is_3d(scene_plan)
    print(f"  mode: {'3D' if three_d else '2D'} scene (three_d={three_d})")

    print("\n[3] Generating code + scene_meta...")
    code, meta, has_meta = generate(prompt, scene_plan, temperature=0.1, three_d=three_d)
    print(f"  scene_meta present: {has_meta} ({len(meta.get('objects', []))} objects)")

    previous_result = None
    pipeline_start = time.time()
    attempts = []
    best = None
    polish_done = False

    for attempt in range(6):
        elapsed = time.time() - pipeline_start
        if elapsed > MAX_PIPELINE_TIME:
            print(f"\nPipeline time limit reached ({MAX_PIPELINE_TIME}s). Stopping.")
            break

        attempt_dir = out / f"attempt_{attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        _write(attempt_dir / "code.py", code)

        print(f"\n=== ATTEMPT {attempt + 1} ===")
        print(code[:300] + ("..." if len(code) > 300 else ""))

        stage = "rendered"
        repair_prompt = None
        geometry_errors = []

        # --- validation stages (same as pipeline) ---
        valid, syntax_error = validate_python(code)
        if not valid:
            print(f"\n[VALIDATION] Invalid Python: {syntax_error}")
            stage = "syntax_repair"
            repair_prompt = _syntax_repair_prompt(prompt, code, syntax_error, scene_plan)
        else:
            obj_budget = (
                "Max 40 individual objects total."
                if three_d
                else "Max 15 individual objects total."
            )
            unknown_symbols = find_unknown_symbols(code)
            if unknown_symbols:
                print(f"\n[VALIDATION] Unknown symbols: {', '.join(unknown_symbols)}")
                stage = "unknown_symbol_repair"
                repair_prompt = f"""Original request:

{prompt}

Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}

Previous code:

{code}

These symbols do NOT exist in Manim Community Edition
and must be removed or replaced with real APIs:

{chr(10).join(f'- {symbol}' for symbol in unknown_symbols)}

Rules:

- Never invent methods that do not exist.
- You MAY use TracedPath(mob.get_center, ...).

- Keep the scene simple.
- {obj_budget}
- Return ONLY complete Python code.
- Do NOT include reasoning or explanations.
- The class MUST be named GeneratedScene."""
            else:
                undefined_attrs = static_checks.find_undefined_self_attrs(code)
                premature_attrs = static_checks.find_premature_self_attrs(code)
                readonly_attrs = static_checks.find_readonly_self_assignments(code)
                broadcast_errors = static_checks.find_2d_3d_broadcast(code)
                closure_errors = static_checks.find_closure_before_assign(code)
                loop_errors = static_checks.find_loop_play_risks(code)
                method_errors = static_checks.find_unknown_methods(code)
                if method_errors:
                    print(f"\n[VALIDATION] unknown method call(s):")
                    for err in method_errors:
                        print(f"  {err}")
                    stage = "unknown_method_repair"
                    repair_prompt = scene_meta.build_method_repair_prompt(
                        prompt, scene_plan, code, method_errors
                    )
                elif loop_errors:
                    print(f"\n[VALIDATION] loop render-timeout risk(s):")
                    for err in loop_errors:
                        print(f"  {err}")
                    stage = "loop_timeout_repair"
                    repair_prompt = scene_meta.build_loop_repair_prompt(
                        prompt, scene_plan, code, loop_errors
                    )
                elif (
                    undefined_attrs or premature_attrs or readonly_attrs
                    or broadcast_errors or closure_errors
                ):
                    print(
                        f"\n[VALIDATION] static issues: "
                        f"undefined={undefined_attrs} "
                        f"premature={premature_attrs} "
                        f"readonly={readonly_attrs} "
                        f"2d3d={broadcast_errors} "
                        f"closure={closure_errors}"
                    )
                    stage = "undefined_self_attr_repair"
                    issue_lines = []
                    for attr in undefined_attrs:
                        issue_lines.append(
                            f"- self.{attr}: READ but never assigned anywhere "
                            "in the class."
                        )
                    for attr in premature_attrs:
                        issue_lines.append(
                            f"- self.{attr}: READ inside an always_redraw/"
                            "AlwaysRedraw callback but first assigned AFTER the "
                            "callback. always_redraw runs its function "
                            "immediately, so this raises AttributeError before "
                            "the animation starts."
                        )
                    for attr in readonly_attrs:
                        issue_lines.append(
                            f"- self.{attr}: ASSIGNED but it is a read-only "
                            "Manim property (cannot be assigned)."
                        )
                    for err in broadcast_errors:
                        issue_lines.append(
                            f"- {err}: mixes a 2D numpy array with a Manim 3D "
                            "point. Manim points are 3D (shape (3,)); a 2D "
                            "np.array([x, y]) has shape (2,) and the render "
                            "crashes with 'operands could not be broadcast "
                            "together with shapes (3,) (2,)'. Promote the 2D "
                            "array to 3D, e.g. dir_vec = np.array([vx, vy, 0]) "
                            "or np.append(dir_vec, 0)."
                        )
                    for err in closure_errors:
                        issue_lines.append(
                            f"- {err}: an always_redraw lambda or comprehension "
                            "reads a local variable that is assigned LATER in "
                            "the same function. always_redraw and comprehensions "
                            "run immediately, so this raises 'NameError: free "
                            "variable ... referenced before assignment' before "
                            "the animation starts. Move the assignment BEFORE "
                            "the lambda/comprehension."
                        )
                    three_d_closure_block = ""
                    if three_d:
                        three_d_closure_block = '''
- closure in a 3D scene (working orbit pattern): update functions on
  electrons may only close over variables that are ALREADY bound when the
  updater is created. Precompute every orbit basis / radius list BEFORE the
  loop, and bind per-electron values as keyword defaults. CORRECT pattern:

    angle_tracker = ValueTracker(0)          # must exist before updaters
    bases = [plane_basis(v) for v in shell_normals]   # precomputed first
    for i, count in enumerate([2, 8, 14]):
        for k in range(count):
            electron = Dot3D(...)
            def update(mob, dt, bi=bases[i], r=shell_radii[i],
                       a0=phase + TAU * k / count, w=speed):
                mob.move_to(orbit_point(r, bi, angle_tracker.get_value() * w + a0))
            electron.add_updater(update)

  NEVER read `bases`/`radii`/loop vars directly inside add_updater without
  pre-binding them first as default arguments.'''
                    repair_prompt = f"""Original request:

{prompt}

Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}

Previous code:

{code}

Static pre-render checks found bugs that will crash Manim before the
animation starts:

{chr(10).join(issue_lines)}

Fix ALL of them:

- undefined: assign each once (e.g. in construct, before any updater or
  AlwaysRedraw references it) with a sensible default value.
- premature: move the assignment BEFORE the always_redraw/AlwaysRedraw
  callback that reads it (or inline the value).
- readonly: use a different name (e.g. self.scene_time) instead of assigning
  the Manim-owned property.
- 2d/3d broadcast: make the numpy array 3D (append a 0 component) before
  combining it with a Manim point.
- closure: move the assignment of the referenced variable BEFORE the
  lambda/comprehension that reads it.
{three_d_closure_block}
Rules:

- Keep the scene simple.
- {obj_budget}
- Return ONLY complete Python code.
- Do NOT include reasoning or explanations.
- The class MUST be named GeneratedScene."""

        if repair_prompt is not None:
            _write(attempt_dir / "repair_prompt.txt", repair_prompt)
            code = clean_code(ask_coder_luna(repair_prompt, 0.2, three_d=three_d))
            _write(attempt_dir / "next_code.py", code)
            meta, has_meta = {}, False
            attempts.append(
                {
                    "attempt": attempt,
                    "stage": stage,
                    "requirements_pass": None,
                    "requirements_total": len(requirements),
                    "video_available": False,
                    "temporal_available": False,
                    "quality_total": None,
                }
            )
            continue

        # --- geometry + figures (pre-render hard blocking) ---
        if has_meta and meta:
            try:
                fig_info = render_figures.render_figures(meta, attempt_dir)
                code = render_figures.embed_figures(code, meta, fig_info)
                _write(attempt_dir / "code.py", code)
                _write(attempt_dir / "scene_meta.json", json.dumps(meta, indent=2))
                geometry_errors = geometry.validate(meta)
                hard = [e for e in geometry_errors if e["severity"] == "hard"]
                if hard:
                    print(
                        f"\n[GEOMETRY] {len(hard)} hard error(s) - advisory, "
                        "rendering anyway"
                    )
                    for e in hard:
                        print(f"  {e['object']} ({e['frames']}): {e['problem']}")
            except Exception as error:
                print(f"\n[FIGURE] error: {error}")
                stage = "figure_error_repair"
                repair_prompt = scene_meta.build_geometry_repair_prompt(
                    prompt, scene_plan, code,
                    [{"object": "figure", "frames": "all", "problem": str(error)}],
                )
                _write(attempt_dir / "repair_prompt.txt", repair_prompt)
                code, meta, has_meta = generate_repair(repair_prompt, three_d=three_d)
                _write(attempt_dir / "next_code.py", code)
                attempts.append(
                    {
                        "attempt": attempt,
                        "stage": stage,
                        "requirements_pass": None,
                        "requirements_total": len(requirements),
                        "video_available": False,
                        "temporal_available": False,
                        "quality_total": None,
                    }
                )
                continue
        else:
            _write(attempt_dir / "scene_meta.json", "{}")

        # --- render ---
        try:
            print("\n[4] Rendering...")
            video = render(
                code, attempt_dir, background_color=background_color
            )
        except subprocess.TimeoutExpired:
            print(f"\nRENDER TIMEOUT after {RENDER_TIMEOUT}s - scene too complex")
            stage = "timeout_repair"
            repair_prompt = _timeout_repair_prompt(prompt, code, scene_plan, three_d=three_d)
            _write(attempt_dir / "repair_prompt.txt", repair_prompt)
            code = clean_code(ask_coder_luna(repair_prompt, 0.2, three_d=three_d))
            _write(attempt_dir / "next_code.py", code)
            meta, has_meta = {}, False
            attempts.append(
                {
                    "attempt": attempt,
                    "stage": stage,
                    "requirements_pass": None,
                    "requirements_total": len(requirements),
                    "video_available": False,
                    "temporal_available": False,
                    "quality_total": None,
                }
            )
            continue
        except Exception as error:
            print(f"\nRENDER ERROR:\n{error}")
            stage = "render_error_repair"
            repair_prompt = _render_error_prompt(prompt, code, error, scene_plan, three_d=three_d)
            _write(attempt_dir / "repair_prompt.txt", repair_prompt)
            code = clean_code(ask_coder_luna(repair_prompt, 0.2, three_d=three_d))
            _write(attempt_dir / "next_code.py", code)
            meta, has_meta = {}, False
            attempts.append(
                {
                    "attempt": attempt,
                    "stage": stage,
                    "requirements_pass": None,
                    "requirements_total": len(requirements),
                    "video_available": False,
                    "temporal_available": False,
                    "quality_total": None,
                }
            )
            continue

        # --- frames + three evaluation branches ---
        print("\n[5] Extracting frames...")
        frames = extract_frames(
            video, attempt_dir / "frames", count=FRAME_SAMPLE_COUNT
        )
        frame_paths = [str(f) for f in frames]

        print("\n[6a] Frame branch (review_animation_v2)...")
        frame_result = review_animation_v2(
            prompt,
            requirements,
            frame_paths,
            code,
            previous_result,
            geometry=meta if (has_meta and meta) else None,
        )
        previous_result = best["result"] if best else frame_result
        _write(attempt_dir / "review_v2.json", json.dumps(frame_result, indent=2))

        print("\n[6b] Deterministic temporal analysis...")
        temporal_result = temporal.analyze(video)
        _write(attempt_dir / "temporal_analysis.json", json.dumps(temporal_result, indent=2))
        temporal_available = bool(temporal_result.get("available"))

        print("\n[6c] Video-level temporal evaluation...")
        frame_failed = frame_result.get("failed_ids", [])
        frame_total = (frame_result.get("visual_critique", {}) or {}).get("total")
        polish_needed = (
            not frame_failed
            and frame_total is not None
            and frame_total < POLISH_THRESHOLD
        )
        video_reason = _should_run_video_eval(
            frame_result,
            requirements,
            consume,
            attempt,
            force_video=(consume or polish_needed),
        )
        if video_reason:
            print(f"  running (reason: {video_reason})")
            video_result = video_eval.evaluate_video(video, requirements, prompt)
        else:
            print("  skipped - frame branch conclusive (no movement requirement in doubt)")
            video_result = {
                "available": False,
                "reason": "skipped: frame branch conclusive",
            }
        _write(attempt_dir / "review_video.json", json.dumps(video_result, indent=2))
        video_available = bool(video_result.get("available"))
        if not video_available:
            print(f"  video branch unavailable: {video_result.get('reason', '')}")

        print("\n[6d] Merging branches...")
        result = merge_evaluation.merge(
            frame_result, video_result, geometry_errors,
            meta if (has_meta and meta) else None,
            temporal_result, requirements, prompt,
        )
        _write(attempt_dir / "review.json", json.dumps(result, indent=2))

        for entry in result["requirements"]:
            status = "PASS" if entry.get("pass") is True else "FAIL"
            print(
                f"  {entry.get('id')}: {status} ({entry.get('confidence', '?')}) - "
                f"{entry.get('evidence', '')[:180]}"
            )

        quality = result["visual_critique"]
        print(
            f"  rubric total: {quality.get('total')}/30, "
            f"defects: {len(quality.get('observed_defects', []))}, "
            f"pacing: {quality.get('pacing', 'n/a')}"
        )

        attempts.append(
            {
                "attempt": attempt,
                "stage": stage,
                "requirements_pass": len(requirements) - len(result["failed_ids"]),
                "requirements_total": len(requirements),
                "video_available": video_available,
                "temporal_available": temporal_available,
                "quality_total": quality.get("total"),
            }
        )

        failed_ids = result["failed_ids"]
        quality_total = quality.get("total")
        req_pass = len(requirements) - len(failed_ids)

        # --- running best: adopt only if no previously-passing req regresses ---
        candidate_passing = {
            e["id"] for e in result["requirements"] if e.get("pass") is True
        }
        if best is None:
            best = {
                "code": code,
                "meta": meta,
                "has_meta": has_meta,
                "result": result,
                "req_pass": req_pass,
                "quality": quality_total,
                "attempt": attempt,
                "passing": candidate_passing,
            }
        else:
            regressed = best["passing"] - candidate_passing
            better = (
                req_pass > best["req_pass"]
                or (
                    req_pass == best["req_pass"]
                    and (quality_total or 0) >= (best["quality"] or 0)
                )
            )
            if not regressed and better:
                best = {
                    "code": code,
                    "meta": meta,
                    "has_meta": has_meta,
                    "result": result,
                    "req_pass": req_pass,
                    "quality": quality_total,
                    "attempt": attempt,
                    "passing": candidate_passing,
                }

        # Enrich a deep copy for the repair/polish prompt only; review.json stays canonical.
        enriched = enrich_result(
            result,
            requirements,
            meta if (has_meta and meta) else None,
            temporal_result,
        )

        if failed_ids and attempt < 5:
            print(f"\n[REPAIR] Failed requirements: {', '.join(failed_ids)}")
            repair_prompt = scene_meta.build_repair_prompt(
                prompt, scene_plan, requirements, best["code"], enriched,
                protected_ids=sorted(best["passing"]),
            )
        elif consume and attempt < 5:
            print(
                f"\n[QUALITY] All requirements pass ({quality_total}/30). "
                f"Improving visual quality..."
            )
            polish_done = True
            repair_prompt = scene_meta.build_polish_prompt(
                prompt, scene_plan, requirements, best["code"], enriched,
                POLISH_THRESHOLD,
            )
        elif (
            (quality_total or 0) < POLISH_THRESHOLD
            and attempt < 5
            and not polish_done
        ):
            print(
                f"\n[POLISH] All requirements pass but rubric {quality_total}/30 "
                f"< {POLISH_THRESHOLD}. Running one focused polish pass..."
            )
            polish_done = True
            repair_prompt = scene_meta.build_polish_prompt(
                prompt, scene_plan, requirements, best["code"], enriched,
                POLISH_THRESHOLD,
            )
        else:
            break

        _write(attempt_dir / "repair_prompt.txt", repair_prompt)
        code, meta, has_meta = generate_repair(repair_prompt, three_d=three_d)
        _write(attempt_dir / "next_code.py", code)
        print(f"  repaired incrementally, scene_meta present: {has_meta}")
        continue

    else:
        print("\nAll attempts exhausted.")

    print_table(out, attempts)
    summary = {
        "slug": slug,
        "best_attempt": best["attempt"] if best else None,
        "best_req_pass": best["req_pass"] if best else None,
        "best_quality": best["quality"] if best else None,
        "attempts": [
            {**a, "quality": None} for a in attempts
        ],
    }
    _write(out / "summary.json", json.dumps(summary, indent=2))
    if best is not None:
        _write(out / "best_code.py", best["code"])
        _write(out / "best_scene_meta.json", json.dumps(best.get("meta") or {}, indent=2))


if __name__ == "__main__":
    consume = "--consume" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    slug = args[0] if args else "projectile_motion"
    if slug not in PROMPTS:
        print(f"Unknown slug: {slug}. Choices: {', '.join(PROMPTS)}")
        sys.exit(1)
    run(slug, consume=consume)
