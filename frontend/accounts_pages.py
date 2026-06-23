import streamlit as st

from api_client import create_account, get_user_accounts, update_user_account


def render_my_accounts_page():
    st.header("🏦 My Accounts")

    if st.button("Refresh"):
        st.session_state.pop("accounts_cache", None)

    if "accounts_cache" not in st.session_state:
        result = get_user_accounts()
        if result["status"] == "success":
            # Backend returns {"accounts": {name: account_id, ...}}
            st.session_state.accounts_cache = result["data"].get("accounts", {})
        else:
            st.session_state.accounts_cache = {}
            st.error(result["message"])

    accounts = st.session_state.accounts_cache

    if not accounts:
        st.info("You don't have any accounts yet. Create one to get started.")
    else:
        for name, account_id in accounts.items():
            display_name = name or "(unnamed account)"
            with st.container(border=True):
                cols = st.columns([3, 1])
                cols[0].write(f"**{display_name}**")
                cols[0].caption(f"`{account_id}`")
                if cols[1].button("View Positions →", key=f"acct_{account_id}"):
                    st.session_state.jump_to_account = account_id
                    st.rerun()


def render_create_account_page():
    st.header("➕ Open a New Account")
    st.caption("POST /users/account")

    name = st.text_input("Account Name", placeholder="e.g. Retirement, Trading")
    can_short = st.checkbox("Can Short")

    if st.button("Create Account"):
        result = create_account(name, can_short)
        if result["status"] == "success":
            account_id = result.get("account_id")
            display_name = result.get("name") or name or "(unnamed account)"
            if account_id:
                st.success(f"Account **{display_name}** created — ID: `{account_id}`")
            else:
                st.success("Account created.")
            st.session_state.pop("accounts_cache", None)
        else:
            st.error(result["message"])


def render_update_account_page():
    st.header("✏️ Edit Account Settings")
    st.caption("PUT /users/accounts/{account_id}")
    st.caption("This endpoint doesn't exist in the backend yet -- showing mock data.")

    account_id = st.text_input("Account ID")
    can_short = st.checkbox("Can Short")

    if st.button("Update Account"):
        data = {
            "username": st.session_state.username,
            "can_short": can_short,
        }
        result = update_user_account(account_id, data)
        st.json(result)
