import streamlit as st

from api_client import (
    get_trades,
    get_trades_by_account,
    get_trades_by_ticker,
    get_trades_by_account_and_ticker,
    get_trade_by_id,
    update_trade,
)


def render_all_trades_page():
    st.header("📜 Trade History")
    st.caption("GET /trades")

    if st.button("Load Trades"):
        result = get_trades()
        if result["status"] == "success":
            if result["data"]:
                st.table(result["data"])
            else:
                st.info("No trades found.")
        else:
            st.error(result["message"])


def render_trades_by_account_page():
    st.header("📜 Trade History by Account")
    st.caption("GET /trades/account/{account_id}")

    account_id = st.text_input("Account ID")

    if st.button("Load Trades"):
        result = get_trades_by_account(account_id)
        if result["status"] == "success":
            if result["data"]:
                st.table(result["data"])
            else:
                st.info("No trades found.")
        else:
            st.error(result["message"])


def render_trades_by_ticker_page():
    st.header("📜 Trade History by Ticker")
    st.caption("GET /trades/ticker/{ticker}")

    ticker = st.text_input("Ticker", "AAPL")

    if st.button("Load Trades"):
        result = get_trades_by_ticker(ticker.upper())
        if result["status"] == "success":
            if result["data"]:
                st.table(result["data"])
            else:
                st.info("No trades found.")
        else:
            st.error(result["message"])


def render_trades_by_account_and_ticker_page():
    st.header("📜 Trade History by Account & Ticker")
    st.caption("GET /trades/account/{account_id}/ticker.{ticker}")

    account_id = st.text_input("Account ID")
    ticker = st.text_input("Ticker", "AAPL")

    if st.button("Load Trades"):
        result = get_trades_by_account_and_ticker(account_id, ticker.upper())
        if result["status"] == "success":
            if result["data"]:
                st.table(result["data"])
            else:
                st.info("No trades found.")
        else:
            st.error(result["message"])


def render_trade_by_id_page():
    st.header("🔍 Look Up Trade by ID")
    st.caption("GET /trades/{trade_id}")

    trade_id = st.text_input("Trade ID")

    if st.button("Load Trade"):
        result = get_trade_by_id(trade_id)
        if result["status"] == "success":
            st.json(result["data"])
        else:
            st.error(result["message"])


def render_update_trade_page():
    st.header("✏️ Edit Trade")
    st.caption("PUT /trades/{trade_id}")
    st.caption("This endpoint doesn't exist in the backend yet -- showing mock data.")

    trade_id = st.text_input("Trade ID")
    symbol = st.text_input("New Symbol")
    side = st.selectbox("New Side", ["BUY", "SELL"])
    quantity = st.number_input("New Quantity", min_value=1)
    price = st.number_input("New Price", min_value=0.01)

    if st.button("Update Trade"):
        data = {
            "symbol": symbol.upper(),
            "side": side,
            "quantity": quantity,
            "price": price,
        }
        result = update_trade(trade_id, data)
        st.json(result)
