import pandas as pd
import streamlit as st
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

    # New GET /trades shape: {"trades": [...], "next_cursor": {...} | None}
    # Unwrap it first so everything below still works unchanged.
    if isinstance(data, dict) and "trades" in data:
        data = data["trades"]

    if not data:
        return []

    if isinstance(data, list):
        return [_trade_row(t) for t in data]

    # Single bare trade dict (e.g. from GET /trade/{trade_id})
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

    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
    from st_aggrid.shared import JsCode
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(sortable=True, filter=True, resizable=True)
    gb.configure_pagination(paginationAutoPageSize=True)

    # AgGrid's date filter compares the filter's chosen date against
    # each cell value using this comparator. cellValue arrives as an
    # ISO-ish datetime string (from pandas), so parse it back into a
    # Date before comparing against filterLocalDateAtMidnight.
    date_comparator = JsCode(
        """
        function(filterLocalDateAtMidnight, cellValue) {
            if (!cellValue) return -1;
            const cellDate = new Date(cellValue);
            const cellDateAtMidnight = new Date(
                cellDate.getFullYear(), cellDate.getMonth(), cellDate.getDate()
            );
            if (cellDateAtMidnight < filterLocalDateAtMidnight) return -1;
            if (cellDateAtMidnight > filterLocalDateAtMidnight) return 1;
            return 0;
        }
        """
    )

    # Sort most recent first by default, and enable a date-range filter
    # (adds an "in range" option with a from/to date picker).
    gb.configure_column(
        "Booked At",
        sort="desc",
        type=["customDateTimeFormat"],
        custom_format_string="MMM dd, yyyy HH:mm",
        filter="agDateColumnFilter",
        filterParams={
            "comparator": date_comparator,
            "browserDatePicker": True,
        },
    )
    gb.configure_grid_options(enableCellTextSelection=True, ensureDomOrder=True)

    grid_options = gb.build()

    AgGrid(
        df,
        gridOptions=grid_options,
        fit_columns_on_grid_load=True,
        update_mode=GridUpdateMode.NO_UPDATE,
        allow_unsafe_jscode=True,  # required for the Booked At date comparator
        # The page this grid lives on auto-refreshes every few seconds
        # (st.fragment(run_every=...)). That's intentional -- but AgGrid's
        # own loading overlay flashes on every single one of those
        # refreshes, which looks like a visual bug even though the data
        # really is updating correctly underneath. Suppress just the
        # overlay so refreshes are invisible instead of flickery.
        custom_css={
            ".ag-overlay-loading-center": {"display": "none !important"},
            ".ag-overlay-wrapper": {"background-color": "transparent !important"},
        },
        # Without this, every 6s auto-refresh (st.fragment run_every) makes
        # AgGrid tear down and rebuild its whole client-side grid/JS state
        # from scratch instead of just patching in new rows -- that's what
        # was racing against the refresh interval and causing the "trouble
        # loading the component" failures. reload_data=False keeps the grid
        # instance alive across reruns and only updates its data in place.
        reload_data=False,
        key=key,
    )

    # Force a rerun on first load so AgGrid JS has time to initialize.
    # Without this the grid renders blank on first visit and only appears
    # after a manual reload.
    first_load_key = f"{key}_initialized"
    if not st.session_state.get(first_load_key):
        st.session_state[first_load_key] = True
        st.rerun()