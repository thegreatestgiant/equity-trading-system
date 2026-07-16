import json
import os
import time
import urllib.parse

import streamlit as st
from streamlit_cookies_controller import CookieController

# Only mark cookies Secure once the app is actually served over HTTPS --
# the streamlit ingress is plain HTTP today (see k8s/manifests/base/apps/
# streamlit/ingress.yaml), and a Secure cookie is silently dropped by the
# browser over HTTP, which would break "stay logged in on reload". Flip
# this on via env var once TLS is in front of streamlit, no code change
# needed.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"

def _get_cookie_controller():
    if "cookie_controller" not in st.session_state:
        st.session_state.cookie_controller = CookieController()
    return st.session_state.cookie_controller

def get_session_cookie():
    return st.session_state.get("saved_session_cookie")

def get_username():
    return st.session_state.get("username")

def remember_login(username, session_cookie):
    controller = _get_cookie_controller()
    controller.set("eq_username", username, path="/", secure=COOKIE_SECURE, same_site="strict")
    controller.set("eq_session", session_cookie, path="/", secure=COOKIE_SECURE, same_site="strict")
    st.session_state.username = username
    st.session_state.saved_session_cookie = session_cookie
    st.session_state.session_validated = True

def forget_login():
    controller = _get_cookie_controller()
    try:
        controller.remove("eq_username", secure=COOKIE_SECURE, same_site="strict")
    except KeyError:
        pass
    try:
        controller.remove("eq_session", secure=COOKIE_SECURE, same_site="strict")
    except KeyError:
        pass
    st.session_state.username = None
    st.session_state.saved_session_cookie = None
    st.session_state.session_validated = False


def _decode_cookie(val):
    if not val: return val
    try:
        val = urllib.parse.unquote(val)
        if val.startswith('"') and val.endswith('"'):
            val = json.loads(val)
    except Exception:
        pass
    return val

def init_auth():
    # st.context.cookies reads straight from the incoming HTTP request
    # headers -- it's synchronous and always correct on the very first
   # script run of a fresh session. But it's a SNAPSHOT of that one
   # request: it does not update when a cookie changes mid-session via
   # CookieController (forget_login/remember_login), since those don't
   # trigger a new HTTP request. So this restore-from-cookie step must
   # only run once per live session -- otherwise, after forget_login()
   # clears username and triggers a rerun, this would immediately read
   # the still-stale (pre-logout) cookie snapshot and undo the logout
   # on the very next run. A real reload starts a fresh session, so
   # the flag below resets and the restore correctly re-runs against
   # that new request's actual current cookies.
    if not st.session_state.get("_cookie_restore_attempted"):
        st.session_state._cookie_restore_attempted = True
        cookie_user = _decode_cookie(st.context.cookies.get("eq_username"))
        cookie_session = _decode_cookie(st.context.cookies.get("eq_session"))

        if st.session_state.get("username") is None and cookie_user:
            st.session_state.username = cookie_user
            st.session_state.saved_session_cookie = cookie_session
            st.session_state.session_validated = False

    if not get_session_cookie() or not get_username():
        st.session_state.username = None
        st.session_state.saved_session_cookie = None

def render_user_sidebar(sections=None):
    username = get_username()
    if username:
        for title, pages in (sections or []):
            st.sidebar.caption(title.upper())
            for p in pages:
                st.sidebar.page_link(p)
            st.sidebar.markdown("")
        st.sidebar.divider()
        st.sidebar.markdown(f"👤 **{username}**")
        if st.sidebar.button("🚪 Log Out", use_container_width=True):
            from api_client import logout
            logout()
            forget_login()
            time.sleep(0.5)
            st.rerun()

def require_auth():
    if not get_username():
        st.switch_page("pages/login.py")
