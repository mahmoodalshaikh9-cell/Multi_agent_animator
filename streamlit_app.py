import json
import logging
import threading
import time
from pathlib import Path

import streamlit as st

import test_iteration_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_RUN_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Bootstrap-inspired theming
# ---------------------------------------------------------------------------

_BOOTSTRAP_CSS = """
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
      integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YcnS/1WR6zNmtwFE5yrT1H3Iy3VQI1p6Q1p"
      crossorigin="anonymous">

<style>
/* ---------- global ---------- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
    --bs-primary: #6610f2;
    --bs-body-font-family: 'Inter', sans-serif;
}

html, body, [class*="css"]  {
    font-family: 'Inter', sans-serif;
}

/* ---------- header bar ---------- */
.header-bar {
    background: linear-gradient(135deg, #6610f2 0%, #0d6efd 100%);
    padding: 1.8rem 2rem 1.4rem;
    border-radius: 0 0 1rem 1rem;
    margin: -1rem -1rem 1.5rem -1rem;
    color: #fff;
}
.header-bar h1 { margin: 0; font-weight: 700; font-size: 1.75rem; }
.header-bar p  { margin: 0.3rem 0 0; opacity: .85; font-size: .95rem; }

/* ---------- cards ---------- */
.card {
    background: #fff;
    border: 1px solid #dee2e6;
    border-radius: .75rem;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.dark .card { background: #1e1e1e; border-color: #333; }

/* ---------- section labels ---------- */
.section-label {
    font-size: .8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: #6c757d;
    margin-bottom: .5rem;
}

/* ---------- submit button polish ---------- */
.stButton > button {
    border-radius: .5rem;
    font-weight: 600;
    transition: transform .1s ease;
}
.stButton > button:hover { transform: translateY(-1px); }

/* ---------- video containers ---------- */
.video-box {
    border: 1px solid #dee2e6;
    border-radius: .75rem;
    overflow: hidden;
    background: #000;
}
.dark .video-box { border-color: #333; }

/* ---------- footer ---------- */
.footer {
    text-align: center;
    color: #6c757d;
    font-size: .8rem;
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid #dee2e6;
}
</style>
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


st.markdown(_BOOTSTRAP_CSS, unsafe_allow_html=True)

# ---------- header ----------
st.markdown(
    """
<div class="header-bar">
    <h1>Automated Animation Engine
</h1>
    <p>Describe an animation in plain English — the pipeline writes Manim code,
       renders, evaluates, and iterates until your prompt is satisfied.</p>
</div>
""",
    unsafe_allow_html=True,
)

# ---------- prompt card ----------
with st.form("prompt_form"):
    st.markdown('<div class="section-label">Prompt</div>', unsafe_allow_html=True)
    prompt = st.text_area(
        "Animation prompt",
        height=150,
        placeholder="Create an animation of a blue circle moving from left to right...",
        label_visibility="collapsed",
    )
    submitted = st.form_submit_button("✨  Generate", type="primary", use_container_width=True)

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
                st.markdown('<div class="section-label">First vs Final Render</div>', unsafe_allow_html=True)
                cols = st.columns(2)
                with cols[0]:
                    st.markdown(f"**{first_video.parent.name}**")
                    st.video(str(first_video))
                with cols[1]:
                    st.markdown(f"**{last_video.parent.name}**")
                    st.video(str(last_video))

            st.markdown('<div class="section-label">Best Animation</div>', unsafe_allow_html=True)
            st.video(str(video))

            if frames:
                st.markdown('<div class="section-label">Vision Frames</div>', unsafe_allow_html=True)
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

# ---------- footer ----------
st.markdown(
    '<div class="footer"> Manim animation generation pipeline</div>',
    unsafe_allow_html=True,
)
