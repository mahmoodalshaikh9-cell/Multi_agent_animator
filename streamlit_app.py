import os
import streamlit as st
import subprocess
import sys
from pathlib import Path
import test_iteration_video
from local_agent import ask_coder,clean_code
import json
import time
import manim 
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
openrouter_BASE_URL = "https://openrouter.ai/api/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

REQUEST_TIMEOUT = 60
RENDER_TIMEOUT = 120

FALLBACK_MODELS = [
    "deepseek-chat",
]




# st.set_page_config(
#     page_title="Local Manim Agent",
#     page_icon="🎬",
# )

# st.title("🎬 Local Manim Agent")

# prompt = st.text_area(
#     "Animation prompt",
#     height=150,
#     placeholder="Create an animation showing a blue circle moving from left to right.",
# )

        
            
# if st.button("Generate", type="primary") and prompt.strip():
#     if st.download_button(
#                     label="prompt",
#                     data=prompt,
#                     file_name="prompt.txt"):

#         runs_root = Path(__file__).parent / "runs"

#         st.write(f"Runs folder: `{runs_root}`")

#         # Run pipeline while streaming its output live.
#         # Without this, the page sits frozen for minutes because the
#         # pipeline performs many local model calls before finishing.
#         with st.status("Running pipeline...", expanded=True) as status:
#             log_view = st.empty()

#             child_env = os.environ.copy()
#             # Python buffers stdout when piped; unbuffered keeps the log live.
#             child_env["PYTHONUNBUFFERED"] = "1"

#             process = subprocess.Popen(
#                 [
#                     sys.executable,
#                     str(Path(__file__).parent / "pipeline_deepseek.py"),
#                 ],
#                 stdin=subprocess.PIPE,
#                 stdout=subprocess.PIPE,
#                 stderr=subprocess.STDOUT,
#                 text=True,
#                 encoding="utf-8",
#                 errors="replace",
#                 bufsize=1,
#                 env=child_env,
#                 cwd=str(Path(__file__).parent),
#             )

#             process.stdin.write(prompt.strip() + "\n")
#             process.stdin.close()

#             lines = []

#             for line in process.stdout:
#                 lines.append(line)
#                 log_view.code("".join(lines[-50:]))

#             process.wait()

#             status.update(
#                 label=f"Pipeline finished (exit code {process.returncode})",
#                 state="complete" if process.returncode == 0 else "error",
#             )

#         full_log = "".join(lines)

#         with st.expander("Full pipeline log", expanded=False):
#             st.code(full_log)

#         # Find videos generated DURING this run
#         run_dirs = sorted(
#             p for p in runs_root.iterdir() if p.is_dir()
#         ) if runs_root.exists() else []

#         run_dir = run_dirs[-1] if run_dirs else None

#         st.write(f"Run: `{run_dir.name}`") if run_dir else None

#         videos = list(run_dir.rglob("GeneratedScene.mp4")) if run_dir else []

#         if videos:

#             video = videos[-1]

#             st.subheader("🎥 Animation")

#             st.video(str(video))

#         else:

#             st.error("No animation was produced.")

#             st.stop()

#         # Find frames from THIS run
#         frames = sorted(
#             run_dir.rglob("frame_*.jpg")
#         ) if run_dir else []

#         if frames:

#             st.subheader("👁️ Vision frames")

#             cols = st.columns(len(frames))

#             for col, frame in zip(cols, frames):

#                 with col:
#                     st.image(
#                         str(frame),
#                         caption=frame.name,
#                         use_container_width=True,
#                     )

def main(prompt):

    prompt = prompt.strip()

    out_root = Path(__file__).parent / "baseline_runs" / "streamlit_ui"

    slug = f"ui_{int(time.time())}"

    test_iteration_video.run(
        slug,
        prompts={slug: prompt},
        out_dir=out_root,
    )

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

    video = videos[0]

    frames = sorted(
        attempt_dir.glob("frames/frame_*.jpg")
    )

    return video, frames, out


def first_last_rendered(run_dir: Path):
    """Dynamically find the first and last attempt that actually rendered a
    video. Reads the exact attempt_* dirs on disk (never hardcoded), skipping
    validation/render-failure attempts that produced no GeneratedScene.mp4."""
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
    first = rendered[0] / "GeneratedScene.mp4"
    last = rendered[-1] / "GeneratedScene.mp4"
    return first, last


with st.form("my_form"):
    prompt= st.text_area("Your Label", value="Enter text here")

   
    submitted = st.form_submit_button("Submit")
    if submitted:
       try:
           video, frames, run_dir = main(prompt)
       except Exception as error:
           st.error(f"Pipeline failed: {error}")
           st.stop()

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

       st.subheader("🎥 Animation")
       st.video(str(video))
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

