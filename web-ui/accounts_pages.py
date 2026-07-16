import streamlit as st

from api_client import create_account, get_user_accounts, update_user_account
from account_picker import account_select, _invalidate_account_options_cache


@st.fragment(run_every="15s")
def _accounts_list_fragment():
    result = get_user_accounts()
    if result["status"] == "success":
        # Backend returns {"accounts": {name: account_id, ...}}
        accounts = result["data"].get("accounts", {})
    else:
        accounts = {}
        st.error(result["message"])

    if not accounts:
        st.info("You don't have any accounts yet. Create one to get started.")
        if st.button("➕ Open New Account", key="empty_state_create_account"):
            st.session_state.redirect_to = "pages/open_account.py"
            st.rerun()
    else:
        for name, account_id in accounts.items():
            display_name = name or "(unnamed account)"
            with st.container(border=True):
                cols = st.columns([3, 2, 2, 2])
                cols[0].write(f"**{display_name}**")
                cols[0].caption(f"`{account_id}`")
                if cols[1].button("📊 View Positions", key=f"acct_{account_id}"):
                    st.session_state.jump_to_account = account_id
                    st.session_state.redirect_to = "pages/positions.py"
                    st.rerun()
                if cols[2].button("📜 View Trades", key=f"acct_view_trade_{account_id}"):
                    st.session_state.jump_to_trades_account = account_id
                    st.session_state.redirect_to = "pages/trade_history.py"
                    st.rerun()
                if cols[3].button("💸 Book a Trade", key=f"acct_trade_{account_id}"):
                    st.session_state.jump_to_trade_account = account_id
                    st.session_state.redirect_to = "pages/book_a_trade.py"
                    st.rerun()


def render_my_accounts_page():
    st.header("🏦 My Accounts", anchor=False)
    if st.button("🚀 Mass Booking"):
        st.session_state.redirect_to = "pages/mass_trade.py"
        st.rerun()
    _accounts_list_fragment()


def render_create_account_page():
    st.header("➕ Open a New Account", anchor=False)
    st.caption("POST /users/account")

    with st.form("create_account_form"):
        name = st.text_input("Account Name", placeholder="e.g. Retirement, Trading")
        can_short = st.checkbox("Can Short")
        submitted = st.form_submit_button("Create Account")

    if submitted:
        result = create_account(name, can_short)
        if result["status"] == "success":
            _invalidate_account_options_cache()
            account_id = result.get("account_id")
            display_name = result.get("name") or name or "(unnamed account)"
            st.session_state["_created_account_id"] = account_id
            st.session_state["_created_account_name"] = display_name
        else:
            st.error(result["message"])

    created_id = st.session_state.get("_created_account_id")
    created_name = st.session_state.get("_created_account_name")
    if created_id:
        st.success(f"Account **{created_name}** created — ID: `{created_id}`")
        col1, col2, _ = st.columns([1, 1, 3])
        if col1.button("💸 Enter a Trade", type="primary"):
            st.session_state.jump_to_trade_account = created_id
            st.session_state.pop("_created_account_id", None)
            st.session_state.pop("_created_account_name", None)
            st.switch_page("pages/book_a_trade.py")
        if col2.button("📋 Mass Trade", type="primary"):
            st.session_state.pop("_created_account_id", None)
            st.session_state.pop("_created_account_name", None)
            st.switch_page("pages/mass_trade.py")


def render_update_account_page():
    st.header("✏️ Edit Account", anchor=False)
    st.caption("PATCH /users/update_account_details/{account_id}")

    account_id = account_select()
    account_name = st.text_input("Account Name (leave blank to keep current)")
    can_short = st.checkbox("Can Short")

    if st.button("Update Account"):
        if not account_id:
            st.error("Select an account first.")
        else:
            result = update_user_account(
                account_id,
                account_name=account_name or None,
                can_short=can_short,
            )
            if result["status"] == "success":
                _invalidate_account_options_cache()
                st.success("Account updated successfully.")
            else:
                st.error(result["message"])