//! populate redis hashes from postgres tables — the reverse of db-syncer.
//! reads users, accounts, positions from postgres and (re)writes the matching
//! redis hashes. runs once and exits (a cold-cache bootstrap / restore).

use anyhow::{Context, Result};
use dotenvy::dotenv;
use tokio_postgres::Row;
use tracing::{debug, info, trace, warn};

#[tokio::main]
async fn main() {
    let _ = dotenv();

    if let Err(err) = helpers::init_tracing("redis-populator") {
        eprintln!("failed to initialize tracing: {:?}", err);
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        std::process::exit(1);
    }

    if let Err(err) = run().await {
        helpers::fatal("Fatal error", err).await;
    }
}

async fn run() -> Result<()> {
    let pg_config = helpers::require_env("POSTGRES_CONFIG")?;
    let redis_url = helpers::require_env("REDIS_URL")?;

    let pg_client = helpers::connect_postgres(&pg_config).await;
    let mut redis_conn = helpers::connect_redis(redis_url).await;

    debug!("starting populate");
    populate_users(&pg_client, &mut redis_conn)
        .await
        .context("user populate failed")?;
    populate_accounts(&pg_client, &mut redis_conn)
        .await
        .context("account populate failed")?;
    populate_positions(&pg_client, &mut redis_conn)
        .await
        .context("position populate failed")?;
    populate_username(&pg_client, &mut redis_conn)
        .await
        .context("username populate failed")?;
    info!("populate complete");

    Ok(())
}

/// postgres `to_char` template that reproduces python's `datetime.isoformat()`
/// for UTC timestamps, e.g. `2026-07-09T22:46:38.970081+00:00`.
///
/// the column is forced to UTC with `AT TIME ZONE 'UTC'`, so the literal
/// `+00:00` offset is always correct.
macro_rules! iso_ts {
    ($col:literal) => {
        concat!(
            "to_char(",
            $col,
            " AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"+00:00\"') AS ",
            $col
        )
    };
}

struct HashPopulateSpec {
    entity_name: &'static str,
    redis_key: &'static str,
    select_query: &'static str,
    /// maps a postgres row to a `(hash field id, json value)` pair
    row_to_entry: fn(&Row) -> Result<(String, String)>,
}

async fn populate_hash(
    pg_client: &tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
    spec: HashPopulateSpec,
) -> Result<()> {
    debug!("populate {}...", spec.entity_name);

    let rows = pg_client
        .query(spec.select_query, &[])
        .await
        .map_err(helpers::pg_error)
        .with_context(|| format!("SELECT of {} failed", spec.entity_name))?;

    info!("read {} {} from postgres", rows.len(), spec.entity_name);

    // full replace in a single pipeline: DEL first, then HSET every row.
    let mut pipe = redis::pipe();
    pipe.del(spec.redis_key);

    let mut skipped = 0;
    for row in &rows {
        match (spec.row_to_entry)(row) {
            Ok((id, json)) => {
                trace!(id = %id, "staged {} entry", spec.entity_name);
                pipe.hset(spec.redis_key, id, json);
            }
            Err(err) => {
                warn!(?err, "skipping malformed {} row", spec.entity_name);
                skipped += 1;
            }
        }
    }

    pipe.query_async::<()>(redis_conn)
        .await
        .with_context(|| format!("redis pipeline for key \"{}\" failed", spec.redis_key))?;

    if skipped > 0 {
        warn!("skipped {skipped} malformed {} rows", spec.entity_name);
    }

    info!(
        "wrote {} {} to redis key \"{}\"",
        rows.len() - skipped,
        spec.entity_name,
        spec.redis_key
    );

    Ok(())
}

