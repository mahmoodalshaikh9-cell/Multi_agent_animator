from pathlib import Path
from extract_frame import extract_frames
from local_agent import clean_code, extract_requirements, find_unknown_symbols, planning
from vision import review_animation
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI

import ast
import json
import subprocess
import sys
import time
import shutil

import secrets_loader

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
openrouter_BASE_URL = "https://openrouter.ai/api/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

DEEPSEEK_API_KEY = secrets_loader.get("deepseek", "DEEPSEEK_API_KEY")

REQUEST_TIMEOUT = 60
RENDER_TIMEOUT = 120

FALLBACK_MODELS = [
    "deepseek-chat",
]


SYSTEM_PROMPT = """\
You are a Manim Community Edition coding agent.

Return ONLY valid Python source code. No analysis, no reasoning, no Markdown.

SCENE RULES — follow exactly:
- Class must be: class GeneratedScene(Scene):
- 2D ONLY. NO 3D objects, NO ThreeDScene, NO camera manipulation.
- NEVER use: Surface, Sphere, Torus, Cube, Cylinder, Cone, Prism, Dot3D
- NEVER use: set_camera_orientation, move_camera, self.camera.set_*
- NEVER use: config.pixel_width, config.pixel_height, config.frame_rate
- NEVER pass method references to self.play(). Use obj.animate.method().
  WRONG: self.play(obj.rotate, PI)
  RIGHT: self.play(obj.animate.rotate(PI))
- NEVER call self.play() inside a for/while loop. Continuous motion is done
  by precomputing a VMobject path and animating ONCE with MoveAlongPath;
  anything that must track a moving object uses at most 2 always_redraw
  mobjects.

ALLOWED mobjects:
Circle, Square, Rectangle, Ellipse, Dot, Line, Arrow, Text, Polygon, Arc, NumberLine, Axes, VGroup

ALLOWED animations:
self.play(Create(...), Write(...), FadeIn(...), FadeOut(...), Transform(...), ReplacementTransform(...))

ALLOWED methods:
mobject.animate.shift / scale / move_to / set_color / rotate / set_opacity
mobject.to_edge(UP), mobject.next_to(other, DOWN)
self.wait()

EXAMPLE — this is the exact style expected:

from manim import *

class GeneratedScene(Scene):
    def construct(self):
        title = Text("Hello World", font_size=48).to_edge(UP)
        circle = Circle(color=BLUE, radius=1)
        square = Square(color=RED, side_length=2)

        self.play(Write(title))
        self.play(Create(circle))
        self.wait(0.5)
        self.play(Transform(circle, square))
        self.wait(1)
        self.play(FadeOut(circle), FadeOut(title))

Return ONLY the code. The output must be directly saveable as scene.py.
"""

# 3D-scene variant: relaxes the 2D-only rules when the scene plan requests
# spatial depth / volumetric objects / orbiting or camera-moved renders.
SYSTEM_PROMPT_3D = """\
You are a Manim Community Edition coding agent.

Return ONLY valid Python source code. No analysis, no reasoning, no Markdown.

SCENE RULES — follow exactly:
- Class must be: class GeneratedScene(Scene): — or
  class GeneratedScene(ThreeDScene): when the request needs spatial depth,
  volumetric shapes, orbital planes, or an orbiting camera.
- 3D is ALLOWED and encouraged when requested: you MAY use ThreeDScene,
  ThreeDAxes, Sphere, Cylinder, Torus, Surface, Dot3D, and camera controls
  (self.set_camera_orientation(phi=..., theta=..., zoom=...),
   self.move_camera(...), self.begin_ambient_camera_rotation(...)).
- 2D scenes remain fully supported (Scene, Circle, Rectangle, ...). Only go
  3D when the request really calls for it.
- Set the background to match the request (e.g. self.camera.background_color
  = BLACK for a black-background render).
- NEVER pass method references to self.play(). Use obj.animate.method().
  WRONG: self.play(obj.rotate, PI)
  RIGHT: self.play(obj.animate.rotate(PI))
- NEVER call self.play() inside a for/while loop. Animate each object ONCE
  along a precomputed path (MoveAlongPath for 2D; for 3D orbit motion,
  precompute the orbit path and MoveAlongPath once, or use a few
  always_redraw/updater mobjects — never one self.play per electron).
- Object budget: up to 40 individual mobjects when the request needs many
  identical objects (e.g. 24 electrons); keep it minimal otherwise.
- Keep the total animation under 8-10 seconds and everything inside frame.

Return ONLY the code. The output must be directly saveable as scene.py.
"""


