FastAPI backend for booking and querying trades. Reads Postgres for trade history, Reads/Writes Redis for fast data, and authenticates requests via a session cookie.

### Components (`app/`)
- `routers/` — `auth`, `accounts`, `positions`, `trades`, `health`: the API surface.
- `services/` — business logic behind each router (account/position/trade services, S&P ticker validation).
- `models/` — Pydantic request/response models.
- `core/` — Postgres pool, Redis client, config, security (cookie auth), logging, event_monitoring (logging various test only data).
- `middleware/` — request logging and timings.

### Endpoints
- **Auth**: `POST /register`, `POST /login`, `POST /logout`
- **Accounts**: `POST /users/account`, `POST /users/add_account/{account_id}`, `PATCH /users/update_account_details/{account_id}`, `GET /users/allaccounts`
- **Positions**: `GET /positions`, `GET /positions/accounts/{account_id}`, `GET /positions/ticker/{ticker}`, `GET /positions/accounts/{account_id}/ticker/{ticker}`
- **Trades**: `GET /tickers`, `POST /trade` (single or batch), `GET /trades`, `GET /trade/{trade_id}`, `PATCH /edit_trade/{trade_id}`
- **Health**: `GET /probe`

All routes except auth verify the session cookie. Positions, Accounts, and Users are written to Redis for fast acces ad for the `db-syncer` to then update Postgres. Trades are written to a Redis stream for the `trade-writer` workers to pick up (see [`db/redis-postgres-syncers/README.md`](../db/redis-postgres-syncers/README.md)).

Requires Postgres, Redis, Redis to be loaded with the S&P tickers, and the logging stack to be up before it will start.
