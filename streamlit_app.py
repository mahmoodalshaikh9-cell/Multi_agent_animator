import json
import logging
import threading
import time
from pathlib import Path

import streamlit as st

import test_iteration_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_RUN_LOCK = threading.Lock()


def run_pipeline(prompt: str) -> tuple[Path, list[Path], Path]:
    """Run the full generation pipeline for the user's prompt and return the
    best video, its frames, and the run directory."""
    out_root = Path(__file__).parent / "baseline_runs" / "streamlit_ui"
    slug = f"ui_{int(time.time())}"

    test_iteration_video.run(slug, prompts={slug: prompt}, out_dir=out_root)

    out = out_root / slug
    summary = json.loads(
        (out / "summary.json").read_text(encoding="utf-8")
    )

    best = summary.get("best_attempt")
    if best is None:
        raise RuntimeError("Pipeline finished without a successful attempt.")

    attempt_dir = out / f"attempt_{best}"

    videos = [
        p for p in attempt_dir.glob("GeneratedScene.mp4") if p.is_file()
    ]
    if not videos:
        raise RuntimeError("Best attempt produced no video.")

    frames = sorted(attempt_dir.glob("frames/frame_*.jpg"))

    return videos[0], frames, out


def first_last_rendered(run_dir: Path):
    """First and last attempt in the run that actually produced a video."""
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


st.set_page_config(page_title="Capstone Proto", page_icon="🎬")
st.title("🎬 Capstone Proto")
st.caption(
    "Describe an animation in plain English. The pipeline generates the "
    "Manim code, renders it, evaluates it, and iterates until your prompt "
    "is satisfied."
)

with st.form("prompt_form"):
    prompt = st.text_area(
        "Animation prompt",
        height=150,
        placeholder="Create an animation of a blue circle moving from left to right...",
    )
    submitted = st.form_submit_button("Generate", type="primary")

if submitted:
    if not prompt.strip():
        st.warning("Enter a prompt first.")
    elif not _RUN_LOCK.acquire(blocking=False):
        st.warning(
            "Another animation is already running on this machine. "
            "Please wait for it to finish, then try again."
        )
    else:
        try:
            with st.status("Running pipeline...", expanded=True) as status:
                st.write(
                    "Generating code, rendering, and evaluating. "
                    "This can take several minutes."
                )
                logging.info("Starting run: %s", prompt.strip())
                video, frames, run_dir = run_pipeline(prompt)
                logging.info("Run complete: %s", run_dir.name)
                status.update(label="Pipeline complete", state="complete")

            first_video, last_video = first_last_rendered(run_dir)

            if first_video is not None:
                st.subheader("🔄 First vs final render")
                cols = st.columns(2)
                with cols[0]:
                    st.caption(f"First render: `{first_video.parent.name}`")
                    st.video(str(first_video))
                with cols[1]:
                    st.caption(f"Final render: `{last_video.parent.name}`")
                    st.video(str(last_video))

            st.subheader("🎥 Best animation")
            st.video(str(video))

            if frames:
                st.subheader("👁️ Vision frames")
                cols = st.columns(min(len(frames), 6))
                for col, frame in zip(cols, frames):
                    with col:
                        st.image(
                            str(frame),
                            caption=frame.name,
                            use_container_width=True,
                        )
        except Exception as error:
            logging.exception("Pipeline failed")
            st.error(f"Pipeline failed: {error}")
            st.exception(error)
        finally:
            _RUN_LOCK.release()