def system_prompt(three_d: bool = False) -> str:
    """Pick the codegen system prompt for the scene's dimensionality."""
    return SYSTEM_PROMPT_3D if three_d else SYSTEM_PROMPT


def _load_api_key() -> str:
    """Load DeepSeek API key."""
    return DEEPSEEK_API_KEY


def validate_python(code: str) -> tuple[bool, str]:
    """Check that generated code is valid Python before rendering."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as error:
        return False, (
            f"SyntaxError: {error.msg} "
            f"(line {error.lineno}, column {error.offset})"
        )


def ask_coder(prompt: str, temperature: float = 0.2) -> str:
    """Generate Manim code with model fallback chain."""
    api_key = _load_api_key()

    for model_name in FALLBACK_MODELS:
        client = OpenAI(
            api_key=api_key,
            base_url=DEEPSEEK_BASE_URL,
            timeout=REQUEST_TIMEOUT,
            max_retries=0,
        )

        print(f"  [CODEGEN] Trying {model_name}...", flush=True)

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=4096,
            )

            print(f"  [CODEGEN] {model_name} responded OK")

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
        f"All models unreachable. Tried: {', '.join(FALLBACK_MODELS)}"
    )


def find_failed_ids(
    evaluation: dict,
    requirements: list[dict],
) -> list[str]:
    answered = {
        entry.get("id"): entry
        for entry in evaluation.get("requirements", [])
    }

    failed = []

    for requirement in requirements:
        if not requirement.get("required", True):
            continue

        entry = answered.get(requirement["id"])

        if entry is None or entry.get("pass") is not True:
            failed.append(requirement["id"])

    return failed


def build_repair_report(
    evaluation: dict,
    requirements: list[dict],
) -> str:
    descriptions = {
        r["id"]: r["description"]
        for r in requirements
    }

    lines = []

    for entry in evaluation.get("requirements", []):
        if (
            entry.get("pass") is not True
            and entry.get("id") in descriptions
        ):
            lines.append(
                f"{entry['id']} FAILED: "
                f"{descriptions[entry['id']]}"
            )
            lines.append(
                f"Evidence: "
                f"{entry.get('evidence', 'none given')}"
            )

    for instruction in evaluation.get("repair_instructions", []):
        lines.append(f"REPAIR: {instruction}")

    return "\n".join(lines)


def render(code: str, run_dir: Path, background_color: str = "WHITE") -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)

    scene_file = run_dir / "scene.py"
    scene_file.write_text(code, encoding="utf-8")

    config_file = run_dir / "manim.cfg"

    config_file.write_text(
        f"[CLI]\nbackground_color = {background_color}\n",
        encoding="utf-8",
    )

    dest = run_dir / "GeneratedScene.mp4"
    if dest.exists():
        dest.unlink()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "manim",
            "-ql",
            "-c",
            str(config_file),
            "--media_dir",
            str(run_dir / "media"),
            str(scene_file),
            "GeneratedScene",
        ],
        capture_output=True,
        text=True,
        timeout=RENDER_TIMEOUT,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr[-4000:])

    videos = list(run_dir.rglob("GeneratedScene.mp4"))

    if not videos:
        raise RuntimeError("No video produced.")
    shutil.copy2(videos[0], dest)

    return dest



def _syntax_repair_prompt(
    prompt: str,
    code: str,
    error: str,
      
    scene_plan: dict,

) -> str:
    return f"""Original request:

{prompt}

Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}

Previous code:

{code}

Python syntax validation failed:

{error}

Fix the syntax error.

IMPORTANT:
- Return ONLY complete Python code.
- Do NOT include analysis.
- Do NOT include reasoning.
- Do NOT include Markdown fences.
- Do NOT include explanations.
- The first line must be: from manim import *
- The class MUST be named GeneratedScene.
- Do not leave any natural-language reasoning inside the Python file.
- restructre the prompt into coding agent langauges

