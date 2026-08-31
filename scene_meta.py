"""scene_meta contract: codegen prompts, meta-aware model calls, and
extraction of scene.py + scene_meta.json from the model reply.

Recreates the pipeline's codegen call path (pipeline_deepseek.py is untouched)
but with a system prompt that allows returning scene_meta alongside the code.
"""

import json
import re

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI

import metrics
import pipeline_deepseek as pipeline
from local_agent import clean_code

META_MARKER = "SCENE_META"

META_SYSTEM_FOOTER = """After the scene code, on its own line, write the single word SCENE_META,
then on the next line the scene_meta JSON exactly as described in the user message.
Return ONLY the code, then SCENE_META, then the JSON. No other text.
"""

CODEGEN_META_SYSTEM_PROMPT = pipeline.SYSTEM_PROMPT + """
""" + META_SYSTEM_FOOTER


def codegen_meta_system_prompt(three_d: bool = False) -> str:
    """System prompt for codegen+meta, matched to scene dimensionality."""
    return pipeline.system_prompt(three_d) + """
""" + META_SYSTEM_FOOTER


def is_3d(scene_plan) -> bool:
    """True when the scene plan requests genuinely 3D content.

    Trusts the planner's "three_d" flag first; falls back to conservative
    keyword detection on the serialized plan so older plans still route
    correctly. Kept conservative: generic words like 'camera' are NOT enough.
    """
    if not scene_plan:
        return False
    inner = scene_plan.get("scene_plan") or scene_plan
    if inner.get("three_d"):
        return True
    text = json.dumps(scene_plan).lower()
    hints = ("\"three_d\": true", "3d ", " three-dimensional", " three dimensional",
             "orbit", "in 3d", "sphere", "spatial depth", " volumetric")
    return any(h in text for h in hints)


META_FOOTER = """
OUTPUT FORMAT - return BOTH the scene code and the scene metadata:

1) The complete Manim scene (class GeneratedScene).

2) On its own line after the code, write the single word: SCENE_META

3) On the next line, the scene_meta JSON (valid JSON, no markdown fences).

scene_meta schema (coordinates in Manim scene units; frame is 14.222 x 8.0):

{
  "objects": [
    {"id": "vx_label", "kind": "text", "center": [x, y],
     "width": 0.8, "height": 0.3, "color": "ORANGE", "frames": "2-10"},
    {"id": "ball", "kind": "dot", "center": [x, y], "radius": 0.15,
     "color": "BLUE", "frames": "all",
     "path": [[x0, y0], [x1, y1]]},
    {"id": "velocity_arrow", "kind": "arrow", "start": [x, y], "end": [x, y],
     "color": "RED", "frames": "2-10"}
  ],
  "figures": [
    {"id": "traj", "code": "fig, ax = plt.subplots(); ax.plot(...)",
     "center": [0, 0], "width": 4.0}
  ]
}

Rules:
- Declare every visible label, arrow, circle and distinct object.
- kind is one of: text, dot/circle/ball, arrow, rect, image.
- Arrows use "start"/"end". Text/circles use "center" (+ width/height or radius).
- "frames" is the frame range where the object is visible ("all" if always).
- For a moving object, add "path" with at least two positions.
- matplotlib figures: put the drawing code in "figures" (must define fig and ax;
  Agg backend, executed separately). Embed in the scene as
  ImageMobject("figures/<id>.png").
"""


def ask_coder_meta(prompt: str, temperature: float = 0.2, three_d: bool = False) -> str:
    """Generate Manim code + scene_meta with the pipeline's fallback chain."""
    api_key = pipeline.DEEPSEEK_API_KEY
    system = codegen_meta_system_prompt(three_d)

    for model_name in pipeline.FALLBACK_MODELS:
        client = OpenAI(
            api_key=api_key,
            base_url=pipeline.DEEPSEEK_BASE_URL,
            timeout=pipeline.REQUEST_TIMEOUT,
            max_retries=0,
        )
        print(f"  [CODEGEN] Trying {model_name}...", flush=True)
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=4096,
            )
            print(f"  [CODEGEN] {model_name} responded OK")
            usage = response.usage
            metrics.record_llm(
                model_name,
                prompt,
                {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(usage, "completion_tokens", 0),
                },
            )
            return response.choices[0].message.content
        except (
            APITimeoutError,
            APIConnectionError,
            InternalServerError,
        ) as err:
            print(
                f"  [CODEGEN] {model_name} failed "
                f"({type(err).__name__}), trying next..."
            )
            continue

    raise RuntimeError(
        f"All models unreachable. Tried: {', '.join(pipeline.FALLBACK_MODELS)}"
    )


