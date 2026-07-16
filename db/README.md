- **`init.sql`** — Postgres schema for the `trading` database: tables `users`, `accounts`, `positions`, `trades`; and some utility stuff
- **[`redis-postgres-syncers/`](redis-postgres-syncers/README.md)** — Rust workers that
    1. move data between Redis (hot path, written by the API) and Postgres (persistence & accessibility)
    2. keep redis updated with cached stock price data (for the API)