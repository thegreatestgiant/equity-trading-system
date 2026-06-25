import streamlit as st

from api_client import login, register
from persistent_login import remember_login


def render_auth_sidebar():
    """Renders the Login/Register page picker in the sidebar (radio --
    shows current page, no free text entry). Returns the selected page
    name: 'Login' or 'Register'."""
    st.sidebar.markdown("**Page**")
    return st.sidebar.radio(
        "Page", ["Login", "Register"], label_visibility="collapsed"
    )


def render_login_page():
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        result = login(username, password)
        if result["status"] == "success":
            st.session_state.username = username
            st.session_state.saved_session_cookie = result["session_cookie"]
            st.query_params["remember_user"] = username
            st.query_params["remember_session"] = result["session_cookie"]
            remember_login(username, result["session_cookie"])
            st.rerun()
        else:
            st.error(result.get("message", "Login failed"))


def render_register_page():
    with st.form("register_form"):
        username = st.text_input("New Username")
        password = st.text_input("New Password", type="password")
        submitted = st.form_submit_button("Register")

    if submitted:
        result = register(username, password)
        if result["status"] == "success":
            # Auto-login with the same credentials, then drop the user
            # straight into the main app instead of back at the login page.
            login_result = login(username, password)
            if login_result["status"] == "success":
                st.session_state.username = username
                remember_login(username, login_result["session_cookie"])
                st.success(f"Account created for {result['username']}. Logging you in...")
                st.rerun()
            else:
                # Account was created but auto-login failed for some reason --
                # fall back to telling the user to log in manually.
                st.success(f"Account created for {result['username']}. You can now log in.")
                st.error(login_result.get("message", "Auto-login failed."))
        else:
            st.error(result["message"])