def extract_scene_meta(reply: str):
    """Split the model reply into (scene_code, scene_meta_dict, meta_present)."""
    idx = reply.find(META_MARKER)
    if idx == -1:
        return clean_code(reply), {}, False

    scene_part = reply[:idx]
    meta_text = reply[idx + len(META_MARKER):]

    start = meta_text.find("{")
    end = meta_text.rfind("}")
    meta = {}
    if start != -1 and end != -1:
        try:
            parsed = json.loads(meta_text[start:end + 1])
            if isinstance(parsed, dict):
                meta = parsed
        except json.JSONDecodeError:
            meta = {}

    return clean_code(scene_part), meta, True


CODING_DIRECTIVES = """
CODING DIRECTIVES - follow exactly:

- OBJECT BUDGET: max 15 individual objects total (mobjects shown on screen).
- CONSTANTS: declare every color and size once as a named constant at the top
  of construct() (e.g. AXIS_COLOR = GREY_B, BALL_RADIUS = 0.15, LABEL_SIZE = 30),
  then reuse them. Never hardcode a color/size more than once.
- TIMELINE: lay the animation out as a beat-by-beat timeline derived from the
  scene plan sequence. Explicitly define what is on screen at each phase:
  * START (first 1-2 seconds): the setup objects and their positions.
  * MIDDLE (the main action, apex/transition): what moves or changes and when.
  * FINAL 2 SECONDS: exactly which objects remain visible and where - every
    required element must still be on screen at the end.
- DURATION: total animation must be under 8 seconds. Use self.wait() sparingly.
- PROGRESSIVE REVEAL: introduce objects in the order the scene plan sequence
  lists them; nothing required later should be visible from the first frame.
- MOTION: never call self.play() inside a loop. Precompute paths and use
  MoveAlongPath; at most 2 always_redraw mobjects for anything that must
  track a moving object.
"""

CODING_DIRECTIVES_3D = """
CODING DIRECTIVES - follow exactly:

- OBJECT BUDGET: up to 40 individual objects total when the request needs many
  identical objects (e.g. 24 electrons); otherwise keep it minimal.
- CONSTANTS: declare every color and size once as a named constant at the top
  of construct() (e.g. NUCLEUS_COLOR = ORANGE, ELECTRON_RADIUS = 0.05), then
  reuse them. Never hardcode a color/size more than once.
- TIMELINE: lay the animation out as a beat-by-beat timeline derived from the
  scene plan sequence. Explicitly define what is on screen at each phase:
  * START (first 1-2 seconds): the setup objects and their positions.
  * MIDDLE (the main action, apex/transition): what moves or changes and when.
  * FINAL 2 SECONDS: exactly which objects remain visible and where - every
    required element must still be on screen at the end.
- DURATION: total animation must be under 8 seconds. Use self.wait() sparingly.
- PROGRESSIVE REVEAL: introduce objects in the order the scene plan sequence
  lists them; nothing required later should be visible from the first frame.
- MOTION: never call self.play() inside a loop. Precompute each orbit/path and
  animate each object ONCE with MoveAlongPath; a few always_redraw/updater
  mobjects are fine for objects that must track motion.
- 3D: you MAY use ThreeDScene, ThreeDAxes, Sphere, Cylinder, Torus, Surface,
  Dot3D and camera methods (set_camera_orientation / move_camera /
  begin_ambient_camera_rotation) exactly when the scene plan or prompt
  requests spatial depth or an orbiting camera. Set the background to match
  the request (e.g. self.camera.background_color = BLACK).
- 3D COLOR PITFALL: Manim's surface lighting tints solids toward blue/white
  and hides declared colors (a "warm orange/gold" Sphere can render cyan).
  Keep colors accurate: after creating each colored 3D solid, call
  mob.set_flat_shading(True) so its declared fill color renders faithfully.
- 3D VISIBILITY: tiny particles are hard to see in a 480p preview - give
  small glowing particles (electrons) a radius >= 0.09 and a faint, larger
  translucent halo so they read as bright dots; space concentric shells by
  >= 0.9 scene units so their different radii are obvious.
"""


