import streamlit as st
from pathlib import Path

st.set_page_config(page_title="AcuityAI Capability Map", layout="wide")

html_content = Path(__file__).parent.joinpath("capability_map.html").read_text()

st.components.v1.html(html_content, height=2800, scrolling=True)
