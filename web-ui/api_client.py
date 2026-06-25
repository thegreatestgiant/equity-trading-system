import os
import requests
import streamlit as st

API_BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def _get_session():
    if "http" not in st.session_state:
        session = requests.Session()
        saved_cookie = st.session_state.get("saved_session_cookie")
        if saved_cookie:
            session.cookies.set("session", saved_cookie)
        st.session_state.http = session
    return st.session_state.http


def _api_error(response):
    """Pulls a clean error message out of a failed response, falling back to
    raw text if the body isn't JSON (e.g. a 500 with no detail field).

    Also guards against a specific edge case: if the browser remembered a
    username via localStorage (see persistent_login.py) but the actual
    backend session cookie didn't survive the reload, the UI would think
    it's logged in while every real API call 401s. Rather than show that
    confusingly on every page, treat a 401 here as "the remembered login
    wasn't actually valid" and bounce back to a clean login screen."""
    if response.status_code == 401 and st.session_state.get("username"):
        from persistent_login import forget_login
        st.session_state.username = None
        st.session_state.pop("http", None)
        forget_login()
        st.warning("Your session expired. Please log in again.")
        st.rerun()

    try:
        return response.json().get("detail", response.text)
    except Exception:
        return response.text


# --- Auth -------------------------------------------------------------

def login(username, password):
    session = _get_session()
    response = session.post(
        f"{API_BASE_URL}/login",
        json={"username": username, "password": password},
    )

    if response.status_code == 200:
        session_cookie = session.cookies.get("session")

        if not session_cookie:
            return {
                "status": "error",
                "message": "Login succeeded, but no session cookie was received.",
            }

        st.session_state.saved_session_cookie = session_cookie

        return {
            "status": "success",
            "session_cookie": session_cookie,
        }
    else:
        return {"status": "error", "message": _api_error(response)}


def register(username, password):
    session = _get_session()
    response = session.post(
        f"{API_BASE_URL}/register",
        json={"username": username, "password": password},
    )

    if response.status_code == 200:
        return {"status": "success", "username": username}
    else:
        return {"status": "error", "message": _api_error(response)}


def logout():
    session = _get_session()
    response = session.post(f"{API_BASE_URL}/logout")

    if response.status_code == 200:
        return {"status": "success"}
    else:
        return {"status": "error", "message": _api_error(response)}


# --- Positions ----------------------------------------------------------

def get_all_positions():
    session = _get_session()
    response = session.get(f"{API_BASE_URL}/positions")

    if response.status_code == 200:
        return {"status": "success", "data": response.json()["message"]}
    else:
        return {"status": "error", "message": _api_error(response)}


def _normalize_positions(raw, account_id=None, ticker=None):
    """The backend returns a different shape per positions endpoint
    (confirmed via Swagger against the live backend):

      - /positions
          {account_id: [{account_name, symbol_ticker, quantity, ...}, ...]}
      - /positions/accounts/{account_id}
          {ticker: {quantity, created_at, updated_at}}  -- no account_id/
          symbol_ticker in the value, since both are already known from
          the URL/key.
      - /positions/ticker/{ticker}
          {account_id: [{account_name, symbol_ticker, quantity, ...}, ...]}
          -- same shape as /positions, already has everything it needs.
      - /positions/accounts/{account_id}/ticker/{ticker}
          {ticker: quantity}  -- just a bare int, not a position dict at
          all, since account_id and ticker are both already known from
          the URL and there's only ever one position to describe.

    This normalizes the by-account and by-account-and-ticker shapes (the
    ones missing fields) into the same flat list of position dicts the
    renderer expects elsewhere; the other two are already in a shape the
    renderer understands, so they pass through untouched.
    """
    if not raw:
        return []

    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        first_value = next(iter(raw.values()), None)

        if isinstance(first_value, dict):
            # {ticker: {fields}} -- one bare position per key, fields like
            # quantity/created_at/updated_at but no account_id/symbol_ticker.
            return [
                {"account_id": account_id, "symbol_ticker": key, **fields}
                for key, fields in raw.items()
            ]

        if isinstance(first_value, list):
            # {account_id: [positions]} -- already fully-formed (e.g.
            # /positions/ticker/{ticker}). Leave it for the renderer's
            # per-account branch to handle directly.
            return raw

        if isinstance(first_value, (int, float)):
            # {ticker: quantity} -- the account+ticker endpoint's bare-int
            # shape. Build a minimal position dict from what we already
            # know (account_id/ticker from the call args) plus the
            # quantity, since the backend gives us nothing else here.
            return [
                {"account_id": account_id, "symbol_ticker": key, "quantity": qty}
                for key, qty in raw.items()
            ]

        # Unrecognized dict shape -- treat as a single bare position dict
        # rather than crash; the renderer will render whatever fields exist.
        position = dict(raw)
        position.setdefault("account_id", account_id)
        position.setdefault("symbol_ticker", ticker)
        return [position]

    return raw