def coding_directives(three_d: bool = False) -> str:
    return CODING_DIRECTIVES_3D if three_d else CODING_DIRECTIVES


def meta_footer(three_d: bool = False) -> str:
    if not three_d:
        return META_FOOTER
    return META_FOOTER + """
For 3D/ThreeDScene scenes the scene_meta is OPTIONAL and should be kept
minimal: you may emit a scene_meta with empty objects ({"objects": []}) to
skip the 2D frame-bounds validation. Do NOT fabricate 2D bounding boxes or
x/y centers for genuinely 3D objects - those checks only apply to 2D scenes.
"""


def build_codegen_prompt(prompt: str, scene_plan: dict) -> str:
    three_d = is_3d(scene_plan)
    bg_line = ""
    if re.search(
        r"\bblack\s*(?:background|screen|backdrop)\b|\bdark\s*(?:background|screen)\b",
        prompt,
        re.IGNORECASE,
    ):
        bg_line = (
            "\nBackground (enforced by the renderer, do NOT fight it): the "
            "final video renders on a BLACK background. Choose every element's "
            "color to be clearly visible against pure black (no near-black "
            "grays for objects that must be seen), and set "
            "self.camera.background_color = BLACK at the very start of "
            "construct so previews match.\n"
        )
    return f"""{prompt}

Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}
{bg_line}{coding_directives(three_d)}
{meta_footer(three_d)}
"""


def build_repair_prompt(
    prompt: str,
    scene_plan: dict,
    requirements: list[dict],
    code: str,
    result: dict,
    protected_ids: list[str] | None = None,
) -> str:
    checklist = "\n".join(
        f"{r['id']}: {r['description']}" for r in requirements
    )
    report = "\n".join(result["repair_instructions"])
    failed = ", ".join(result["failed_ids"])
    protected = (
        f"\nPROTECTED (these requirements passed in the best attempt and must "
        f"NOT regress): {', '.join(protected_ids)}\n"
        if protected_ids
        else ""
    )
    three_d = is_3d(scene_plan)
    if three_d:
        mode_line = (
            "3D scene: you MAY use ThreeDScene, ThreeDAxes, Sphere, Cylinder, Torus, "
            "Surface, Dot3D and camera methods (set_camera_orientation / move_camera / "
            "begin_ambient_camera_rotation) to satisfy the requested depth."
        )
        budget = "max 40 individual objects"
    else:
        mode_line = "Stay strictly 2D: no camera methods, no 3D objects."
        budget = "max 15 individual objects"

    return f"""{prompt}
Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}

Requirements checklist:

{checklist}

Previous code:

{code}

Evaluation of the rendered animation (structured):

{report}

FAILED requirements to fix: {failed}
{protected}
Rules:
- Edit the code above in place. Modify ONLY the failing parts.
- Preserve every PRESERVE item, every PROTECTED requirement, and every
  currently-passing requirement exactly as-is.
- Fix ONLY the listed failures and DEFECT items.
- Apply high/medium IMPROVE suggestions only if they do not break a passing requirement.
- You MAY use TracedPath (max 2) for motion trails.
- {mode_line}
- Keep the scene simple: {budget}, animation under 10 seconds.
{meta_footer(three_d)}
"""


def build_geometry_repair_prompt(
    prompt: str,
    scene_plan: dict,
    code: str,
    hard_errors: list[dict],
) -> str:
    lines = "\n".join(
        f"- '{e['object']}' (frames {e['frames']}): {e['problem']}"
        for e in hard_errors
    )
    return f"""{prompt}
Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}

Previous code:

{code}

GEOMETRY VALIDATION FAILED - the scene_meta coordinates are invalid:

{lines}

The frame is 14.222 x 8.0 scene units: x in [-7.111, 7.111], y in [-4.0, 4.0].
With the 0.5-unit safety margin, every declared bbox MUST satisfy:
  -6.6 <= x_min and x_max <= 6.6     and    -3.5 <= y_min and y_max <= 3.5

The most common failure is the Axes: declaring an extent wider than the frame
or offset to one side (e.g. x from -7.5 to 1.5 goes past the left edge).
For Axes, set x_length and y_length (or scale/place the object) so its full
extent stays inside x [-6.6, 6.6] x [-3.5, 3.5], and declare that extent in
scene_meta.

Fix the coordinates in scene_meta so every declared object fits inside the
frame. Do not change the animation narrative; only correct positions and sizes.
{META_FOOTER}
"""


