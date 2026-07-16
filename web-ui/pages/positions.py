import streamlit as st
from auth_state import require_auth
require_auth()
from positions_pages import render_all_positions_page

render_all_positions_page()