async fn populate_users(
    pg_client: &tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
) -> Result<()> {
    populate_hash(
        pg_client,
        redis_conn,
        HashPopulateSpec {
            entity_name: "users",
            redis_key: "users",
            select_query: concat!(
                "SELECT user_id::text AS user_id, username, oauth_key, ",
                "accounts_associated::text[] AS accounts_associated, ",
                iso_ts!("created_at"),
                ", ",
                iso_ts!("updated_at"),
                " FROM users"
            ),
            row_to_entry: |row| {
                let id: String = row.try_get("user_id").context("user_id")?;
                let user = helpers::User {
                    username: row.try_get("username").context("username")?,
                    oauth_key: row.try_get("oauth_key").context("oauth_key")?,
                    accounts_associated: row
                        .try_get("accounts_associated")
                        .context("accounts_associated")?,
                    created_at: row.try_get("created_at").context("created_at")?,
                    updated_at: row.try_get("updated_at").context("updated_at")?,
                };
                let json = serde_json::to_string(&user)
                    .with_context(|| format!("serializing user {id}"))?;
                Ok((id, json))
            },
        },
    )
    .await
}

async fn populate_username(
    pg_client: &tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
) -> Result<()> {
    populate_hash(
        pg_client,
        redis_conn,
        HashPopulateSpec {
            entity_name: "usernames",
            redis_key: "username",
            select_query: "SELECT username, user_id::text AS user_id FROM username",
            // the redis value is the bare uuid string, not JSON.
            row_to_entry: |row| {
                let username: String = row.try_get("username").context("username")?;
                let user_id: String = row.try_get("user_id").context("user_id")?;
                Ok((username, user_id))
            },
        },
    )
    .await
}

async fn populate_accounts(
    pg_client: &tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
) -> Result<()> {
    populate_hash(
        pg_client,
        redis_conn,
        HashPopulateSpec {
            entity_name: "accounts",
            redis_key: "accounts",
            select_query: concat!(
                "SELECT account_id::text AS account_id, account_name, ",
                "positions::text[] AS positions, can_short, ",
                iso_ts!("created_at"),
                ", ",
                iso_ts!("updated_at"),
                " FROM accounts"
            ),
            row_to_entry: |row| {
                let id: String = row.try_get("account_id").context("account_id")?;
                let account = helpers::Account {
                    account_name: row.try_get("account_name").context("account_name")?,
                    positions: row.try_get("positions").context("positions")?,
                    can_short: row.try_get("can_short").context("can_short")?,
                    created_at: row.try_get("created_at").context("created_at")?,
                    updated_at: row.try_get("updated_at").context("updated_at")?,
                };
                let json = serde_json::to_string(&account)
                    .with_context(|| format!("serializing account {id}"))?;
                Ok((id, json))
            },
        },
    )
    .await
}

async fn populate_positions(
    pg_client: &tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
) -> Result<()> {
    populate_hash(
        pg_client,
        redis_conn,
        HashPopulateSpec {
            entity_name: "positions",
            redis_key: "positions",
            select_query: concat!(
                "SELECT position_id::text AS position_id, account_id::text AS account_id, ",
                "symbol_ticker, quantity, ",
                "average_cost::float8 AS average_cost, ",
                "total_realized_gains::float8 AS total_realized_gains, ",
                iso_ts!("created_at"),
                ", ",
                iso_ts!("updated_at"),
                " FROM positions"
            ),
            row_to_entry: |row| {
                let id: String = row.try_get("position_id").context("position_id")?;
                let position = helpers::Position {
                    account_id: row.try_get("account_id").context("account_id")?,
                    symbol_ticker: row.try_get("symbol_ticker").context("symbol_ticker")?,
                    quantity: row.try_get("quantity").context("quantity")?,
                    average_cost: row.try_get("average_cost").context("average_cost")?,
                    total_realized_gains: row
                        .try_get("total_realized_gains")
                        .context("total_realized_gains")?,
                    created_at: row.try_get("created_at").context("created_at")?,
                    updated_at: row.try_get("updated_at").context("updated_at")?,
                };
                let json = serde_json::to_string(&position)
                    .with_context(|| format!("serializing position {id}"))?;
                Ok((id, json))
            },
        },
    )
    .await
}
