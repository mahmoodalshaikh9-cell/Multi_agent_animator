"""CI driver: run the pipeline for a prompt and publish the first/last
rendered attempts to demo/ so GitHub Pages can display them.

Invoked by .github/workflows/render.yml. Secrets come from GitHub Actions
env vars (secrets_loader reads env first), so no code changes are needed.
"""
import argparse
import json
import shutil
import time
from pathlib import Path

import test_iteration_video

ROOT = Path(__file__).parent
DEMO = ROOT / "demo"


def first_last_rendered(run_dir: Path):
    attempts = sorted(
        (p for p in run_dir.glob("attempt_*") if p.is_dir()),
        key=lambda p: int(p.name.split("_")[1]),
    )
    rendered = [
        a for a in attempts
        if (a / "GeneratedScene.mp4").is_file()
    ]
    if not rendered:
        return None, None
    return (
        rendered[0] / "GeneratedScene.mp4",
        rendered[-1] / "GeneratedScene.mp4",
    )


def main(prompt: str) -> None:
    prompt = prompt.strip()
    slug = f"ci_{int(time.time())}"
    out_root = ROOT / "baseline_runs" / "streamlit_ui"

    print(f"\n=== Rendering for prompt ===\n{prompt}\n")
    test_iteration_video.run(slug, prompts={slug: prompt}, out_dir=out_root)

    run_dir = out_root / slug
    summary = json.loads(
        (run_dir / "summary.json").read_text(encoding="utf-8")
    )

    first, last = first_last_rendered(run_dir)
    if first is None:
        raise SystemExit("No attempt rendered a video.")

    DEMO.mkdir(exist_ok=True)
    shutil.copy2(first, DEMO / "first.mp4")
    shutil.copy2(last, DEMO / "final.mp4")
    (DEMO / "run.json").write_text(
        json.dumps(
            {
                "prompt": prompt,
                "first_attempt": first.parent.name,
                "last_attempt": last.parent.name,
                "best_attempt": summary.get("best_attempt"),
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "run_dir": str(run_dir.relative_to(ROOT)),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nPublished:")
    print(f"  prompt     : {prompt}")
    print(f"  first.mp4  <- {first}")
    print(f"  final.mp4  <- {last}")
    print(f"  run.json   <- {DEMO / 'run.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    args = parser.parse_args()
    main(args.prompt)
