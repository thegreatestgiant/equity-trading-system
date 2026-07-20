Streamlit frontend for the trading system: account management, position/trade lookups, and single or bulk trade entry.

### Components
- **`app_ui.py`** — entry point. Auth-gated navigation via `st.navigation` over the page files in `pages/`, with a custom sidebar.
- **`pages/`** — the Streamlit page entry points wired up in `app_ui.py`; each delegates to a `render_*` function in the modules below.
- **`auth_pages.py`** / **`auth_state.py`** — login/register forms and session-state auth helpers (the `require_auth` guard, saved session cookie, and user sidebar).
- **`accounts_pages.py`** / **`account_picker.py`** — create/view/edit accounts.
- **`positions_pages.py`** / **`positions_grid.py`** — position views (all / by account / by ticker / by account+ticker), rendered as AG Grid tables.
- **`trade_history_pages.py`** / **`trades_grid.py`** — trade history views and lookup/edit by trade ID.
- **`enter_trade_page.py`** — single-trade entry form.
- **`mass_trade_page.py`** — bulk trade entry (e.g. paste/import many trades at once).
- **`market_data.py`** — live price lookups via yfinance (cached).
- **`api_client.py`** — talks to the FastAPI backend; nearly every page goes through it.
- **`theme.py`** — Streamlit theming.

Trading data comes through `api_client.py` calling the FastAPI backend (see [`../api/README.md`](../api/README.md)) — the UI holds no direct Postgres/Redis connection. (`mass_trade_page.py` posts to the API directly for parallel bulk submission, and `market_data.py` pulls live prices from yfinance.)
