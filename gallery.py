import json
from pathlib import Path

import streamlit as st

_SITE_DIR = Path(__file__).parent / "site"

_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.header-bar {
    background: linear-gradient(135deg, #6610f2 0%, #0d6efd 100%);
    padding: 1.8rem 2rem 1.4rem;
    border-radius: 0 0 1rem 1rem;
    margin: 0 -1rem 1.5rem -1rem;
    color: #fff;
}
.header-bar h1 { margin: 0; font-weight: 700; font-size: 1.75rem; }
.header-bar p  { margin: 0.3rem 0 0; opacity: .85; font-size: .95rem; }
.section-label {
    font-size: .8rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: .06em; color: #6c757d; margin-bottom: .5rem;
}
.footer {
    text-align: center; color: #6c757d; font-size: .8rem;
    margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #dee2e6;
}
</style>
"""


def load_catalog():
    catalog_path = _SITE_DIR / "catalog.json"
    if not catalog_path.exists():
        return []
    return json.loads(catalog_path.read_text(encoding="utf-8"))


st.markdown(_STYLE, unsafe_allow_html=True)

st.markdown(
    """
<div class="header-bar">
    <h1>🎬 Gallery</h1>
    <p>Rendered Manim animations produced by the Capstone Proto pipeline.</p>
</div>
""",
    unsafe_allow_html=True,
)

items = load_catalog()

if not items:
    st.info("No catalog found. Run the pipeline to generate animations.")
else:
    cols = st.columns(3)
    for idx, item in enumerate(items):
        col = cols[idx % 3]
        video_path = _SITE_DIR / item["video"]
        with col:
            st.markdown('<div class="section-label">{}</div>'.format(item["title"]), unsafe_allow_html=True)
            if video_path.exists():
                st.video(str(video_path))
            else:
                st.warning(f"Missing video for {item['slug']}")
            st.caption(
                f"Prompt: `{item['prompt']}`  ·  Quality: {item.get('best_quality') or 'n/a'}"
            )
