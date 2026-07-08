import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from account_picker import get_account_name

def _trade_row(trade):
    """Builds one flat row dict from a single position dict."""
    ticker = trade.get("symbol_ticker") or trade.get("ticker", "—")

    return {
        "Booked At": trade.get("created_at"),
        "Ticker": ticker,
        "Direction": trade.get("direction", "—"),
        "Quantity": trade.get("quantity", "—"),
        "Price": trade.get("price", "—"),
        "Account": get_account_name(trade.get("account_id")),
        "Trade ID": trade.get("trade_id", "—"),
    }

def flatten_trades(data):
    if not data:
        return []

    if isinstance(data, list):
        return [_trade_row(t) for t in data]

    # Single bare trade dict (edge case, probably never happens)
    if isinstance(data, dict) and "trade_id" in data:
        return [_trade_row(data)]

    return []



def render_trades_grid(rows, empty_message="No trades found.", key="trades_grid"):
    if not rows:
        st.info(empty_message)
        return

    df = pd.DataFrame(rows)

    # Parse Booked At as datetime so AgGrid sorts it correctly
    # rather than as a raw string. Keep original for display.
    if "Booked At" in df.columns:
        df["Booked At"] = pd.to_datetime(df["Booked At"], errors="coerce")

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(sortable=True, filter=True, resizable=True)
    gb.configure_pagination(paginationAutoPageSize=True)

    # Sort most recent first by default
    gb.configure_column(
        "Booked At",
        sort="desc",
        type=["customDateTimeFormat"],
        custom_format_string="MMM dd, yyyy HH:mm",
    )

    grid_options = gb.build()

    AgGrid(
        df,
        gridOptions=grid_options,
        fit_columns_on_grid_load=True,
        update_mode=GridUpdateMode.NO_UPDATE,
        key=key,
    )

    # # Force a rerun on first load so AgGrid JS has time to initialize.
    # # Without this the grid renders blank on first visit and only appears
    # # after a manual reload.
    # first_load_key = f"{key}_initialized"
    # if not st.session_state.get(first_load_key):
    #     st.session_state[first_load_key] = True
    #     st.rerun()