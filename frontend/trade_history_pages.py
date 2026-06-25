import streamlit as st

from api_client import (
    get_trades,
    get_trades_by_account,
    get_trades_by_ticker,
    get_trades_by_account_and_ticker,
    get_trade_by_id,
    update_trade,
)
from account_picker import account_select, get_account_name


def _trade_card(trade):
    ticker = trade.get("symbol_ticker") or trade.get("ticker", "—")
    with st.container(border=True):
        cols = st.columns([3, 2, 2])
        cols[0].write(f"**{trade.get('direction', '—')} {ticker}**")
        cols[1].write(f"Qty: {trade.get('quantity', '—')}")
        cols[2].write(f"${trade.get('price', '—')}")

        cols2 = st.columns([2, 3])
        cols2[0].caption(f"Account: {get_account_name(trade.get('account_id'))}")
        if trade.get("trade_id"):
            cols2[1].caption(f"Trade ID: {trade['trade_id']}")

        if trade.get("created_at"):
            st.caption(f"Booked: {trade['created_at']}")


def _render_trades_table(result):
    if result["status"] != "success":
        st.error(result["message"])
        return

    trades = result["data"]
    if not trades:
        st.info("No trades found.")
        return

    for trade in trades:
        _trade_card(trade)


@st.fragment(run_every="15s")
def _all_trades_fragment():
    _render_trades_table(get_trades())


def render_all_trades_page():
    st.header("📜 Trade History")
    st.caption("GET /trades")
    # No filters needed -- loads immediately and refreshes automatically,
    # so trades booked from another tab show up here without a manual reload.
    _all_trades_fragment()


@st.fragment(run_every="15s")
def _trades_by_account_fragment(account_id):
    _render_trades_table(get_trades_by_account(account_id))


def render_trades_by_account_page():
    st.header("📜 Trade History by Account")
    st.caption("GET /trades/account/{account_id}")

    account_id = account_select()

    # Auto-loads (and keeps polling) as soon as an account is selected.
    if account_id:
        _trades_by_account_fragment(account_id)


@st.fragment(run_every="15s")
def _trades_by_ticker_fragment(ticker):
    _render_trades_table(get_trades_by_ticker(ticker))


def render_trades_by_ticker_page():
    st.header("📜 Trade History by Ticker")
    st.caption("GET /trades/ticker/{ticker}")

    ticker = st.text_input("Ticker", "AAPL")

    if st.button("Load Trades"):
        st.session_state.trades_by_ticker_query = ticker.upper()

    query = st.session_state.get("trades_by_ticker_query")
    if query:
        _trades_by_ticker_fragment(query)


@st.fragment(run_every="15s")
def _trades_by_account_and_ticker_fragment(account_id, ticker):
    _render_trades_table(get_trades_by_account_and_ticker(account_id, ticker))


def render_trades_by_account_and_ticker_page():
    st.header("📜 Trade History by Account & Ticker")
    st.caption("GET /trades/account/{account_id}/ticker.{ticker}")

    account_id = account_select(key="trades_acct_ticker_select")
    ticker = st.text_input("Ticker", "AAPL")

    if account_id and ticker:
        _trades_by_account_and_ticker_fragment(account_id, ticker.upper())


@st.fragment(run_every="15s")
def _trade_by_id_fragment(trade_id):
    result = get_trade_by_id(trade_id)
    if result["status"] != "success":
        st.error(result["message"])
        return

    trades = result["data"]
    if not trades:
        st.info("No trade found with that ID.")
        return

    for trade in trades:
        _trade_card(trade)


def render_trade_by_id_page():
    st.header("🔍 Look Up Trade by ID")
    st.caption("GET /trades/{trade_id}")

    trade_id = st.text_input("Trade ID")

    if st.button("Load Trade"):
        st.session_state.trade_by_id_query = trade_id

    query = st.session_state.get("trade_by_id_query")
    if query:
        _trade_by_id_fragment(query)


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
        st.success(f"Trade `{result['trade_id']}` updated.")
        updated = result["updated"]
        st.caption(
            f"**{updated['side']} {updated['quantity']} {updated['symbol']}** "
            f"@ ${updated['price']}"
        )