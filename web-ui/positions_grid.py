import pandas as pd
import streamlit as st

from account_picker import get_account_name


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
    price = position.get("latest_price")

    total_value = position.get("position_value")
    if total_value is None and price is not None and quantity is not None:
        total_value = price * quantity

    return {
        "Account": get_account_name(account_id) if account_id else "—",
        "Account ID": account_id or "—",
        "Ticker": ticker or "—",
        "Quantity": quantity,
        "Price/Share": round(price, 2) if price is not None else None,
        "Total Value": round(total_value, 2) if total_value is not None else None,
        "Updated": _format_timestamp(position.get("updated_at")),
    }


def flatten_positions(data, account_id=None):
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
        return [_position_row(p, account_id=account_id) for p in data]

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

    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(sortable=True, filter=True, resizable=True)
    gb.configure_pagination(paginationAutoPageSize=True)
    gb.configure_grid_options(enableCellTextSelection=True, ensureDomOrder=True)
    grid_options = gb.build()

    print("AG-Grid loading for positions...")
    AgGrid(
        df,
        gridOptions=grid_options,
        fit_columns_on_grid_load=True,
        update_mode=GridUpdateMode.NO_UPDATE,
        # Without this, every 6s auto-refresh (st.fragment run_every) makes
        # AgGrid tear down and rebuild its whole client-side grid/JS state
        # from scratch instead of just patching in new rows -- that's what
        # was racing against the refresh interval and causing the "trouble
        # loading the component" failures. reload_data=False keeps the grid
        # instance alive across reruns and only updates its data in place.
        reload_data=False,
        key=key,
    )
    print("AG-Grid loaded for positions.")

    # Force a rerun on first load so AgGrid JS has time to initialize.
    # Without this the grid renders blank on first visit and only appears
    # after a manual reload.
    first_load_key = f"{key}_initialized"
    if not st.session_state.get(first_load_key):
        st.session_state[first_load_key] = True
        st.rerun()
