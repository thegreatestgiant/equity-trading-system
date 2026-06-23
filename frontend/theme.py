import streamlit as st


def apply_theme():
    """Injects the app's custom CSS (blue gradient sidebar, card styling,
    primary button colors, etc). Theme-aware: provides separate color
    values for light and dark mode so nothing renders invisible (e.g.
    white text on a white background) when the user switches themes.
    Call once near the top of app_ui.py."""
    st.markdown(
        """
        <style>
        :root {
            --eq-blue-50:  #eef6ff;
            --eq-blue-100: #dbeeff;
            --eq-blue-200: #b9deff;
            --eq-blue-400: #5aa9ea;
            --eq-blue-500: #2f86d6;
            --eq-blue-700: #1c5e9e;

            /* Light-mode defaults */
            --eq-app-bg: var(--eq-blue-50);
            --eq-header-color: var(--eq-blue-700);
            --eq-card-bg: #ffffff;
            --eq-card-border: var(--eq-blue-200);
            --eq-card-text: #1a1a1a;
            --eq-sidebar-grad-start: var(--eq-blue-700);
            --eq-sidebar-grad-end: var(--eq-blue-500);
            --eq-sidebar-text: #ffffff;
        }

        /* Dark-mode overrides -- Streamlit sets data-theme="dark" on the
           root html element when the user picks Dark (or System resolves
           to dark). Override just the values that need to change instead
           of hard-coding colors that only work in one mode. */
        [data-theme="dark"] {
            --eq-app-bg: #0e1117;
            --eq-header-color: var(--eq-blue-400);
            --eq-card-bg: #1c2128;
            --eq-card-border: var(--eq-blue-500);
            --eq-card-text: #f0f2f6;
            --eq-sidebar-grad-start: #0d2b46;
            --eq-sidebar-grad-end: #1c5e9e;
            --eq-sidebar-text: #f0f2f6;
        }

        .stApp {
            background-color: var(--eq-app-bg);
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--eq-sidebar-grad-start) 0%, var(--eq-sidebar-grad-end) 100%);
        }
        section[data-testid="stSidebar"] * {
            color: var(--eq-sidebar-text) !important;
        }
        section[data-testid="stSidebar"] .stRadio [data-baseweb="radio"] {
            background-color: rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 6px 10px;
            margin-bottom: 4px;
        }
        section[data-testid="stSidebar"] .stRadio [data-baseweb="radio"]:hover {
            background-color: rgba(255, 255, 255, 0.18);
        }
        section[data-testid="stSidebar"] .stButton button {
            background-color: rgba(255, 255, 255, 0.12);
            color: var(--eq-sidebar-text);
            border: 1px solid rgba(255, 255, 255, 0.35);
            border-radius: 8px;
        }
        section[data-testid="stSidebar"] .stButton button:hover {
            background-color: rgba(255, 255, 255, 0.25);
            border-color: #ffffff;
        }
        section[data-testid="stSidebar"] hr {
            border-color: rgba(255, 255, 255, 0.25);
        }

        /* Main content headers */
        h1, h2, h3 {
            color: var(--eq-header-color);
        }

        /* Primary buttons in main content */
        .stButton button[kind="primary"] {
            background-color: var(--eq-blue-500);
            border-color: var(--eq-blue-500);
            color: #ffffff;
        }
        .stButton button[kind="primary"]:hover {
            background-color: var(--eq-blue-700);
            border-color: var(--eq-blue-700);
        }

        /* Cards (st.container(border=True)) */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--eq-card-border) !important;
            background-color: var(--eq-card-bg);
            color: var(--eq-card-text);
            border-radius: 10px;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] * {
            color: var(--eq-card-text);
        }

        /* Text inputs / number inputs -- ensure visible borders and text
           in both themes instead of relying on Streamlit defaults that
           can render low-contrast against our custom backgrounds. */
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input {
            border: 1px solid var(--eq-card-border);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )