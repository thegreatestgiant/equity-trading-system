import streamlit as st

from api_client import login, register


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
            st.success("Logged in")
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
            st.success(f"Account created for {result['username']}. You can now log in.")
        else:
            st.error(result["message"])
