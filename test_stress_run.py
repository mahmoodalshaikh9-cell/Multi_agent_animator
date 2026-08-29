"""Stress-test driver for the finalized pipeline.

Runs a curated set of prompts (see STRESS_PROMPTS) through the same
test_iteration_video loop, but writes results to a NEW output directory
(baseline_runs/stress_tests) so the presentation outputs under
baseline_runs/video_iteration are left untouched.

Usage: python test_stress_run.py
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

from stress_prompts import STRESS_PROMPTS

# Curated 5 (4 stress variants + the black-hole prompt).
SLUGS = [
    "projectile_motion_3",
    "iron_atom_3",
    "kmeans_3",
    "la_espada_3",
    "black_hole",
]

OUT_ROOT = BASE_DIR / "baseline_runs" / "stress_tests"


def main():
    import test_iteration_video as tiv

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    for slug in SLUGS:
        if slug not in STRESS_PROMPTS:
            print(f"!! unknown stress slug: {slug}; skipping")
            continue
        try:
            tiv.run(
                slug,
                consume=False,
                out_dir=OUT_ROOT,
                prompts=STRESS_PROMPTS,
            )
        except Exception:
            import traceback

            traceback.print_exc()
            print(f"!! run failed for {slug}; continuing")

    print(f"\nDone. Stress outputs in {OUT_ROOT}")


if __name__ == "__main__":
    main()
