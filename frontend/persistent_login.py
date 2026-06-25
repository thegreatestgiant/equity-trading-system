import streamlit as st
import streamlit.components.v1 as components


def restore_login_from_browser():
    """On a fresh page load (st.session_state.username is None), checks
    the browser's localStorage for a remembered username via a query
    param round-trip, and restores the logged-in view without making the
    user sign in again.

    This does NOT re-verify the session with the backend -- it just skips
    the login form. The backend's own cookie-based auth still enforces
    real access control on every API call, so if that cookie has expired,
    the first API call will fail and the user will be sent back to login
    at that point (handled in api_client.py callers via normal error
    handling)."""
    if st.session_state.get("username"):
        return  # already logged in this session, nothing to restore

    remembered = st.query_params.get("remember_user")
    if remembered:
        st.session_state.username = remembered
        # Clean the URL so the username isn't sitting in the address bar.
        del st.query_params["remember_user"]
        st.rerun()
        return

    # Ask the browser if it has a remembered username in localStorage.
    # If so, reload once with it attached as a query param so Python can
    # pick it up above.
    #
    # NOTE: this script runs inside an iframe (components.html), and that
    # iframe gets re-created on every Streamlit script run -- so its own
    # sessionStorage is not a reliable place to guard against a reload
    # loop (it can look "empty" again on the next run even though no
    # human-visible reload happened). Checking the *top-level* page's own
    # URL for the query param is reliable instead, since that's the thing
    # we're actually trying to avoid re-adding.
    components.html(
        """
        <script>
        (function() {
            const remembered = window.localStorage.getItem("eq_username");
            if (!remembered) { return; }

            const topUrl = new URL(window.top.location.href);
            if (topUrl.searchParams.has("remember_user")) {
                return;  // already in the URL -- Python just hasn't processed it yet
            }

            topUrl.searchParams.set("remember_user", remembered);
            window.top.location.href = topUrl.toString();
        })();
        </script>
        """,
        height=0,
    )


def remember_login(username):
    """Call after a successful login/register to save the username in the
    browser's localStorage so a page reload doesn't require signing in
    again."""
    components.html(
        f"""
        <script>
        window.localStorage.setItem("eq_username", {username!r});
        </script>
        """,
        height=0,
    )


def forget_login():
    """Call on logout to clear the remembered browser login."""
    components.html(
        """
        <script>
        window.localStorage.removeItem("eq_username");
        </script>
        """,
        height=0,
    )