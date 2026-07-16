import streamlit as st
import concurrent.futures
import pandas as pd
import requests
from api_client import submit_trades, API_BASE_URL
from account_picker import get_account_options

EXPECTED_FIELDS = 5  # name, ticker, direction, quantity, price
VALID_DIRECTIONS = {"Buy", "Sell"}

EXAMPLE_TEXT = """My Retirement Account,AAPL,Buy,100,189.42
Trading Account,MSFT,Sell,50,415.00
My Retirement Account,GOOGL,Buy,200,175.30,other-account-id"""


def _resolve_accounts():
    """Returns a dict of {lowercased account name: account_id} for fast lookup."""
    _, label_to_id = get_account_options()
    # label_to_id keys look like "Name — uuid", so split on " — " to get name
    return {
        lbl.split(" — ")[0].strip().lower(): aid
        for lbl, aid in label_to_id.items()
    }


def _parse_line(line: str, line_num: int, name_to_id: dict) -> dict:
    """Parses one line into a trade row dict with a status field.
    Returns a dict with all fields plus 'Status' and '_valid' for grid coloring."""
    parts = [p.strip() for p in line.split(",")]

    if len(parts) < EXPECTED_FIELDS:
        return {
            "Line": line_num,
            "Account Name": parts[0] if parts else "",
            "Ticker": "",
            "Direction": "",
            "Quantity": "",
            "Price": "",
            "Other Account": "",
            "Status": f"Too few fields — expected at least {EXPECTED_FIELDS}, got {len(parts)}",
            "_valid": False,
            "_account_id": None,
        }

    account_name = parts[0]
    ticker = parts[1].upper()
    direction = parts[2].strip().capitalize()
    quantity_raw = parts[3]
    price_raw = parts[4]
    other_account = parts[5] if len(parts) > 5 else None

    errors = []

    # Resolve account name to ID
    account_id = name_to_id.get(account_name.strip().lower())
    if account_id is None:
        errors.append(f"Unknown account '{account_name}'")

    # Validate ticker
    if not ticker:
        errors.append("Ticker is required")

    # Validate direction
    if direction not in VALID_DIRECTIONS:
        errors.append(f"Direction must be Buy or Sell, got '{direction}'")

    # Validate quantity
    try:
        quantity = int(quantity_raw)
        if quantity <= 0:
            errors.append("Quantity must be a positive integer")
    except ValueError:
        quantity = quantity_raw
        errors.append(f"Quantity must be an integer, got '{quantity_raw}'")

    # Validate price
    try:
        price = float(price_raw)
        if price <= 0:
            errors.append("Price must be positive")
    except ValueError:
        price = price_raw
        errors.append(f"Price must be a number, got '{price_raw}'")

    valid = len(errors) == 0

    return {
        "Line": line_num,
        "Account Name": account_name,
        "Ticker": ticker,
        "Direction": direction,
        "Quantity": quantity,
        "Price": price,
        "Other Account": other_account or "",
        "Status": "✅ Valid" if valid else " | ".join(errors),
        "_valid": valid,
        "_account_id": account_id,
    }


def _parse_input(raw_text: str) -> list[dict]:
    """Splits raw text into lines and parses each one."""
    name_to_id = _resolve_accounts()
    rows = []
    for i, line in enumerate(raw_text.strip().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        rows.append(_parse_line(line, i, name_to_id))
    return rows


def _render_preview_grid(rows: list[dict]):
    """Renders parsed trades as an AgGrid with green/red row coloring
    based on validity."""
    df = pd.DataFrame(rows)

    # Drop internal columns before display
    display_df = df.drop(columns=["_valid", "_account_id"])
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

    gb = GridOptionsBuilder.from_dataframe(display_df)
    gb.configure_default_column(sortable=True, resizable=True)
    gb.configure_pagination(paginationAutoPageSize=True)

    # Color rows red/green based on Status column content
    row_style = JsCode("""
        function(params) {
            if (params.data.Status && params.data.Status.startsWith('\u2705')) {
                return { 'background-color': '#d4edda', 'color': '#155724' };
            } else {
                return { 'background-color': '#f8d7da', 'color': '#721c24' };
            }
        }
    """)

    gb.configure_grid_options(getRowStyle=row_style, enableCellTextSelection=True, ensureDomOrder=True)
    grid_options = gb.build()

    AgGrid(
        display_df,
        gridOptions=grid_options,
        fit_columns_on_grid_load=True,
        update_mode=GridUpdateMode.NO_UPDATE,
        allow_unsafe_jscode=True,
        key="mass_trade_preview_grid",
    )


def _submit_chunk_with_cookie(chunk, cookie):
    session = requests.Session()
    if cookie:
        session.cookies.set("session", cookie)
    try:
        response = session.post(f"{API_BASE_URL}/trade", json=chunk)
    except Exception:
        return {"status": "error", "message": "Could not reach the backend."}
    if response.status_code == 200:
        return {"status": "success", "data": response.json()}
    return {"status": "error", "message": response.text}


BATCH_SIZE = 25


def _submit_in_batches(payload):
    cookie = st.session_state.get("saved_session_cookie")

    chunks = []
    for i in range(0, len(payload), BATCH_SIZE):
        chunks.append(payload[i:i + BATCH_SIZE])

    all_successes = []
    all_failures = []
    errors = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_submit_chunk_with_cookie, chunk, cookie) for chunk in chunks]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result["status"] == "success":
                data = result["data"]
                all_successes.extend(data.get("successes", []))
                all_failures.extend(data.get("failures", []))
            else:
                errors.append(result["message"])

    if errors and not all_successes and not all_failures:
        return {"status": "error", "message": "; ".join(errors)}

    return {"status": "success", "data": {"successes": all_successes, "failures": all_failures}}


def _reset_mass_trade_state():
    """Clears everything about the last batch so the page goes back to
    a blank paste box."""
    st.session_state.mass_trade_submitted = False
    st.session_state.mass_trade_last_result = None
    st.session_state.mass_trade_last_rows = None
    st.session_state.mass_trade_raw_text = ""


def _render_success_state():
    """Renders the post-submission view: the same preview grid that was
    showing right before submit (so you can see exactly what was
    booked), with "Book More Trades" up top in place of the submit
    button. No submit control is rendered here, so there's no way to
    re-book the same batch.

    NOTE: the backend now processes every trade in the batch regardless
    of earlier failures, and always returns HTTP 200 -- so we can't rely
    on "the request succeeded" to mean "every trade succeeded." We have
    to read data["successes"]/data["failures"] to know what really
    happened.
    """
    payload, data = st.session_state.mass_trade_last_result
    rows = st.session_state.get("mass_trade_last_rows", [])

    successes = data.get("successes", []) if isinstance(data, dict) else []
    failures = data.get("failures", []) if isinstance(data, dict) else []

    if st.button("📋 Book More Trades", type="primary"):
        _reset_mass_trade_state()
        st.rerun()

    if failures:
        st.warning(
            f"{len(successes)} of {len(payload)} trades booked. "
            f"{len(failures)} failed:"
        )
        for entry in failures:
            reason = (
                entry.get("Failure Reason", "Unknown error")
                if isinstance(entry, dict)
                else str(entry)
            )
            st.error(reason)
    else:
        st.success(f"✅ {len(successes)} of {len(payload)} trades submitted successfully.")

    if rows:
        _render_preview_grid(rows)


