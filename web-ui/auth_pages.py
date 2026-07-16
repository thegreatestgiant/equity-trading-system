import time

import streamlit as st

from api_client import login, register
import auth_state


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
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Login")

    if submitted:
        result = login(username, password)
        if result["status"] == "success":
            auth_state.remember_login(username, result["session_cookie"])
            time.sleep(0.5)
            st.session_state.redirect_to = "pages/my_accounts.py"
            st.rerun()
        else:
            st.error(result.get("message", "Login failed"))

    st.caption("Don't have an account?")
    st.page_link("pages/register.py", label="Register here")


def render_register_page():
    with st.form("register_form"):
        username = st.text_input("New Username", autocomplete="username")
        password = st.text_input("New Password", type="password", autocomplete="new-password")
        submitted = st.form_submit_button("Register")

    if submitted:
        result = register(username, password)
        if result["status"] == "success":
            login_result = login(username, password)
            if login_result["status"] == "success":
                auth_state.remember_login(username, login_result["session_cookie"])
                st.session_state.redirect_to = "pages/my_accounts.py"
                st.rerun()
            else:
                st.success(f"Account created for {result['username']}. You can now log in.")
                st.error(login_result.get("message", "Auto-login failed."))
        else:
            st.error(result["message"])

    st.caption("Already have an account?")
    st.page_link("pages/login.py", label="Log in here")
