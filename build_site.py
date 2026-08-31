"""Build a static gallery site (site/) from the first stress-test outputs.

For each of the 5 first-stress slugs it copies the best-attempt video and
frames into site/assets/<slug>/ and writes site/catalog.json with the prompt
title, video path, frame paths, and run metrics. GitHub Pages serves site/.
"""
import json
import shutil
from pathlib import Path

BASE = Path(__file__).parent
SRC = BASE / "baseline_runs" / "stress_tests"
OUT = BASE / "site"
ASSETS = OUT / "assets"

SLUGS = [
    "projectile_motion_3",
    "iron_atom_3",
    "kmeans_3",
    "la_espada_3",
    "black_hole",
]

TITLES = {
    "projectile_motion_3": "Projectile Motion",
    "iron_atom_3": "Iron Atom (3D)",
    "kmeans_3": "K-Means Clustering",
    "la_espada_3": "La Espada",
    "black_hole": "Black Hole Spacetime",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if ASSETS.exists():
        shutil.rmtree(ASSETS)
    ASSETS.mkdir(parents=True, exist_ok=True)

    catalog = []
    for slug in SLUGS:
        summary_path = SRC / slug / "summary.json"
        if not summary_path.exists():
            print(f"!! no summary for {slug}")
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        best = summary.get("best_attempt")
        attempt_dir = SRC / slug / f"attempt_{best}"
        video_src = attempt_dir / "GeneratedScene.mp4"
        if not video_src.exists():
            print(f"!! no best video for {slug}")
            continue

        dest = ASSETS / slug
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video_src, dest / "best.mp4")

        catalog.append(
            {
                "slug": slug,
                "title": TITLES.get(slug, slug),
                "prompt": summary.get("slug"),
                "video": f"assets/{slug}/best.mp4",
                "best_attempt": best,
                "best_quality": summary.get("best_quality"),
                "best_req_pass": summary.get("best_req_pass"),
                "total_cost_usd": summary.get("total_cost_usd"),
                "total_duration_s": summary.get("total_duration_s"),
            }
        )
        print(f"  built {slug}: video={video_src.name}")

    (OUT / "catalog.json").write_text(
        json.dumps(catalog, indent=2), encoding="utf-8"
    )
    print(f"\nWrote {OUT / 'catalog.json'} with {len(catalog)} entries")


if __name__ == "__main__":
    main()
