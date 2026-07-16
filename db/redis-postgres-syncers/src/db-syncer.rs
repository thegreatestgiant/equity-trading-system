//! copy users, accounts, positions from redis to postgres

use anyhow::{Context, Result};
use dotenvy::dotenv;
use serde::de::DeserializeOwned;
use std::fmt::Write;
use tracing::{debug, info, trace, warn};

#[tokio::main]
async fn main() {
    let _ = dotenv();

    if let Err(err) = helpers::init_tracing("db-syncer") {
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

    let sync_interval: u64 = helpers::require_env("DELAY")?
        .parse()
        .context("DELAY must be an int")?;

    debug!(sync_interval, "read env vars");

    let pg_client = helpers::connect_postgres(&pg_config).await;
    let mut redis_conn = helpers::connect_redis(redis_url).await;

    loop {
        debug!("starting sync cycle");
        sync_users(&pg_client, &mut redis_conn)
            .await
            .context("user sync failed")?;
        sync_accounts(&pg_client, &mut redis_conn)
            .await
            .context("account sync failed")?;
        sync_positions(&pg_client, &mut redis_conn)
            .await
            .context("position sync failed")?;
        sync_usernames(&pg_client, &mut redis_conn)
            .await
            .context("username sync failed")?;
        info!("sync cycle complete");

        debug!(sync_interval, "sleeping until next sync cycle");
        tokio::select! {
            () = tokio::time::sleep(std::time::Duration::from_secs(sync_interval)) => {}
            () = helpers::shutdown_signal() => {
                info!("Shutdown signal received");
                return Ok(());
            }
        }
    }
}

struct JsonHashTableSyncSpec<T> {
    entity_name: &'static str,
    redis_key: &'static str,
    staging_table_name: &'static str,
    target_table_name: &'static str,
    copy_columns: &'static str,
    conflict_column: &'static str,
    update_assignments: &'static str,
    parse_row: fn(&str, &str) -> Result<T>,
    format_row: fn(&str, &T) -> String,
}

fn parse_json_row<T: DeserializeOwned>(entity_name: &str, id: &str, json_str: &str) -> Result<T> {
    serde_json::from_str(json_str)
        .with_context(|| format!("Failed to parse JSON for {entity_name} {id}"))
}

fn build_upsert_sql(
    target_table_name: &str,
    staging_table_name: &str,
    copy_columns: &str,
    conflict_column: &str,
    update_assignments: &str,
) -> String {
    format!(
        "INSERT INTO {target_table_name} ({copy_columns})
  SELECT {copy_columns}
  FROM {staging_table_name}
  ON CONFLICT ({conflict_column}) DO UPDATE SET
    {update_assignments}"
    )
}

async fn sync_json_hash_table<T>(
    pg_client: &tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
    spec: JsonHashTableSyncSpec<T>,
) -> Result<()> {
    debug!("sync {}...", spec.entity_name);

    let rows: std::collections::HashMap<String, String> = redis::cmd("HGETALL")
        .arg(spec.redis_key)
        .query_async(redis_conn)
        .await
        .with_context(|| {
            format!(
                "HGETALL of redis key \"{}\" for {} failed",
                spec.redis_key, spec.entity_name
            )
        })?;

    let total = rows.len();
    info!(
        "found {} {} in redis key \"{}\"",
        total, spec.entity_name, spec.redis_key
    );
    if rows.is_empty() {
        info!("nothing to sync");
        return Ok(());
    }

    pg_client
        .execute(&format!("TRUNCATE TABLE {};", spec.staging_table_name), &[])
        .await
        .map_err(helpers::pg_error)
        .with_context(|| {
            format!(
                "TRUNCATE of staging table {} failed",
                spec.staging_table_name
            )
        })?;

    debug!("cleared table {}", spec.staging_table_name);

    let mut copy_payload_buffer = String::with_capacity(rows.len() * 200);
    let mut skipped = 0;

    for (id_str, json_str) in rows {
        let data = match (spec.parse_row)(&id_str, &json_str) {
            Ok(data) => data,
            Err(err) => {
                warn!(?err, "skipping malformed {} row", spec.entity_name);
                skipped += 1;
                continue;
            }
        };

        trace!(id = %id_str, "staged {} row", spec.entity_name);
        let _ = writeln!(
            &mut copy_payload_buffer,
            "{}",
            (spec.format_row)(&id_str, &data)
        );
    }

    debug!(
        "prepared {} valid {} rows for copy ({} skipped)",
        total - skipped,
        spec.entity_name,
        skipped
    );

    if copy_payload_buffer.is_empty() {
        warn!(
            "every {} row was malformed (skipped {}); sync completed with no writes",
            spec.entity_name, skipped
        );
        return Ok(());
    }

    let copy_query = format!(
        "COPY {} ({}) FROM STDIN WITH (FORMAT text, DELIMITER '\t', NULL '\\N')",
        spec.staging_table_name, spec.copy_columns
    );

    let sink = pg_client
        .copy_in(&copy_query)
        .await
        .map_err(helpers::pg_error)
        .with_context(|| {
            format!(
                "failed to initialize COPY into staging table {}",
                spec.staging_table_name
            )
        })?;

    helpers::send_copy_payload(sink, &copy_payload_buffer)
        .await
        .map_err(helpers::pg_error)
        .with_context(|| format!("COPY into staging table {} failed", spec.staging_table_name))?;

    info!("wrote {} into staging table", spec.entity_name);

    let upserted = pg_client
        .execute(
            &build_upsert_sql(
                spec.target_table_name,
                spec.staging_table_name,
                spec.copy_columns,
                spec.conflict_column,
                spec.update_assignments,
            ),
            &[],
        )
        .await
        .map_err(helpers::pg_error)
        .with_context(|| {
            format!(
                "upsert from {} into {} failed",
                spec.staging_table_name, spec.target_table_name
            )
        })?;

    if skipped > 0 {
        warn!(
            "skipped {} malformed {} payloads from redis",
            skipped, spec.entity_name
        );
    }

    info!(
        "upserted {} {} to {} table",
        upserted, spec.entity_name, spec.target_table_name
    );

    Ok(())
}

async fn sync_users(
    pg_client: &tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
) -> Result<()> {
    sync_json_hash_table(
        pg_client,
        redis_conn,
        JsonHashTableSyncSpec {
            entity_name: "users",
            redis_key: "users",
            staging_table_name: "users_sync_stage",
            target_table_name: "users",
            copy_columns: "user_id, username, oauth_key, accounts_associated, created_at, updated_at",
            conflict_column: "user_id",
            update_assignments: "username = EXCLUDED.username,\n    oauth_key = EXCLUDED.oauth_key,\n    accounts_associated = EXCLUDED.accounts_associated,\n    updated_at = EXCLUDED.updated_at",
            parse_row: |id, json| parse_json_row::<helpers::User>("user", id, json),
            format_row: |id, data| {
                format!(
                    "{}\t{}\t{}\t{}\t{}\t{}",
                    id,
                    data.username,
                    data.oauth_key,
                    to_pg_text_array_literal(&data.accounts_associated),
                    data.created_at,
                    data.updated_at,
                )
            },
        },
    )
    .await
}

async fn sync_accounts(
    pg_client: &tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
) -> Result<()> {
    sync_json_hash_table(
        pg_client,
        redis_conn,
        JsonHashTableSyncSpec {
            entity_name: "accounts",
            redis_key: "accounts",
            staging_table_name: "accounts_sync_stage",
            target_table_name: "accounts",
            copy_columns: "account_id, account_name, positions, can_short, created_at, updated_at",
            conflict_column: "account_id",
            update_assignments: "account_name = EXCLUDED.account_name,\n    positions = EXCLUDED.positions,\n    can_short = EXCLUDED.can_short,\n    updated_at = EXCLUDED.updated_at",
            parse_row: |id, json| parse_json_row::<helpers::Account>("account", id, json),
            format_row: |id, data| {
                format!(
                    "{}\t{}\t{}\t{}\t{}\t{}",
                    id,
                    data.account_name,
                    to_pg_text_array_literal(&data.positions),
                    data.can_short,
                    data.created_at,
                    data.updated_at,
                )
            },
        },
    )
    .await
}

async fn sync_positions(
    pg_client: &tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
) -> Result<()> {
    sync_json_hash_table(
        pg_client,
        redis_conn,
        JsonHashTableSyncSpec {
            entity_name: "positions",
            redis_key: "positions",
            staging_table_name: "positions_sync_stage",
            target_table_name: "positions",
            copy_columns: "position_id, account_id, symbol_ticker, quantity, average_cost, total_realized_gains, created_at, updated_at",
            conflict_column: "position_id",
            update_assignments: "quantity = EXCLUDED.quantity,\n    average_cost = EXCLUDED.average_cost,\n    total_realized_gains = EXCLUDED.total_realized_gains,\n    updated_at = EXCLUDED.updated_at",
            parse_row: |id, json| parse_json_row::<helpers::Position>("position", id, json),
            format_row: |id, data| {
                format!(
                    "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                    id,
                    data.account_id,
                    data.symbol_ticker,
                    data.quantity,
                    to_pg_optional_numeric(data.average_cost),
                    to_pg_optional_numeric(data.total_realized_gains),
                    data.created_at,
                    data.updated_at,
                )
            },
        },
    )
    .await
}

async fn sync_usernames(
    pg_client: &tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
) -> Result<()> {
    sync_json_hash_table(
        pg_client,
        redis_conn,
        JsonHashTableSyncSpec {
            entity_name: "usernames",
            redis_key: "username",
            staging_table_name: "username_sync_stage",
            target_table_name: "username",
            copy_columns: "username, user_id",
            conflict_column: "username",
            update_assignments: "user_id = EXCLUDED.user_id",
            // the redis value is a bare uuid string, not JSON — pass it through.
            parse_row: |_username, user_id| Ok(user_id.to_string()),
            format_row: |username, user_id| format!("{}\t{}", username, user_id),
        },
    )
    .await
}

fn to_pg_optional_numeric(value: Option<f64>) -> String {
    match value {
        Some(v) => v.to_string(),
        None => "\\N".to_string(),
    }
}

fn to_pg_text_array_literal(values: &[String]) -> String {
    if values.is_empty() {
        return "{}".to_string();
    }

    let elements: Vec<String> = values
        .iter()
        .map(|val| {
            let mut escaped = String::with_capacity(val.len() + 2);
            escaped.push('"');
            for ch in val.chars() {
                match ch {
                    '\\' => escaped.push_str("\\\\"),
                    '"' => escaped.push_str("\\\""),
                    _ => escaped.push(ch),
                }
            }
            escaped.push('"');
            escaped
        })
        .collect();

    format!("{{{}}}", elements.join(","))
}