Return ONLY the corrected code.
"""


def _timeout_repair_prompt(
    prompt: str,
    code: str,
    scene_plan: dict,
    three_d: bool = False,
) -> str:
    if three_d:
        budget_line = "- Reduce to at most 20 individual objects total."
        particle_line = "- Use Dot or a small Sphere for particles as needed."
        dim_line = (
            "- Keep 3D if the plan requires it (ThreeDScene, camera), but "
            "simplify call count and run time."
        )
    else:
        budget_line = "- Reduce to at most 10-12 individual objects total."
        particle_line = "- Use Dot for particles, never Sphere or other 3D objects."
        dim_line = "- Stay strictly 2D: no camera methods, no ThreeDScene, no 3D objects."
    return f"""Original request:

{prompt}

Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}

Previous code:

{code}

The render TIMED OUT after {RENDER_TIMEOUT} seconds.

The scene is too complex for preview rendering (a 120s timeout also happens
when construct() raises on a nonexistent Manim method and the error-page
render hangs - double-check every method name, e.g. set_points_smoothly,
NOT set_points_smooth).

You MUST simplify drastically:

{budget_line}
{particle_line}
- Keep total animation time under 8 seconds.
{dim_line}
- Remove heavy updaters.
- Remove per-frame computations.
- Never call a method that does not exist in Manim CE.

Return ONLY complete Python code.
The class MUST be named GeneratedScene.
Do NOT include reasoning or explanations.
"""


def _render_error_prompt(
    prompt: str,
    code: str,
    error: Exception,
    scene_plan: dict,
    three_d: bool = False,
) -> str:
    if three_d:
        mode_rules = (
            "- If the scene is 3D/ThreeDScene, KEEP the 3D structure and camera "
            "movement and fix ONLY the failing API usage - do not flatten it to 2D."
        )
        budget_line = "- Keep max 40 individual objects."
    else:
        mode_rules = "- Stay strictly 2D: never use camera methods or ThreeDScene."
        budget_line = "- Keep max 15 individual objects."
    return f"""Original request:

{prompt}

Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}

Previous code:

{code}

Manim error:

{error}

Fix the code.

IMPORTANT:

