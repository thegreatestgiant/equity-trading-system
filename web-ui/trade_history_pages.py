import streamlit as st
import datetime
from api_client import (
    get_trades,
    get_trades_by_account,
    get_trades_by_ticker,
    get_trades_by_account_and_ticker,
    get_trade_by_id,
    update_trade,
)

from trades_grid import flatten_trades, render_trades_grid

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

    data = result["data"]
    # GET /trades now returns {"trades": [...], "next_cursor": {...} | None}
    trades = data.get("trades", []) if isinstance(data, dict) else data

    if not trades:
        st.info("No trades found.")
        return

    for trade in trades:
        _trade_card(trade)


@st.fragment(run_every="6s")
def _all_trades_fragment():
    account_id = st.session_state.get("trades_account_filter")
    ticker = st.session_state.get("trades_ticker_filter")
    time_start = st.session_state.get("trades_date_from_filter")
    time_end = st.session_state.get("trades_date_to_filter")
    result = get_trades(account_id=account_id, ticker=ticker, time_start=time_start, time_end=time_end)
    if result["status"] != "success":
        st.error(result["message"])
        return
    rows = flatten_trades(result["data"])
    render_trades_grid(
        rows,
        empty_message="No trades found.",
        key="all_trades_grid",
    )


def render_all_trades_page():
    st.header("📜 Trade History")
    st.caption("GET /trades")
    col1, col2 = st.columns(2)
    with col1:
        account_id = account_select(label="Account (optional)", key="trades_page_filter_account")
    with col2:
        ticker = st.text_input("Ticker (optional)", key="trades_page_filter_ticker").strip().upper() or None
    col3, col4 = st.columns(2)
    with col3:
        date_from = st.date_input("From", value=datetime.date.today() - datetime.timedelta(days=30),
                                  key="trades_page_filter_from")
    with col4:
        date_to = st.date_input("To (optional)", value=None, key="trades_page_filter_to")
    time_start = date_from.isoformat() if date_from else None
    time_end = date_to.isoformat() if date_to else None
    st.session_state["trades_account_filter"] = account_id
    st.session_state["trades_ticker_filter"] = ticker
    st.session_state["trades_date_from_filter"] = time_start
    st.session_state["trades_date_to_filter"] = time_end
    if not account_id and not ticker and not time_start and not time_end:
        st.info("Select an account, enter a ticker, or pick a date range to load trades.")
        return
    _all_trades_fragment()


@st.fragment(run_every="15s")
def _trades_by_account_fragment(account_id):
    _render_trades_table(get_trades_by_account(account_id))


def render_trades_by_account_page():
    st.header("📜 Trade History by Account")
    st.caption("GET /trades?account_id={account_id}")

    account_id = account_select()

    # Auto-loads (and keeps polling) as soon as an account is selected.
    if account_id:
        _trades_by_account_fragment(account_id)


@st.fragment(run_every="15s")
def _trades_by_ticker_fragment(ticker):
    _render_trades_table(get_trades_by_ticker(ticker))


def render_trades_by_ticker_page():
    st.header("📜 Trade History by Ticker")
    st.caption("GET /trades?ticker={ticker}")

    with st.form("trades_by_ticker_form"):
        ticker = st.text_input("Ticker", "AAPL")
        submitted = st.form_submit_button("Load Trades")

    if submitted:
        st.session_state.trades_by_ticker_query = ticker.upper()

    query = st.session_state.get("trades_by_ticker_query")
    if query:
        _trades_by_ticker_fragment(query)


@st.fragment(run_every="15s")
def _trades_by_account_and_ticker_fragment(account_id, ticker):
    _render_trades_table(get_trades_by_account_and_ticker(account_id, ticker))


def render_trades_by_account_and_ticker_page():
    st.header("📜 Trade History by Account & Ticker")
    st.caption("GET /trades?account_id={account_id}&ticker={ticker}")

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

    trade = result["data"]
    if not trade:
        st.info("No trade found with that ID.")
        return

    _trade_card(trade)


def render_trade_by_id_page():
    st.header("🔍 Look Up Trade by ID")
    st.caption("GET /trade/{trade_id}")

    with st.form("trade_by_id_form"):
        trade_id = st.text_input("Trade ID")
        submitted = st.form_submit_button("Load Trade")

    if submitted:
        st.session_state.trade_by_id_query = trade_id

    query = st.session_state.get("trade_by_id_query")
    if query:
        _trade_by_id_fragment(query)


def render_update_trade_page():
    st.header("✏️ Edit Trade")
    st.caption("PATCH /edit_trade/{trade_id}")

    with st.form("load_trade_for_edit_form"):
        trade_id_input = st.text_input(
            "Trade ID", value=st.session_state.get("editing_trade_id", "")
        )
        load_clicked = st.form_submit_button("Load Trade")

    if load_clicked:
        result = get_trade_by_id(trade_id_input)
        if result["status"] == "success" and result["data"]:
            st.session_state.editing_trade_id = trade_id_input
            st.session_state.editing_trade_data = result["data"]
        else:
            st.session_state.editing_trade_data = None
            st.error(result.get("message", "Trade not found."))

    loaded = st.session_state.get("editing_trade_data")
    if not loaded:
        return

    st.divider()
    st.caption(f"Editing trade `{st.session_state.editing_trade_id}`")

    with st.form("update_trade_form"):
        account_id = account_select(
            preselect_account_id=loaded.get("account_id"),
            key="update_trade_account_select",
        )
        ticker = st.text_input("Ticker", value=loaded.get("symbol_ticker", ""))
        direction_is_sell = st.toggle(
            "Sell (off = Buy)", value=(loaded.get("direction") == "Sell")
        )
        direction = "Sell" if direction_is_sell else "Buy"
        st.caption(f"Direction: **{direction}**")
        quantity = st.number_input(
            "Quantity", min_value=1, step=1, value=int(loaded.get("quantity", 1))
        )
        price = st.number_input(
            "Price", min_value=0.01, value=float(loaded.get("price", 0.01))
        )
        other_account = st.text_input(
            "Other Account (optional)", value=loaded.get("other_account") or ""
        )
        submitted = st.form_submit_button("Update Trade")

    if submitted:
        if not account_id or not ticker:
            st.error("Account and Ticker are required.")
            return

        payload = {
            "account_id": account_id,
            "ticker": ticker.upper(),
            "direction": direction,
            "quantity": int(quantity),
            "price": str(price),
            "other_account": other_account or None,
        }
        result = update_trade(st.session_state.editing_trade_id, payload)

        if result["status"] == "success":
            st.success(f"Trade `{st.session_state.editing_trade_id}` updated successfully.")
            st.session_state.editing_trade_data = None
        else:
            st.error(result["message"])