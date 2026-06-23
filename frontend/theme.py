import streamlit as st


def apply_theme():
    """Injects the app's custom CSS (blue gradient sidebar, card styling,
    primary button colors, etc). Call once near the top of app_ui.py."""
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
        }

        .stApp {
            background-color: var(--eq-blue-50);
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--eq-blue-700) 0%, var(--eq-blue-500) 100%);
        }
        section[data-testid="stSidebar"] * {
            color: #ffffff !important;
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
            color: #ffffff;
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
            color: var(--eq-blue-700);
        }

        /* Primary buttons in main content */
        .stButton button[kind="primary"] {
            background-color: var(--eq-blue-500);
            border-color: var(--eq-blue-500);
        }
        .stButton button[kind="primary"]:hover {
            background-color: var(--eq-blue-700);
            border-color: var(--eq-blue-700);
        }

        /* Cards (st.container(border=True)) */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--eq-blue-200) !important;
            background-color: #ffffff;
            border-radius: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
