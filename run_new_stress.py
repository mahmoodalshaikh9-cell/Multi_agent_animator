"""One-off stress driver for the new 5 prompts (metrics data collection).

Runs ONLY the newly added slugs from stress_prompts.py (lithium_battery,
airplane_lift, rain_formation, binary_search, sky_blue) through the
test_iteration_video loop. Writes to baseline_runs/stress_tests under these
new slugs, so no existing stress output or video_iteration output is
overwritten.

Usage: python run_new_stress.py [slug ...]
"""
import sys
from pathlib import Path

import stress_prompts

BASE_DIR = Path(__file__).parent
OUT_ROOT = BASE_DIR / "baseline_runs" / "stress_tests"

NEW_SLUGS = [
    "lithium_battery",
    "airplane_lift",
    "rain_formation",
    "binary_search",
    "sky_blue",
]


def main():
    import test_iteration_video as tiv

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = [a for a in sys.argv[1:]]
    slugs = [a for a in args if a in stress_prompts.STRESS_PROMPTS]
    if not slugs:
        slugs = NEW_SLUGS

    for slug in slugs:
        if slug not in stress_prompts.STRESS_PROMPTS:
            print(f"!! unknown slug: {slug}; skipping")
            continue
        try:
            tiv.run(
                slug,
                consume=False,
                out_dir=OUT_ROOT,
                prompts=stress_prompts.STRESS_PROMPTS,
            )
        except Exception:
            import traceback

            traceback.print_exc()
            print(f"!! run failed for {slug}; continuing")

    print(f"\nDone. Stress outputs in {OUT_ROOT}")


if __name__ == "__main__":
    main()