def render_mass_trade_page():
    st.header("📋 Mass Trade Booker")

    # Once a batch has been submitted, show only the success state above
    # (with "Book More Trades" up top) until the user explicitly starts a
    # new batch. This makes re-submission of the same batch impossible on
    # a stray rerun, since the paste form and submit form below are never
    # even rendered while this is true.
    if st.session_state.get("mass_trade_submitted"):
        _render_success_state()
        return

    st.caption("Paste or type trades below, one per line.")

    st.markdown("""
    **Format:** `Account Name, Ticker, Direction, Quantity, Price, Other Account (optional)`

    **Example:**
    ```
    My Retirement Account, AAPL, Buy, 100, 189.42
    Trading Account, MSFT, Sell, 50, 415.00
    My Retirement Account, GOOGL, Buy, 200, 175.30
    ```
    Direction must be `Buy` or `Sell`. Account name must match exactly.
    """)

    # This lives in its own form. Cmd/Ctrl+Enter inside a text_area submits
    # whichever form contains it — isolating the paste box here means that
    # keystroke can only ever trigger "Preview Trades" below, and has no
    # way to reach (or auto-fire) the real submit button further down.
    with st.form("mass_trade_paste_form"):
        raw_text_input = st.text_area(
            "Trades",
            height=300,
            placeholder=EXAMPLE_TEXT,
            value=st.session_state.get("mass_trade_raw_text", ""),
        )
        preview_clicked = st.form_submit_button("Preview Trades")

    if preview_clicked:
        st.session_state.mass_trade_raw_text = raw_text_input

    raw_text = st.session_state.get("mass_trade_raw_text", "")

    if not raw_text.strip():
        return

    rows = _parse_input(raw_text)

    if not rows:
        st.warning("No trades found — make sure each line has at least 5 fields.")
        return

    valid_rows = [r for r in rows if r["_valid"]]
    invalid_rows = [r for r in rows if not r["_valid"]]

    st.divider()
    st.subheader(
        f"Preview — {len(rows)} trades ({len(valid_rows)} valid, {len(invalid_rows)} invalid)"
    )

    _render_preview_grid(rows)

    if invalid_rows:
        st.warning(
            f"{len(invalid_rows)} trades have errors and will be skipped. "
            f"Fix them above and re-paste to include them."
        )

    if not valid_rows:
        st.error("No valid trades to submit.")
        return

    st.divider()

    # Submission lives in its own form too, entirely separate from the
    # paste form above — it can only ever fire from an explicit click on
    # its own submit button, never as a side effect of the paste form.
    # Wrapped in a keyed container so the CSS below only recolors this
    # specific button, not "Preview Trades" or "Book More Trades" (which
    # also use type="primary").
    with st.container(key="mass_trade_submit_container"):
        st.markdown(
            """
            <style>
            .st-key-mass_trade_submit_container button {
                background-color: #28a745;
                border-color: #28a745;
                color: white;
            }
            .st-key-mass_trade_submit_container button:hover {
                background-color: #218838;
                border-color: #1e7e34;
                color: white;
            }
            .st-key-mass_trade_submit_container button:active {
                background-color: #1e7e34;
                border-color: #1c7430;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        with st.form("mass_trade_submit_form"):
            submit_clicked = st.form_submit_button(
                f"Submit {len(valid_rows)} Valid Trades", type="primary"
            )

    if submit_clicked:
        st.session_state.mass_trade_last_rows = rows

        payload = [
            {
                "account_id": r["_account_id"],
                "ticker": r["Ticker"],
                "direction": r["Direction"],
                "quantity": int(r["Quantity"]),
                "price": str(r["Price"]),
                "other_account": r["Other Account"] or None,
                "user_id": st.session_state.username,
            }
            for r in valid_rows
        ]

        n_batches = (len(payload) + BATCH_SIZE - 1) // BATCH_SIZE
        with st.spinner(f"Submitting {len(payload)} trades across {n_batches} parallel batches…"):
            result = _submit_in_batches(payload)


        if result["status"] == "success":
            st.session_state.mass_trade_submitted = True
            st.session_state.mass_trade_last_result = (payload, result["data"])
            st.rerun()
        else:
            st.error(f"Submission failed: {result['message']}")