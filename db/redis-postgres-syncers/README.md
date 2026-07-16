Rust workspace of five binaries that move data between Redis and Postgres, plus market data ingestion. Each binary is packaged as a container image and deployed as its own Kubernetes deployment/job.

### Binaries (`src/`)
- **`trade-writer`** — continually reads booked trades off a Redis stream (written by the API) and writes them to Postgres.
- **`db-syncer`** — continually copies users, accounts, positions, and the username map from Redis to Postgres.
- **`redis-populator`** — the reverse of `db-syncer`: reads users/accounts/positions/username from Postgres and rebuilds the Redis hashes. Runs once and exits — used for cold-cache bootstrap or restore after loading a Postgres dump.
- **`price-cacher`** — continually pulls current S&P 500 prices from the Yahoo Finance API and caches them in Redis.

### Build
`build_dev_images.nu` builds and pushes multi-arch `:dev` images. Stable `:latest` images are built by the Github Actions CI job
