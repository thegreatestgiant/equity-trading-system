import streamlit as st

from api_client import logout
from theme import apply_theme
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


st.set_page_config(page_title="Equity Trading System", page_icon="📈", layout="wide")
apply_theme()


if "username" not in st.session_state:
    st.session_state.username = None

# if "username" not in st.session_state:
#     st.session_state.username = "dev_bypass"  # TODO: remove this before going live, allows to see the main page without logging in


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
        st.session_state.username = None
        st.rerun()

    page_options = {
        "🏦 My Accounts": "My Accounts",
        "📊 All Positions": "All Positions",
        "📊 Positions by Account": "Positions by Account",
        "📊 Positions by Ticker": "Positions by Ticker",
        "📊 Positions by Account & Ticker": "Positions by Account and Ticker",
        "📜 Trade History": "All Trades",
        "📜 Trade History by Account": "Trades by Account",
        "📜 Trade History by Ticker": "Trades by Ticker",
        "📜 Trade History by Account & Ticker": "Trades by Account and Ticker",
        "🔍 Look Up Trade by ID": "Trade by ID",
        "💸 Book a Trade": "Enter Trade",
        "➕ Open New Account": "Create Account",
        "✏️ Edit Account Settings": "Update Account",
        "✏️ Edit Trade": "Update Trade",
    }

    st.sidebar.markdown("**Navigate**")
    selected_label = st.sidebar.radio(
        "Page", list(page_options.keys()), label_visibility="collapsed"
    )
    page = page_options[selected_label]

    # Lets other pages send the user to "Positions by Account" with a
    # specific account already filled in, e.g. from a My Accounts link.
    if "jump_to_account" in st.session_state:
        page = "Positions by Account"

    PAGE_RENDERERS = {
        "Enter Trade": render_enter_trade_page,
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
