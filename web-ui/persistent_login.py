import streamlit as st
import streamlit.components.v1 as components


def restore_login_from_browser():
    if st.session_state.get("username") and st.session_state.get("saved_session_cookie"):
        return

    remembered_user = st.query_params.get("remember_user")
    remembered_session = st.query_params.get("remember_session")

    if remembered_user and remembered_session:
        st.session_state.username = remembered_user
        st.session_state.saved_session_cookie = remembered_session

        #del st.query_params["remember_user"]
        #del st.query_params["remember_session"]
        st.rerun()
        return

    components.html(

        """

        <script>

        (function() {

            let username = null;

            let sessionCookie = null;

            try {

                username = window.top.localStorage.getItem("eq_username");

                sessionCookie = window.top.localStorage.getItem("eq_session");

            } catch (e) {

                username = window.localStorage.getItem("eq_username");

                sessionCookie = window.localStorage.getItem("eq_session");

            }

            if (!username || !sessionCookie) {

                return;

            }

            const topUrl = new URL(window.top.location.href);

            topUrl.searchParams.set("remember_user", username);

            topUrl.searchParams.set("remember_session", sessionCookie);

            window.top.location.href = topUrl.toString();

        })();

        </script>

        """,

        height=0,

    )


def remember_login(username, session_cookie):
    components.html(
        f"""
        <script>
        window.localStorage.setItem("eq_username", {username!r});
        window.localStorage.setItem("eq_session", {session_cookie!r});
        </script>
        """,
        height=0,
    )


def forget_login():
    components.html(
        """
        <script>
        window.localStorage.removeItem("eq_username");
        window.localStorage.removeItem("eq_session");
        </script>
        """,
        height=0,
    )