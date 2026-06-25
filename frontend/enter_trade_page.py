import streamlit as st

from api_client import submit_trades
from account_picker import account_select


def render_enter_trade_page():
    st.header("💸 Book a Trade")
    st.caption("POST /trade")

    # Initialize trade queue and review mode in session state
    if "trade_queue" not in st.session_state:
        st.session_state.trade_queue = []
    if "reviewing" not in st.session_state:
        st.session_state.reviewing = False
    if "editing_trade_index" not in st.session_state:
        st.session_state.editing_trade_index = None

    if st.session_state.reviewing:
        _render_review_step()
    else:
        _render_builder_step()


def _trade_row(trade, key_prefix, index):
    """Renders one queued trade as a card with Edit and Remove buttons.
    Returns True if the row triggered a rerun-worthy action."""
    with st.container(border=True):
        cols = st.columns([3, 2, 2, 2, 1, 1])
        cols[0].write(f"**{trade['ticker']}**  —  {trade['account_id']}")
        cols[1].write(trade["direction"])
        cols[2].write(f"Qty: {trade['quantity']}")
        cols[3].write(f"${trade['price']}")
        if cols[4].button("✏️", key=f"{key_prefix}_edit_{index}", help="Edit this trade"):
            st.session_state.editing_trade_index = index
            st.session_state.reviewing = False
            st.rerun()
        if cols[5].button("✕", key=f"{key_prefix}_remove_{index}", help="Remove this trade"):
            st.session_state.trade_queue.pop(index)
            if st.session_state.editing_trade_index == index:
                st.session_state.editing_trade_index = None
            st.rerun()


def _render_review_step():
    st.subheader("Review Trades")

    for i, trade in enumerate(st.session_state.trade_queue):
        _trade_row(trade, "review", i)

    st.divider()
    col_back, col_submit = st.columns([1, 1])

    if col_back.button("← Back"):
        st.session_state.reviewing = False
        st.rerun()

    if col_submit.button("Submit All", type="primary"):
        # Attach user_id to each trade and send as a single array
        payload = [
            {**trade, "user_id": st.session_state.username}
            for trade in st.session_state.trade_queue
        ]

        result = submit_trades(payload)

        if result["status"] == "success":
            st.success(f"All {len(payload)} trades submitted successfully.")
            _render_submission_results(payload, result["data"])
            st.session_state.trade_queue = []
            st.session_state.reviewing = False
        else:
            st.error(f"Submission failed: {result['message']}")


def _render_submission_results(payload, data):
    """Shows which trade got which trade_id, in plain readable text
    instead of raw JSON."""
    messages = data.get("message", []) if isinstance(data, dict) else []

    for trade, entry in zip(payload, messages):
        status_text = entry.get("status", "") if isinstance(entry, dict) else str(entry)
        # Backend currently returns "success, here is your trade_id <uuid>"
        trade_id = status_text.split("trade_id")[-1].strip() if "trade_id" in status_text else None

        with st.container(border=True):
            st.markdown(
                f"✅ **{trade['direction']} {trade['quantity']} {trade['ticker']}** "
                f"on account `{trade['account_id']}`"
            )
            if trade_id:
                st.caption(f"Trade ID: `{trade_id}`")
            else:
                st.caption(status_text)


def _render_builder_step():
    editing_index = st.session_state.editing_trade_index
    editing_trade = (
        st.session_state.trade_queue[editing_index]
        if editing_index is not None and editing_index < len(st.session_state.trade_queue)
        else None
    )

    # Show queued trades so far (skip the one currently being edited so
    # it doesn't look duplicated while it's loaded into the form below)
    other_trades = [
        (i, t) for i, t in enumerate(st.session_state.trade_queue) if i != editing_index
    ]
    if other_trades:
        st.subheader("Queued Trades")
        for i, trade in other_trades:
            _trade_row(trade, "queue", i)
        st.divider()

    # Add / Edit trade form
    st.subheader("Edit Trade" if editing_trade else "Add Trade")

    prefilled_account = st.session_state.pop("jump_to_trade_account", None)
    preselect = editing_trade["account_id"] if editing_trade else prefilled_account
    account_id = account_select(preselect_account_id=preselect, key="enter_trade_account_select")

    ticker = st.text_input("Ticker", value=editing_trade["ticker"] if editing_trade else "")
    direction_is_sell = st.toggle(
        "Sell (off = Buy)",
        value=(editing_trade["direction"] == "Sell") if editing_trade else False,
    )
    direction = "Sell" if direction_is_sell else "Buy"
    st.caption(f"Direction: **{direction}**")
    quantity = st.number_input(
        "Quantity", min_value=1, step=1,
        value=int(editing_trade["quantity"]) if editing_trade else 1,
    )
    price = st.number_input(
        "Price", min_value=0.01,
        value=float(editing_trade["price"]) if editing_trade else 0.01,
    )
    other_account = st.text_input(
        "Other Account (optional)",
        value=(editing_trade.get("other_account") or "") if editing_trade else "",
    )

    def _build_trade():
        return {
            "account_id": account_id,
            "ticker": ticker.upper(),
            "direction": direction,
            "quantity": int(quantity),
            "price": str(price),  # backend expects price as a string
            "other_account": other_account or None,
        }

    if editing_trade:
        col_save, col_cancel = st.columns([1, 1])
        if col_save.button("💾 Save Changes", type="primary"):
            if not account_id or not ticker:
                st.error("Account and Ticker are required.")
            else:
                st.session_state.trade_queue[editing_index] = _build_trade()
                st.session_state.editing_trade_index = None
                st.rerun()
        if col_cancel.button("Cancel"):
            st.session_state.editing_trade_index = None
            st.rerun()
    else:
        col_add, col_review = st.columns([1, 1])

        if col_add.button("＋ Add Trade"):
            if not account_id or not ticker:
                st.error("Account and Ticker are required.")
            else:
                st.session_state.trade_queue.append(_build_trade())
                st.session_state.last_added_trade = _build_trade()
                st.rerun()

        if col_review.button(
            "Review & Submit →",
            type="primary",
            disabled=len(st.session_state.trade_queue) == 0 and (not account_id or not ticker),
        ):
            # If the current form holds a trade that hasn't already
            # been added to the queue (via "+ Add Trade"), add it now.
            current = _build_trade() if (account_id and ticker) else None
            if current is not None and current != st.session_state.get("last_added_trade"):
                st.session_state.trade_queue.append(current)
            st.session_state.reviewing = True
            st.rerun()