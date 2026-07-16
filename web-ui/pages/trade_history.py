import streamlit as st
from auth_state import require_auth
require_auth()
from trade_history_pages import render_all_trades_page

render_all_trades_page()