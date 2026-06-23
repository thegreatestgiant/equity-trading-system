import streamlit as st

from api_client import submit_trades


def render_enter_trade_page():
    st.header("💸 Book a Trade")
    st.caption("POST /trade")

    # Initialize trade queue and review mode in session state
    if "trade_queue" not in st.session_state:
        st.session_state.trade_queue = []
    if "reviewing" not in st.session_state:
        st.session_state.reviewing = False

    if st.session_state.reviewing:
        _render_review_step()
    else:
        _render_builder_step()


def _render_review_step():
    st.subheader("Review Trades")

    for i, trade in enumerate(st.session_state.trade_queue):
        with st.container(border=True):
            cols = st.columns([3, 2, 2, 2, 1])
            cols[0].write(f"**{trade['ticker']}**  —  {trade['account_id']}")
            cols[1].write(trade["direction"])
            cols[2].write(f"Qty: {trade['quantity']}")
            cols[3].write(f"${trade['price']}")
            if cols[4].button("✕", key=f"remove_{i}"):
                st.session_state.trade_queue.pop(i)
                st.rerun()

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
            st.json(result["data"])
            st.session_state.trade_queue = []
            st.session_state.reviewing = False
        else:
            st.error(f"Submission failed: {result['message']}")


def _render_builder_step():
    # Show queued trades so far
    if st.session_state.trade_queue:
        st.subheader("Queued Trades")
        for i, trade in enumerate(st.session_state.trade_queue):
            with st.container(border=True):
                cols = st.columns([3, 2, 2, 2, 1])
                cols[0].write(f"**{trade['ticker']}**  —  {trade['account_id']}")
                cols[1].write(trade["direction"])
                cols[2].write(f"Qty: {trade['quantity']}")
                cols[3].write(f"${trade['price']}")
                if cols[4].button("✕", key=f"q_remove_{i}"):
                    st.session_state.trade_queue.pop(i)
                    st.rerun()
        st.divider()

    # Add a new trade form
    st.subheader("Add Trade")
    account_id = st.text_input("Account ID")
    ticker = st.text_input("Ticker")
    direction_is_sell = st.toggle("Sell (off = Buy)")
    direction = "Sell" if direction_is_sell else "Buy"
    st.caption(f"Direction: **{direction}**")
    quantity = st.number_input("Quantity", min_value=1, step=1)
    price = st.number_input("Price", min_value=0.01)
    other_account = st.text_input("Other Account (optional)")

    def _build_trade():
        return {
            "account_id": account_id,
            "ticker": ticker.upper(),
            "direction": direction,
            "quantity": int(quantity),
            "price": str(price),  # backend expects price as a string
            "other_account": other_account or None,
        }

    col_add, col_review = st.columns([1, 1])

    if col_add.button("＋ Add Trade"):
        if not account_id or not ticker:
            st.error("Account ID and Ticker are required.")
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
