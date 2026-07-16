import streamlit as st
from auth_state import require_auth
require_auth()
from accounts_pages import render_update_account_page

render_update_account_page()