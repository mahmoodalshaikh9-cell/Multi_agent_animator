from pathlib import Path
from extract_frame import extract_frames
from local_agent import ask_coder, clean_code, extract_requirements
from vision import review_animation
import subprocess
import sys
import time


def find_failed_ids(evaluation: dict, requirements: list[dict]) -> list[str]:
    """Conservative overall verdict: every required requirement must be explicitly passed.

    A requirement the evaluator forgot to answer counts as failed.
    """
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


def build_repair_report(evaluation: dict, requirements: list[dict]) -> str:
    """Turn failed requirement results into a concrete report for the coding agent."""
    descriptions = {r["id"]: r["description"] for r in requirements}

    lines = []

    for entry in evaluation.get("requirements", []):
        if entry.get("pass") is not True and entry.get("id") in descriptions:
            lines.append(f"{entry['id']} FAILED: {descriptions[entry['id']]}")
            lines.append(f"Evidence: {entry.get('evidence', 'none given')}")

    for instruction in evaluation.get("repair_instructions", []):
        lines.append(f"REPAIR: {instruction}")

    return "\n".join(lines)


def render(code: str, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)

    scene_file = run_dir / "scene.py"
    scene_file.write_text(code, encoding="utf-8")

    # This Manim install defaults to a black background, which the vision
    # model cannot evaluate properly. Manim 0.19 has no CLI flag for this
    # anymore, so force white through a small per-run config file.
    config_file = run_dir / "manim.cfg"
    config_file.write_text(
        "[CLI]\nbackground_color = WHITE\n",
        encoding="utf-8",
    )

    result = subprocess.run(
    [
        sys.executable,
        "-m",
        "manim",
        "-ql",
        "-c", str(config_file),
        "--media_dir",
        str(run_dir / "media"),
        str(scene_file),
        "GeneratedScene",
    ],
    capture_output=True,
    text=True,
)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-4000:])

    videos = list(run_dir.rglob("GeneratedScene.mp4"))

    if not videos:
        raise RuntimeError("No video produced.")

    return videos[0]


def main():
    # 1. Open and read your instructions directly from your local text file
    with open("prompt.txt", "r", encoding="utf-8") as f:
        prompt = f.read().strip()
    
    # 2. Let the script run immediately using that text file string
    run_id = str(int(time.time()))
    base_dir = Path(__file__).parent / "runs" / run_id

    print(f"\nRun directory: {base_dir}")

    print("\n[1] Extracting requirements...")

    requirements = extract_requirements(prompt)

    for requirement in requirements:
        print(f"  {requirement['id']} ({requirement['type']}): {requirement['description']}")

    print("\n[2] Generating code...")

    code = clean_code(ask_coder(prompt))

    # Kept between iterations so the evaluator can judge improvement.
    previous_result = None

    for attempt in range(5):

        print(f"\n=== ATTEMPT {attempt + 1} ===")
        print(code)

        try:
            print("\n[3] Rendering...")

            video = render(
                code,
                base_dir / f"attempt_{attempt}"
            )

        except Exception as error:

            print("\nRENDER ERROR:")
            print(error)

            repair_prompt = f"""
Original request:

{prompt}

Previous code:

{code}

Manim error:

{error}

Fix the code.

IMPORTANT RULES & DOCUMENTATION CONTRACTS:
- Your previous code threw an error because you are utilizing API methods that do not exist.
- Refer strictly to the Manim Community Module Index (https://docs.manim.community/en/stable/reference.html) for class specifications.
- Check the official Mobject standards at: https://docs.manim.community/en/stable/reference/manim.scene.scene.Scene.html
- You CANNOT use `self.camera.move_to` or animate the default Camera object.
- To use an animatable camera, change the class inheritance definition to: `class GeneratedScene(MovingCameraScene):` 
  and manipulate the view using `self.play(self.camera.frame.animate.move_to(target))`.
- For standard animations, use standard constructors listed under: https://docs.manim.community/en/stable/reference/manim.animation.animation.Animation.html
- Never use non-existent colors. Use basic strings like "#00FFFF" or native constants like BLUE, WHITE, RED.
- Return ONLY the absolute clean, complete Python code wrapped inside Markdown python codeblocks.
"""

            print("\n[REPAIR] Asking coder to fix the error...")

            code = clean_code(
                ask_coder(repair_prompt, 0.7)
            )

            continue

        print("\n[4] Extracting frame...")

        frames = extract_frames(video,
        base_dir / f"attempt_{attempt}" / "frames")

        print("\n[5] Evaluating requirements...")

        result = review_animation(
            prompt,
            requirements,
            [str(frame) for frame in frames],
            previous_result,
        )
        previous_result = result

        print("\nPER-REQUIREMENT RESULTS:")

        for entry in result.get("requirements", []):
            status = "PASS" if entry.get("pass") is True else "FAIL"
            confidence = entry.get("confidence", "?")
            print(f"  {entry.get('id')}: {status} ({confidence}) - {entry.get('evidence', '')}")

        failed_ids = find_failed_ids(result, requirements)

        # The model's own overall opinion is ignored; the per-requirement results decide.
        if failed_ids and attempt < 2:
            print(f"\n[REPAIR] Failed requirements: {', '.join(failed_ids)}")

            checklist = "\n".join(
                f"{r['id']}: {r['description']}" for r in requirements
            )

            code = clean_code(
                ask_coder(
                    f"{prompt}\n\nRequirements checklist:\n{checklist}\n\nPrevious code:\n\n{code}\n\nEvaluation of the rendered animation:\n{build_repair_report(result, requirements)}\n\nFix ONLY the listed failures. Return ONLY complete Python code. The class MUST be named GeneratedScene.",
                    0.7,
                )
            )

            continue

        break
    else:
        print("\nAll attempts failed.")


if __name__ == "__main__":
    main()
