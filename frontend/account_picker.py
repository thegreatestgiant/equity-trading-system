import streamlit as st

from api_client import get_user_accounts


def get_account_options():
    """Returns (labels, label_to_id) built from the logged-in user's real
    accounts. Backend returns {"accounts": {name: account_id, ...}}."""
    result = get_user_accounts()
    accounts = {}
    if result["status"] == "success":
        accounts = result["data"].get("accounts", {})
    label_to_id = {
        f"{name or '(unnamed account)'} — {account_id}": account_id
        for name, account_id in accounts.items()
    }
    return list(label_to_id.keys()), label_to_id


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

    default_index = options.index(default_label) if default_label in options else 0
    selected_label = st.selectbox(label, options, index=default_index, key=key)

    if selected_label == PLACEHOLDER:
        return None
    return label_to_id[selected_label]