def get_positions_by_account(account_id):
    session = _get_session()
    response = session.get(f"{API_BASE_URL}/positions/accounts/{account_id}")

    if response.status_code == 200:
        raw = response.json()["message"]
        return {"status": "success", "data": _normalize_positions(raw, account_id=account_id)}
    else:
        return {"status": "error", "message": _api_error(response)}


def get_positions_by_ticker(ticker):
    session = _get_session()
    response = session.get(f"{API_BASE_URL}/positions/ticker/{ticker}")

    if response.status_code == 200:
        # Already returns {account_id: [position, ...]} with account_name
        # and symbol_ticker included -- same shape as get_all_positions,
        # no normalization needed.
        return {"status": "success", "data": response.json()["message"]}
    else:
        return {"status": "error", "message": _api_error(response)}


def get_positions_by_account_and_ticker(account_id, ticker):
    session = _get_session()
    response = session.get(
        f"{API_BASE_URL}/positions/accounts/{account_id}/ticker/{ticker}"
    )

    if response.status_code == 200:
        raw = response.json()["message"]
        return {
            "status": "success",
            "data": _normalize_positions(raw, account_id=account_id, ticker=ticker),
        }
    else:
        return {"status": "error", "message": _api_error(response)}


# --- Trades ---------------------------------------------------------------

def submit_trades(trades: list):
    """Send a list of trade dicts to POST /trade in a single request.
    Each dict should have: account_id, user_id, ticker, direction,
    quantity, price, and optionally other_account.
    """
    session = _get_session()
    response = session.post(f"{API_BASE_URL}/trade", json=trades)

    if response.status_code == 200:
        return {"status": "success", "data": response.json()}
    else:
        return {"status": "error", "message": _api_error(response)}


# These don't have a real endpoint in main.py yet -- kept as mocks so the
# UI doesn't break.
def get_trades():
    session = _get_session()
    response = session.get(f"{API_BASE_URL}/trades")

    if response.status_code == 200:
        return {"status": "success", "data": response.json()}
    else:
        return {"status": "error", "message": _api_error(response)}


def get_trades_by_account(account_id):
    session = _get_session()
    response = session.get(f"{API_BASE_URL}/trades/account/{account_id}")

    if response.status_code == 200:
        return {"status": "success", "data": response.json()}
    else:
        return {"status": "error", "message": _api_error(response)}


def get_trades_by_ticker(ticker):
    session = _get_session()
    response = session.get(f"{API_BASE_URL}/trades/ticker/{ticker}")

    if response.status_code == 200:
        return {"status": "success", "data": response.json()}
    else:
        return {"status": "error", "message": _api_error(response)}


def get_trades_by_account_and_ticker(account_id, ticker):
    session = _get_session()
    # NOTE: backend route uses a "." before {ticker}, not "/" -- confirm
    # with your teammate whether this is intentional.
    response = session.get(
        f"{API_BASE_URL}/trades/account/{account_id}/ticker/{ticker}"
    )

    if response.status_code == 200:
        return {"status": "success", "data": response.json()}
    else:
        return {"status": "error", "message": _api_error(response)}


def get_trade_by_id(trade_id):
    session = _get_session()
    response = session.get(f"{API_BASE_URL}/trades/{trade_id}")

    if response.status_code == 200:
        return {"status": "success", "data": response.json()}
    else:
        return {"status": "error", "message": _api_error(response)}


# No real endpoint for this yet -- kept as a mock.
def update_trade(trade_id, data):
    return {
        "status": "success",
        "trade_id": trade_id,
        "updated": data,
    }


# --- Accounts ---------------------------------------------------------

def create_account(name, can_short):
    session = _get_session()
    response = session.post(
        f"{API_BASE_URL}/users/account",
        params={"account_name": name, "can_short": can_short},
    )


    if response.status_code == 200:
        data = response.json()
        return {
            "status": "success",
            "account_id": data.get("account_id"),
            "name": data.get("name"),
        }
    else:
        return {"status": "error", "message": _api_error(response)}


def add_account_to_user(account_id):
    session = _get_session()
    response = session.post(f"{API_BASE_URL}/users/accounts/{account_id}")

    if response.status_code == 200:
        return {"status": "success"}
    else:
        return {"status": "error", "message": _api_error(response)}


def get_user_accounts():
    """Returns the logged-in user's full list of accounts, each with at
    least account_id and name. Requires the new GET /users/accounts
    endpoint."""
    session = _get_session()
    response = session.get(f"{API_BASE_URL}/users/allaccounts")

    if response.status_code == 200:
        return {"status": "success", "data": response.json()}
    else:
        return {"status": "error", "message": _api_error(response)}


# No real endpoint for this yet -- kept as a mock.
def update_user_account(account_id, data):
    return {
        "status": "success",
        "account_id": account_id,
        "updated": data,
    }