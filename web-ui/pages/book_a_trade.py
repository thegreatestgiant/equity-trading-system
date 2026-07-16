import streamlit as st
from auth_state import require_auth
require_auth()
from enter_trade_page import render_enter_trade_page

render_enter_trade_page()