import streamlit as st

from api_client import submit_trades
from account_picker import account_select


def render_enter_trade_page():
    st.header("💸 Book a Trade", anchor=False)
    st.caption("POST /trade")

    # Initialize trade queue and review mode in session state
    if "trade_queue" not in st.session_state:
        st.session_state.trade_queue = []
    if "reviewing" not in st.session_state:
        st.session_state.reviewing = False
    if "editing_trade_index" not in st.session_state:
        st.session_state.editing_trade_index = None
    if "last_submission_result" not in st.session_state:
        st.session_state.last_submission_result = None

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
    # If a submission just succeeded, show only the success state --
    # don't keep rendering the stale Review Trades cards/Submit button
    # underneath it.
    if st.session_state.get("last_submission_result"):
        _render_post_submission_state()
        return

    st.subheader("Review Trades", anchor=False)

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
            # Stash the result so the post-submission state can render
            # it, then clear the queue. Don't reset "reviewing" yet --
            # that happens when the user clicks "Book More Trades".
            st.session_state.last_submission_result = (payload, result["data"])
            st.session_state.trade_queue = []
            st.rerun()
        else:
            st.error(f"Submission failed: {result['message']}")


def _render_post_submission_state():
    """NOTE: the backend now processes every trade in the batch
    regardless of earlier failures, and always returns HTTP 200 -- so
    result["status"] == "success" only means the request went through,
    not that every trade booked. We read data["successes"]/
    data["failures"] to know what actually happened."""
    payload, data = st.session_state.last_submission_result

    successes = data.get("successes", []) if isinstance(data, dict) else []
    failures = data.get("failures", []) if isinstance(data, dict) else []

    if failures:
        st.warning(f"{len(successes)} of {len(payload)} trades booked. {len(failures)} failed:")
    else:
        st.success(f"All {len(successes)} trades submitted successfully.")

    _render_submission_results(successes, failures)

    st.divider()
    with st.container(key="enter_trade_success_buttons"):
        st.markdown(
            """
            <style>
            .st-key-enter_trade_success_buttons div[data-testid="column"]:nth-child(1) button {
                background-color: #28a745; border-color: #28a745; color: white; width: 100%;
            }
            .st-key-enter_trade_success_buttons div[data-testid="column"]:nth-child(1) button:hover {
                background-color: #218838; border-color: #1e7e34;
            }
            .st-key-enter_trade_success_buttons div[data-testid="column"]:nth-child(2) button {
                background-color: #007bff; border-color: #007bff; color: white; width: 100%;
            }
            .st-key-enter_trade_success_buttons div[data-testid="column"]:nth-child(2) button:hover {
                background-color: #0069d9; border-color: #0062cc;
            }
            .st-key-enter_trade_success_buttons div[data-testid="column"]:nth-child(3) button {
                background-color: #6f42c1; border-color: #6f42c1; color: white; width: 100%;
            }
            .st-key-enter_trade_success_buttons div[data-testid="column"]:nth-child(3) button:hover {
                background-color: #5a32a3; border-color: #542c98;
            }
            </style>
            """, unsafe_allow_html=True
        )
        col1, col2, col3, _ = st.columns([1.5, 1.5, 1.5, 7.5])
        if col1.button("➕ Book More Trades"):
            st.session_state.last_submission_result = None
            st.session_state.reviewing = False
            st.session_state.editing_trade_index = None
            st.rerun()
        if col2.button("📊 View Positions"):
            if payload and payload[0].get("account_id"):
                st.session_state.jump_to_account = payload[0]["account_id"]
            st.switch_page("pages/positions.py")
        if col3.button("💸 View Trades"):
            if payload and payload[0].get("account_id"):
                st.session_state.jump_to_trades_account = payload[0]["account_id"]
            st.switch_page("pages/trade_history.py")


def _render_submission_results(successes, failures):
    """Shows which trades booked and which failed and why.

    NOTE: successes currently only carry a trade_id -- the backend
    doesn't echo back which account/ticker each one was for, unlike
    failures, whose reason text already names the account/ticker (see
    trade_services.py's error messages). Worth asking for that same
    context on successes too, for a fully readable audit trail here.
    """
    for entry in successes:
        trade_id = entry.get("trade_id") if isinstance(entry, dict) else None
        with st.container(border=True):
            st.markdown("✅ **Trade booked**")
            if trade_id:
                col_tid, col_edit = st.columns([10, 1])
                col_tid.caption(f"Trade ID: `{trade_id}`")
                if col_edit.button("✏️", key=f"edit_booked_{trade_id}", help="Edit Trade"):
                    st.session_state.editing_trade_id = trade_id
                    st.switch_page("pages/edit_trade.py")

    for entry in failures:
        reason = (
            entry.get("Failure Reason", "Unknown error")
            if isinstance(entry, dict)
            else str(entry)
        )
        with st.container(border=True):
            st.markdown(f"❌ {reason}")


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
        st.subheader("Queued Trades", anchor=False)
        for i, trade in other_trades:
            _trade_row(trade, "queue", i)
        st.divider()

    # Add / Edit trade form
    st.subheader("Edit Trade" if editing_trade else "Add Trade", anchor=False)

    with st.form("trade_builder_form"):
        prefilled_account = st.session_state.pop("jump_to_trade_account", None)
        preselect = editing_trade["account_id"] if editing_trade else prefilled_account
        account_id = account_select(preselect_account_id=preselect, key="enter_trade_account_select")

        ticker = st.text_input("Ticker", value=editing_trade["ticker"] if editing_trade else "")
        direction = st.segmented_control(
            "Direction",
            options=["Buy", "Sell"],
            default=(editing_trade["direction"] if editing_trade else "Buy"),
        )
        if not direction:
            direction = "Buy"
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
            save_clicked = col_save.form_submit_button("💾 Save Changes", type="primary")
            cancel_clicked = col_cancel.form_submit_button("Cancel")
            
            if save_clicked:
                if not account_id or not ticker:
                    st.error("Account and Ticker are required.")
                else:
                    st.session_state.trade_queue[editing_index] = _build_trade()
                    st.session_state.editing_trade_index = None
                    st.rerun()
            if cancel_clicked:
                st.session_state.editing_trade_index = None
                st.rerun()
        else:
            col_add, col_review = st.columns([1, 1])
            add_clicked = col_add.form_submit_button("＋ Add Trade")
            review_clicked = col_review.form_submit_button("Review & Submit →", type="primary")

            if add_clicked:
                if not account_id or not ticker:
                    st.error("Account and Ticker are required.")
                else:
                    st.session_state.trade_queue.append(_build_trade())
                    st.session_state.last_added_trade = _build_trade()
                    st.rerun()

            if review_clicked:
                current = _build_trade() if (account_id and ticker) else None
                if current is not None and current != st.session_state.get("last_added_trade"):
                    st.session_state.trade_queue.append(current)
                st.session_state.reviewing = True
                st.rerun()