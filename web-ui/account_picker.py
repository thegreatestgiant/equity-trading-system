import time

import streamlit as st

from api_client import get_user_accounts

_ACCOUNTS_CACHE_TTL_SECONDS = 10


def get_account_options():
    """Returns (labels, label_to_id) built from the logged-in user's real
    accounts. Backend returns {"accounts": {name: account_id, ...}}.

    Cached in session_state for a few seconds. get_account_name() below
    calls this once per row, so rendering a grid/list of N trades or
    positions used to fire N sequential HTTP requests to the backend just
    to resolve account names -- this collapses that to one real fetch per
    TTL window. Deliberately session_state (per browser session), not
    st.cache_data (shared across all sessions), so one user's accounts
    can never leak into another user's cache."""
    cached = st.session_state.get("_account_options_cache")
    if cached and time.time() - cached["fetched_at"] < _ACCOUNTS_CACHE_TTL_SECONDS:
        return cached["labels"], cached["label_to_id"]

    result = get_user_accounts()
    accounts = {}
    if result["status"] == "success":
        accounts = result["data"].get("accounts", {})
    label_to_id = {
        f"{name or '(unnamed account)'} — {account_id}": account_id
        for name, account_id in accounts.items()
    }
    labels = list(label_to_id.keys())

    st.session_state["_account_options_cache"] = {
        "labels": labels,
        "label_to_id": label_to_id,
        "fetched_at": time.time(),
    }
    return labels, label_to_id


def _invalidate_account_options_cache():
    """Call after any mutation that changes the account list/names
    (create/update account) so the next lookup doesn't serve stale data
    for up to _ACCOUNTS_CACHE_TTL_SECONDS."""
    st.session_state.pop("_account_options_cache", None)


def get_account_name(account_id):
    """Reverse lookup: given an account_id, returns its display name, or
    the raw id itself if no matching account is found (e.g. an account
    belonging to a different user, or one that's been deleted)."""
    if not account_id:
        return account_id
    _, label_to_id = get_account_options()
    id_to_name = {aid: lbl.split(" — ")[0] for lbl, aid in label_to_id.items()}
    return id_to_name.get(account_id, account_id)


def account_select(label="Account", preselect_account_id=None, key=None):
    """Renders a dropdown of the user's accounts (shown as 'Name — id'),
    starting on a non-selectable 'Select Account' placeholder unless an
    account should be preselected (e.g. jumping here from My Accounts).
    Returns the selected account_id, or None if nothing real is chosen
    yet, or if the user has no accounts (in which case a warning shows).
    """
    PLACEHOLDER = "Select Account"

    labels, label_to_id = get_account_options()

    if not labels:
        st.warning("You don't have any accounts yet -- create one first.")
        return None

    options = [PLACEHOLDER] + labels

    default_label = None
    if preselect_account_id:
        default_label = next(
            (lbl for lbl, aid in label_to_id.items() if aid == preselect_account_id),
            None,
        )
        if default_label and key:
            st.session_state[key] = default_label

    default_index = options.index(default_label) if default_label in options else 0
    selected_label = st.selectbox(label, options, index=default_index, key=key)

    if selected_label == PLACEHOLDER:
        return None
    return label_to_id[selected_label]