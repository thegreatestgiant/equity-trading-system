Streamlit frontend for the trading system: account management, position/trade lookups, and single or bulk trade entry.

### Components
- **`app_ui.py`** — entry point. Handles auth-gated routing between pages via a sidebar radio, synced to `?page=` in the URL.
- **`auth_pages.py`** / **`persistent_login.py`** — login/register forms and a browser-persisted session cookie.
- **`accounts_pages.py`** / **`account_picker.py`** — create/view/edit accounts.
- **`positions_pages.py`** / **`positions_grid.py`** — position views (all / by account / by ticker / by account+ticker), rendered as AG Grid tables.
- **`trade_history_pages.py`** / **`trades_grid.py`** — trade history views and lookup/edit by trade ID.
- **`enter_trade_page.py`** — single-trade entry form.
- **`mass_trade_page.py`** — bulk trade entry (e.g. paste/import many trades at once).
- **`api_client.py`** — the only module that talks to the FastAPI backend; every page goes through it.
- **`theme.py`** — Streamlit theming.

All data comes through `api_client.py` calling the FastAPI backend (see [`../api/README.md`](../api/README.md)) — the UI holds no direct Postgres/Redis connection.
