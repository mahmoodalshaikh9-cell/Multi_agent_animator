import os
import streamlit as st
import subprocess
import sys
from pathlib import Path


st.set_page_config(
    page_title="Local Manim Agent",
    page_icon="🎬",
)

st.title("🎬 Local Manim Agent")

prompt = st.text_area(
    "Animation prompt",
    height=150,
    placeholder="Create an animation showing a blue circle moving from left to right.",
)

if st.button("Generate", type="primary") and prompt.strip():

    runs_root = Path(__file__).parent / "runs"

    st.write(f"Runs folder: `{runs_root}`")

    # Run pipeline while streaming its output live.
    # Without this, the page sits frozen for minutes because the
    # pipeline performs many local model calls before finishing.
    with st.status("Running pipeline...", expanded=True) as status:
        log_view = st.empty()

        child_env = os.environ.copy()
        # Python buffers stdout when piped; unbuffered keeps the log live.
        child_env["PYTHONUNBUFFERED"] = "1"

        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).parent / "pipeline.py"),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=child_env,
            cwd=str(Path(__file__).parent),
        )

        process.stdin.write(prompt.strip() + "\n")
        process.stdin.close()

        lines = []

        for line in process.stdout:
            lines.append(line)
            log_view.code("".join(lines[-50:]))

        process.wait()

        status.update(
            label=f"Pipeline finished (exit code {process.returncode})",
            state="complete" if process.returncode == 0 else "error",
        )

    full_log = "".join(lines)

    with st.expander("Full pipeline log", expanded=False):
        st.code(full_log)

    # Find videos generated DURING this run
    run_dirs = sorted(
        p for p in runs_root.iterdir() if p.is_dir()
    ) if runs_root.exists() else []

    run_dir = run_dirs[-1] if run_dirs else None

    st.write(f"Run: `{run_dir.name}`") if run_dir else None

    videos = list(run_dir.rglob("GeneratedScene.mp4")) if run_dir else []

    if videos:

        video = videos[-1]

        st.subheader("🎥 Animation")

        st.video(str(video))

    else:

        st.error("No animation was produced.")

        st.stop()

    # Find frames from THIS run
    frames = sorted(
        run_dir.rglob("frame_*.jpg")
    ) if run_dir else []

    if frames:

        st.subheader("👁️ Vision frames")

        cols = st.columns(len(frames))

        for col, frame in zip(cols, frames):

            with col:
                st.image(
                    str(frame),
                    caption=frame.name,
                    use_container_width=True,
                )