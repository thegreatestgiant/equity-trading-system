import streamlit as st
import auth_state
from theme import apply_theme

# We must set page config first
st.set_page_config(page_title="Equity Trading System", page_icon="📈", layout="wide")

apply_theme()
auth_state.init_auth()



print(f"DEBUG: Auth Check - Current username: {auth_state.get_username()}")
st.markdown('<style>#stDecoration {display: none;}</style>', unsafe_allow_html=True)

p_home = st.Page("pages/register.py", title="Register", icon="🏠", default=True)
p_login = st.Page("pages/login.py", title="Login", icon="🔑", url_path="login")

p_my_accounts = st.Page("pages/my_accounts.py", title="My Accounts", icon="🏦")
p_create_acc = st.Page("pages/open_account.py", title="Open Account", icon="➕")
p_edit_acc = st.Page("pages/edit_account.py", title="Edit Account", icon="✏️")

p_all_pos = st.Page("pages/positions.py", title="Positions", icon="📊")

p_trade_history = st.Page("pages/trade_history.py", title="Trade History", icon="📜")
p_book_a_trade = st.Page("pages/book_a_trade.py", title="Book a Trade", icon="💸")
p_mass_trade = st.Page("pages/mass_trade.py", title="Mass Trade", icon="📋")
p_edit_trade = st.Page("pages/edit_trade.py", title="Edit Trade", icon="✏️")

auth_sections = [
    ("Accounts", [p_my_accounts, p_create_acc, p_edit_acc]),
    ("Positions", [p_all_pos, p_trade_history]),
    ("Trading", [p_book_a_trade, p_mass_trade, p_edit_trade]),
]
auth_pages = [p for _, pages in auth_sections for p in pages]
all_pages = [p_home, p_login] + auth_pages

pg = st.navigation(all_pages, position="hidden")

auth_state.render_user_sidebar(auth_sections)

if "redirect_to" in st.session_state:
    redirect_page = st.session_state.pop("redirect_to")
    st.switch_page(redirect_page)

pg.run()
