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
            st.session_state.jump_to_create_account_page = True
            st.rerun(scope="app")
    else:
        for name, account_id in accounts.items():
            display_name = name or "(unnamed account)"
            with st.container(border=True):
                cols = st.columns([3, 1, 1])
                cols[0].write(f"**{display_name}**")
                cols[0].caption(f"`{account_id}`")
                if cols[1].button("View Positions →", key=f"acct_{account_id}"):
                    st.session_state.jump_to_account = account_id
                    st.rerun(scope="app")
                if cols[2].button("💸 Book a Trade", key=f"acct_trade_{account_id}"):
                    st.session_state.jump_to_trade_account = account_id
                    st.session_state.jump_to_trade_page = True
                    st.rerun(scope="app")


def render_my_accounts_page():
    st.header("🏦 My Accounts")
    st.warning("TEST MARKER — latest version as of 12:37 PM 7/14 (remove before ship)")
    _accounts_list_fragment()


def render_create_account_page():
    st.header("➕ Open a New Account")
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
            if account_id:
                st.success(f"Account **{display_name}** created — ID: `{account_id}`")
            else:
                st.success("Account created.")
        else:
            st.error(result["message"])


def render_update_account_page():
    st.header("✏️ Edit Account Settings")
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