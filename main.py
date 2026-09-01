import streamlit as st

st.set_page_config(page_title="Capstone Proto", page_icon="🎬", layout="wide")

pages = [
    st.Page("streamlit_app.py", title="Generate", icon="🎬", default=True),
    st.Page("gallery.py", title="Gallery", icon="🖼️"),
]

pg = st.navigation(pages, position="top")
pg.run()
