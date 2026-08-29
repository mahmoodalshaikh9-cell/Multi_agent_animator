import os
import streamlit as st
import subprocess
import sys
from pathlib import Path
from pipeline_deepseek import main as pipeline_main,extract_frames,extract_requirements,planning,render
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

    prompt_file = Path(__file__).parent / "prompt.txt"

    prompt_file.write_text(prompt, encoding="utf-8")

    pipeline_main()

    runs_root = Path(__file__).parent / "runs"

    run_dirs = sorted(
        p for p in runs_root.iterdir() if p.is_dir()
    ) if runs_root.exists() else []

    if not run_dirs:
        raise RuntimeError("No run directory was created.")

    run_dir = run_dirs[-1]

    videos = list(run_dir.rglob("GeneratedScene.mp4"))

    if not videos:
        raise RuntimeError("Pipeline finished without producing a video.")

    video = videos[-1]

    frames = sorted(
        run_dir.rglob("frame_*.jpg")
    )

    return video, frames


with st.form("my_form"):
    prompt= st.text_area("Your Label", value="Enter text here")

    # Every form must have a submit button.
    submitted = st.form_submit_button("Submit")
    if submitted:
       try:
           video, frames = main(prompt)
       except Exception as error:
           st.error(f"Pipeline failed: {error}")
           st.stop()
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

