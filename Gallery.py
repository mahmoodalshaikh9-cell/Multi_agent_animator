import streamlit as st
pages = {
    "Animator": [
        st.Page("steramlit_app.py"),
       
    ],
    "Gallery": [
        st.Page("Gallery.py", title="Learn about us"),
        
    ],
}


pg = st.navigation(pages, position="top")
pg.run()
