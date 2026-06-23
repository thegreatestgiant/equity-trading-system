import streamlit as st

from api_client import (
    get_all_positions,
    get_positions_by_account,
    get_positions_by_ticker,
    get_positions_by_account_and_ticker,
)


def render_all_positions_page():
    st.header("📊 All Positions")
    st.caption("GET /positions")

    if st.button("Load Positions"):
        result = get_all_positions()
        if result["status"] == "success":
            if result["data"]:
                st.json(result["data"])
            else:
                st.info("No positions yet. Book a trade to see positions here.")
        else:
            st.error(result["message"])


def render_positions_by_account_page():
    st.header("📊 Positions by Account")
    st.caption("GET /positions/accounts/{account_id}")

    prefilled = st.session_state.pop("jump_to_account", "")
    account_id = st.text_input("Account ID", value=prefilled)

    if st.button("Load Positions"):
        result = get_positions_by_account(account_id)
        if result["status"] == "success":
            st.json(result["data"])
        else:
            st.error(result["message"])


def render_positions_by_ticker_page():
    st.header("📊 Positions by Ticker")
    st.caption("GET /positions/ticker/{ticker}")

    ticker = st.text_input("Ticker", "AAPL")

    if st.button("Load Positions"):
        result = get_positions_by_ticker(ticker.upper())
        if result["status"] == "success":
            st.json(result["data"])
        else:
            st.error(result["message"])


def render_positions_by_account_and_ticker_page():
    st.header("📊 Positions by Account & Ticker")
    st.caption("GET /positions/accounts/{account_id}/ticker/{ticker}")

    account_id = st.text_input("Account ID")
    ticker = st.text_input("Ticker", "AAPL")

    if st.button("Load Position"):
        result = get_positions_by_account_and_ticker(account_id, ticker.upper())
        if result["status"] == "success":
            st.json(result["data"])
        else:
            st.error(result["message"])
