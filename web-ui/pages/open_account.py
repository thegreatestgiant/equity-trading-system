import streamlit as st
from auth_state import require_auth
require_auth()
from accounts_pages import render_create_account_page

render_create_account_page()