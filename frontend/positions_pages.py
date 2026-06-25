import datetime

import streamlit as st

from api_client import (
    get_all_positions,
    get_positions_by_account,
    get_positions_by_ticker,
    get_positions_by_account_and_ticker,
)
from account_picker import account_select, get_account_name


def _format_timestamp(value):
    """Backend sends ISO timestamps -- show them more compactly."""
    try:
        return datetime.datetime.fromisoformat(str(value)).strftime("%b %d, %Y %I:%M %p")
    except (TypeError, ValueError):
        try:
            return datetime.datetime.fromtimestamp(float(value)).strftime("%b %d, %Y %I:%M %p")
        except (TypeError, ValueError):
            return str(value)


def _position_card(position, account_id=None):
    with st.container(border=True):
        cols = st.columns([2, 2, 2, 3])
        cols[0].write(f"**{position.get('symbol_ticker', '—')}**")
        cols[1].write(f"Qty: {position.get('quantity', '—')}")
        if account_id:
            cols[2].caption(f"Account: {get_account_name(account_id)}")
        cols[3].caption(f"Updated {_format_timestamp(position.get('updated_at'))}")


def _render_positions_result(result, empty_message="No positions found.", account_id=None):
    """Renders positions as readable cards instead of raw JSON.

    Different endpoints return different shapes:
    - GET /positions, /positions/ticker/{ticker}: {account_id: [position, ...]}
    - GET /positions/accounts/{account_id}, .../ticker/{ticker}: a flat
      list of positions directly, since the account is already known
      from the URL and doesn't need to be repeated as a dict key.

    account_id: when the account is already known (i.e. the caller is on
    a "by account" page), pass it through so each card can show the
    account's display name instead of nothing at all.
    """
    if result["status"] != "success":
        st.error(result["message"])
        return

    data = result["data"]

    if not data:
        st.info(empty_message)
        return

    if isinstance(data, list):
        # Flat list shape -- account is already known from the URL.
        for position in data:
            _position_card(position, account_id=account_id)
        return

    if isinstance(data, dict) and "symbol_ticker" in data:
        # Single position dict, not wrapped in a list or grouped at all.
        _position_card(data, account_id=account_id)
        return

    # Dict-of-accounts shape (or dict-of-tickers with single positions)
    for key, value in data.items():
        if isinstance(value, dict):
            # value is itself a single position dict (e.g. keyed by ticker)
            _position_card(value, account_id=key if key != value.get("symbol_ticker") else account_id)
            continue

        positions = value
        account_label = get_account_name(key)
        st.subheader(account_label)

        for position in positions:
            _position_card(position, account_id=key)

        st.divider()


@st.fragment(run_every="15s")
def _all_positions_fragment():
    _render_positions_result(
        get_all_positions(),
        empty_message="No positions yet. Book a trade to see positions here.",
    )


def render_all_positions_page():
    st.header("📊 All Positions")
    st.caption("GET /positions")
    # Loads immediately and keeps polling -- no button needed.
    _all_positions_fragment()


@st.fragment(run_every="15s")
def _positions_by_account_fragment(account_id):
    _render_positions_result(get_positions_by_account(account_id), account_id=account_id)


def render_positions_by_account_page():
    st.header("📊 Positions by Account")
    st.caption("GET /positions/accounts/{account_id}")

    prefilled = st.session_state.pop("jump_to_account", None)
    account_id = account_select(preselect_account_id=prefilled)

    if account_id:
        _positions_by_account_fragment(account_id)


@st.fragment(run_every="15s")
def _positions_by_ticker_fragment(ticker):
    _render_positions_result(get_positions_by_ticker(ticker))


def render_positions_by_ticker_page():
    st.header("📊 Positions by Ticker")
    st.caption("GET /positions/ticker/{ticker}")

    ticker = st.text_input("Ticker", "AAPL")

    if ticker:
        _positions_by_ticker_fragment(ticker.upper())


@st.fragment(run_every="15s")
def _positions_by_account_and_ticker_fragment(account_id, ticker):
    _render_positions_result(
        get_positions_by_account_and_ticker(account_id, ticker), account_id=account_id
    )


def render_positions_by_account_and_ticker_page():
    st.header("📊 Positions by Account & Ticker")
    st.caption("GET /positions/accounts/{account_id}/ticker/{ticker}")

    account_id = account_select(key="pos_acct_ticker_select")
    ticker = st.text_input("Ticker", "AAPL")

    if account_id and ticker:
        _positions_by_account_and_ticker_fragment(account_id, ticker.upper())