def build_loop_repair_prompt(
    prompt: str,
    scene_plan: dict,
    code: str,
    loop_errors: list[str],
) -> str:
    lines = "\n".join(f"- {e}" for e in loop_errors)
    return f"""{prompt}
Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}

Previous code:

{code}

STATIC PRECHECK REJECTED THE CODE - a for/while loop calls self.play() or
builds heavy mobjects per iteration, which can exceed the 120s render
timeout:

{lines}

Rewrite the animation so it NEVER calls self.play() inside a loop:

- Precompute the full motion path into a single VMobject (or list of
  points) BEFORE the animation starts.
- Animate the moving object ONCE with MoveAlongPath(mobject, path).
- For anything that must track the moving object (labels, arrows, velocity
  components), use at most 2 always_redraw mobjects - never self.play per
  frame.
- Construct each mobject at most once, outside any loop.
- Keep total animation time under 10 seconds.

The trajectory precomputation in the previous code is CORRECT - keep it.
Only the loop that moves the ball and rebuilds the arrows must be replaced.

Correct pattern for moving the ball (no loop):

    traj = VMobject(color=TRAJ_COLOR, stroke_width=3)
    traj.set_points_smoothly(points)   # 'points' already precomputed

    ball = Dot(traj.get_start(), color=BALL_COLOR, radius=0.12)
    self.play(Create(traj), run_time=1.5)
    self.play(MoveAlongPath(ball, traj), run_time=3.0, rate_func=linear)
    self.wait(1.0)

For arrows/labels that must follow the ball, do NOT rebuild them per frame.
Either build a few fixed states (launch / apex / descent) and Transform
between them, or attach at most 2 always_redraw mobjects:

    vx_arrow = always_redraw(
        lambda: Arrow(ball.get_center(), ball.get_center() + RIGHT * 0.8,
                      color=VX_COLOR)
    )

Return ONLY complete Python code.
The class MUST be named GeneratedScene.
"""


def build_method_repair_prompt(
    prompt: str,
    scene_plan: dict,
    code: str,
    method_errors: list[str],
) -> str:
    lines = "\n".join(f"- {e}" for e in method_errors)
    return f"""{prompt}
Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}

Previous code:

{code}

STATIC PRECHECK REJECTED THE CODE - it calls methods that do NOT exist in
Manim Community Edition:

{lines}

Calling a nonexistent method raises an exception inside construct(), and
Manim's error-page render hangs until the 120s render timeout, wasting the
attempt.

Fix EVERY listed method call using only real Manim CE APIs. The most common
one: 'set_points_smooth' does not exist - the real method is
'set_points_smoothly(points)'. Do not rename methods or invent arguments;
verify each against real Manim CE documentation.

Return ONLY complete Python code.
The class MUST be named GeneratedScene.
"""


def build_polish_prompt(
    prompt: str,
    scene_plan: dict,
    requirements: list[dict],
    code: str,
    result: dict,
    threshold: int,
) -> str:
    checklist = "\n".join(
        f"{r['id']}: {r['description']}" for r in requirements
    )
    critique = result.get("visual_critique", {}) or {}
    defects = critique.get("observed_defects", []) or []
    defects_lines = "\n".join(
        f"- '{d.get('object')}' in {d.get('frames')}: {d.get('problem')}"
        for d in defects
    ) or "- none reported"
    improvements = [
        i for i in (critique.get("improvements", []) or [])
        if i.get("priority") in ("high", "medium")
    ]
    improvements_lines = "\n".join(
        f"- ({i.get('priority')}, {i.get('area')}): {i.get('suggestion')}"
        for i in improvements
    ) or "- none reported"
    quality_total = critique.get("total")

    return f"""{prompt}
Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}

Best previous code (keep everything that works):

{code}

POLISH PASS - all requirements currently PASS but the visual/temporal
rubric is below target ({quality_total}/30, target {threshold}/30).

Change ONLY the specific defects and pacing items listed below. Do NOT
restructure the scene, do NOT reorder the sequence, and do NOT change any
color, size, or position that is not listed.

Observed defects:

{defects_lines}

Pacing: {critique.get('pacing', 'n/a')}

High/medium improvements (apply only if they do not alter required content):

{improvements_lines}

Requirements (ALL CURRENTLY PASSING - do not break any):

{checklist}

Return ONLY complete Python code and scene_meta.
The class MUST be named GeneratedScene.
{meta_footer(is_3d(scene_plan))}
"""
