import st_aggrid
import streamlit as st

from api_client import logout
from theme import apply_theme
from persistent_login import forget_login
from auth_pages import render_auth_sidebar, render_login_page, render_register_page
from accounts_pages import (
    render_my_accounts_page,
    render_create_account_page,
    render_update_account_page,
)
from positions_pages import (
    render_all_positions_page,
    render_positions_by_account_page,
    render_positions_by_ticker_page,
    render_positions_by_account_and_ticker_page,
)
from trade_history_pages import (
    render_all_trades_page,
    render_trades_by_account_page,
    render_trades_by_ticker_page,
    render_trades_by_account_and_ticker_page,
    render_trade_by_id_page,
    render_update_trade_page,
)
from enter_trade_page import render_enter_trade_page
from persistent_login import restore_login_from_browser
from mass_trade_page import render_mass_trade_page


st.set_page_config(page_title="Equity Trading System", page_icon="📈", layout="wide")
apply_theme()


if "username" not in st.session_state:
    st.session_state.username = None

# if "username" not in st.session_state:
#     st.session_state.username = "dev_bypass"  # TODO: remove this before going live, allows to see the main page without logging in

restore_login_from_browser()

st.title("📈 Equity Trading System")


if st.session_state.username is None:
    page = render_auth_sidebar()

    if page == "Login":
        render_login_page()
    elif page == "Register":
        render_register_page()

else:
    st.sidebar.markdown(f"👤 **{st.session_state.username}**")
    st.sidebar.divider()

    if st.sidebar.button("🚪 Log Out"):
        logout()
        forget_login()
        st.session_state.username = None
        st.session_state.pop("saved_session_cookie", None)
        st.session_state.pop("http", None)

        for key in ["remember_user", "remember_session"]:
            if key in st.query_params:
                del st.query_params[key]

        st.rerun()

    page_options = {
        "my_accounts": ("🏦 My Accounts", "My Accounts"),
        "all_positions": ("📊 All Positions", "All Positions"),
        "positions_by_account": ("📊 Positions by Account", "Positions by Account"),
        "positions_by_ticker": ("📊 Positions by Ticker", "Positions by Ticker"),
        "positions_by_account_ticker": ("📊 Positions by Account & Ticker", "Positions by Account and Ticker"),
        "all_trades": ("📜 Trade History", "All Trades"),
        "trades_by_account": ("📜 Trade History by Account", "Trades by Account"),
        "trades_by_ticker": ("📜 Trade History by Ticker", "Trades by Ticker"),
        "trades_by_account_ticker": ("📜 Trade History by Account & Ticker", "Trades by Account and Ticker"),
        "trade_by_id": ("🔍 Look Up Trade by ID", "Trade by ID"),
        "enter_trade": ("💸 Book a Trade", "Enter Trade"),
        "mass_trade": ("📋 Mass Trade Booker", "Mass Trade Booker"),
        "create_account": ("➕ Open New Account", "Create Account"),
        "update_account": ("✏️ Edit Account Settings", "Update Account"),
        "update_trade": ("✏️ Edit Trade", "Update Trade"),
    }

    page_name_to_key = {page_name: key for key, (_, page_name) in page_options.items()}

    if "jump_to_account" in st.session_state:
        st.query_params["page"] = "positions_by_account"
        st.session_state.nav_page = "positions_by_account"

    if st.session_state.pop("jump_to_trade_page", False):
        st.query_params["page"] = "enter_trade"
        st.session_state.nav_page = "enter_trade"

    if st.session_state.pop("jump_to_create_account_page", False):
        st.query_params["page"] = "create_account"
        st.session_state.nav_page = "create_account"

    current_page_key = st.query_params.get("page", "my_accounts")

    if current_page_key not in page_options:
        current_page_key = "my_accounts"

    page_keys = list(page_options.keys())


    def sync_nav_to_url():
        st.query_params["page"] = st.session_state.nav_page


    if "nav_page" not in st.session_state or st.session_state.nav_page not in page_options:
        st.session_state.nav_page = current_page_key

    st.sidebar.markdown("**Navigate**")
    st.sidebar.radio(
        "Page",
        page_keys,
        format_func=lambda key: page_options[key][0],
        key="nav_page",
        on_change=sync_nav_to_url,
        label_visibility="collapsed",
    )

    page = page_options[st.session_state.nav_page][1]

    PAGE_RENDERERS = {
        "Enter Trade": render_enter_trade_page,
        "Mass Trade Booker": render_mass_trade_page,
        "My Accounts": render_my_accounts_page,
        "All Positions": render_all_positions_page,
        "Positions by Account": render_positions_by_account_page,
        "Positions by Ticker": render_positions_by_ticker_page,
        "Positions by Account and Ticker": render_positions_by_account_and_ticker_page,
        "All Trades": render_all_trades_page,
        "Trades by Account": render_trades_by_account_page,
        "Trades by Ticker": render_trades_by_ticker_page,
        "Trades by Account and Ticker": render_trades_by_account_and_ticker_page,
        "Trade by ID": render_trade_by_id_page,
        "Create Account": render_create_account_page,
        "Update Account": render_update_account_page,
        "Update Trade": render_update_trade_page,
    }

    PAGE_RENDERERS[page]()