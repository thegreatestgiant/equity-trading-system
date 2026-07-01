import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from account_picker import get_account_name
from market_data import get_current_price


def _format_timestamp(value):
    import datetime
    try:
        return datetime.datetime.fromisoformat(str(value)).strftime("%b %d, %Y %I:%M %p")
    except (TypeError, ValueError):
        try:
            return datetime.datetime.fromtimestamp(float(value)).strftime("%b %d, %Y %I:%M %p")
        except (TypeError, ValueError):
            return str(value)


def _position_row(position, account_id=None):
    """Builds one flat row dict from a single position dict."""
    ticker = position.get("symbol_ticker")
    quantity = position.get("quantity")
    price = get_current_price(ticker)
    total_value = price * quantity if (price is not None and quantity is not None) else None

    return {
        "Account": get_account_name(account_id) if account_id else "—",
        "Account ID": account_id or "—",
        "Ticker": ticker or "—",
        "Quantity": quantity,
        "Price/Share": round(price, 2) if price is not None else None,
        "Total Value": round(total_value, 2) if total_value is not None else None,
        "Updated": _format_timestamp(position.get("updated_at")),
    }


def flatten_positions(data):
    """STEP 1: Takes the raw 'data' value from any positions endpoint
    result and returns a flat list of row dicts, one per position,
    regardless of which shape the backend used.

    Shapes handled (mirrors _normalize_positions / _render_positions_result
    in api_client.py / positions_pages.py):
      - list of position dicts (already flat -- account known elsewhere)
      - dict of {account_id: [position dicts]}
      - dict of {account_id: single position dict}
      - single bare position dict (has 'symbol_ticker' directly)
    """
    if not data:
        return []

    if isinstance(data, list):
        return [_position_row(p) for p in data]

    if isinstance(data, dict) and "symbol_ticker" in data:
        return [_position_row(data)]

    if isinstance(data, dict):
        rows = []
        for key, value in data.items():
            if isinstance(value, list):
                rows.extend(_position_row(p, account_id=key) for p in value)
            elif isinstance(value, dict):
                rows.append(_position_row(value, account_id=key))
        return rows

    return []


def render_positions_grid(rows, empty_message="No positions found.", key="positions_grid"):
    """STEP 2: Renders a list of row dicts (from flatten_positions) as
    an interactive AgGrid. Pass a unique `key` if rendering more than
    one grid on the same page."""
    if not rows:
        st.info(empty_message)
        return

    df = pd.DataFrame(rows)
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(sortable=True, filter=True, resizable=True)
    gb.configure_pagination(paginationAutoPageSize=True)
    grid_options = gb.build()

    AgGrid(
        df,
        gridOptions=grid_options,
        fit_columns_on_grid_load=True,
        update_mode=GridUpdateMode.NO_UPDATE,
        key=key,
    )

    # Force a rerun on first load so AgGrid JS has time to initialize.
    # Without this the grid renders blank on first visit and only appears
    # after a manual reload.
    first_load_key = f"{key}_initialized"
    if not st.session_state.get(first_load_key):
        st.session_state[first_load_key] = True
        st.rerun()