- Find the line named in the traceback and fix it.
- Do NOT repeat the same code unchanged.
{mode_rules}
- NEVER assign self.camera.
- NEVER instantiate any camera inside construct().
- NEVER use BackgroundRectangle(self.camera, ...).
- NEVER use MoveAlongPath as an updater.
- NEVER use self.camera.animate.
- NEVER call move_to(radius=...).
- You MAY use TracedPath, max 2.
{budget_line}
- Keep animation under 10 seconds.
- Use simple, well-known Manim CE APIs.
- Return ONLY complete Python code.
- Do NOT include analysis.
- Do NOT include reasoning.
- Do NOT include Markdown.
- The class MUST be named GeneratedScene.
"""


def main():
    with open("prompt.txt", "r", encoding="utf-8") as f:
        prompt = f.read().strip()

    run_id = str(int(time.time()))

    base_dir = (
        Path(__file__).parent
        / "runs"
        / run_id
    )

    print(f"\nRun directory: {base_dir}")
    print(f"Models: {' -> '.join(FALLBACK_MODELS)}")
    print(
        f"Preview: 480p 15fps, "
        f"render timeout: {RENDER_TIMEOUT}s"
    )

    print("\n[1] Extracting requirements...")

    requirements = extract_requirements(prompt)

    # EXPORT_KEYWORDS = {
    #     "8k",
    #     "8 k",
    #     "60fps",
    #     "60 fps",
    #     "4k",
    #     "4 k",
    #     "resolution",
    #     "frame rate",
    # }

    for requirement in requirements:
        if requirement.get("required", True):
            print(
                f"  {requirement['id']} "
                f"({requirement['type']}): "
                f"{requirement['description']}"
            )

    print("\n[2] Planning scene...")

    scene_plan = planning(prompt, requirements)

    print("\n[3] Generating code...")

    code = clean_code(
        ask_coder(
            f"""{prompt}

Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}
"""
        )
    )

    previous_result = None

    pipeline_start = time.time()
    MAX_PIPELINE_TIME = 1200

    for attempt in range(6):
        elapsed = time.time() - pipeline_start

        if elapsed > MAX_PIPELINE_TIME:
            print(
                f"\nPipeline time limit reached "
                f"({MAX_PIPELINE_TIME}s). Stopping."
            )
            break

        print(f"\n=== ATTEMPT {attempt + 1} ===")

        print(
            code[:500]
            + ("..." if len(code) > 500 else "")
        )

        # ---------------------------------------------------------
        # NEW: validate Python BEFORE running Manim
        # ---------------------------------------------------------
        valid, syntax_error = validate_python(code)

        if not valid:
            print(
                f"\n[VALIDATION] Invalid Python: "
                f"{syntax_error}"
            )

            code = clean_code(
                ask_coder(
                    _syntax_repair_prompt(
                        prompt,
                        code,
                        syntax_error,
                        scene_plan,
                    ),
                    0.2,
                )
            )

            continue

        unknown_symbols = find_unknown_symbols(code)

        if unknown_symbols:
            print(
                f"\n[VALIDATION] Unknown symbols: "
                f"{', '.join(unknown_symbols)}"
            )

            code = clean_code(
                ask_coder(
                    f"""Original request:

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
- Max 15 individual objects total.
- Return ONLY complete Python code.
- Do NOT include reasoning or explanations.
- The class MUST be named GeneratedScene.""",
                    0.2,
                )
            )

            continue

        try:
            print("\n[4] Rendering...")

            video = render(
                code,
                base_dir / f"attempt_{attempt}",
            )

        except subprocess.TimeoutExpired:
            print(
                f"\nRENDER TIMEOUT after "
                f"{RENDER_TIMEOUT}s — scene too complex"
            )

            code = clean_code(
                ask_coder(
                    _timeout_repair_prompt(
                        prompt,
                        code,
                        scene_plan,
                    ),
                    0.2,
                )
            )

            continue

        except Exception as error:
            print(f"\nRENDER ERROR:\n{error}")

            code = clean_code(
                ask_coder(
                    _render_error_prompt(
                        prompt,
                        code,
                        error,
                        scene_plan,
                    ),
                    0.2,
                )
            )

            continue

        print("\n[5] Extracting frames...")

        frames = extract_frames(
            video,
            base_dir
            / f"attempt_{attempt}"
            / "frames",
        )

        print("\n[6] Evaluating requirements...")

        result = review_animation(
            prompt,
            requirements,
            [str(frame) for frame in frames],
            previous_result,
        )

        previous_result = result

        print("\nPER-REQUIREMENT RESULTS:")

        for entry in result.get("requirements", []):
            status = (
                "PASS"
                if entry.get("pass") is True
                else "FAIL"
            )

            confidence = entry.get("confidence", "?")

            print(
                f"  {entry.get('id')}: "
                f"{status} ({confidence}) - "
                f"{entry.get('evidence', '')}"
            )

        failed_ids = find_failed_ids(
            result,
            requirements,
        )

        
        if failed_ids and attempt < 5:
            print(
                f"\n[REPAIR] Failed requirements: "
                f"{', '.join(failed_ids)}"
            )

            checklist = "\n".join(
                f"{r['id']}: {r['description']}"
                for r in requirements
            )

            code = clean_code(
                ask_coder(
                    f"""{prompt}
Scene plan (implement this exactly):

{json.dumps(scene_plan, indent=2)}


Requirements checklist:

{checklist}

Previous code:

{code}

Evaluation of the rendered animation:

{build_repair_report(result, requirements)}

Fix ONLY the listed failures.

You MAY use TracedPath (max 2) for motion trails.
Stay strictly 2D: no camera methods, no 3D objects.

Keep the scene simple:
- max 15 individual objects
- animation under 10 seconds

Return ONLY complete Python code.
Do NOT include analysis.
Do NOT include reasoning.
Do NOT include Markdown.
The class MUST be named GeneratedScene.""",
                    0.2,
                )
            )

            continue

        break

    else:
        print("\nAll attempts exhausted.")


if __name__ == "__main__":
    main()