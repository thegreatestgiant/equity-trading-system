//! Write trades from redis stream (sent by API) to postgres

use anyhow::{Context, Result};
use dotenvy::dotenv;
use redis::AsyncCommands;
use redis::streams::{
    StreamAutoClaimOptions, StreamAutoClaimReply, StreamDeletionPolicy, StreamId,
    StreamReadOptions, StreamReadReply, StreamTrimOptions, StreamTrimmingMode,
};
use serde::Deserialize;
use std::fmt::Write;
use tokio::time::{Duration, Instant};
use tracing::{debug, error, info, trace, warn};

// ADJUSTABLE

/// Max entries to pull per batch
const BATCH_COUNT: usize = 5000; // TODO: determine optimal number

/// How long a message must sit un-ACKed before another worker may reclaim it
const RECLAIM_MIN_IDLE_MS: usize = 10_000;

/// How often the main loop reclaims abandoned messages
const RECLAIM_INTERVAL: Duration = Duration::from_secs(10);

// PRE-ALLOCATED QUERY STRINGS

/// create temp staging table.
/// concurrent workers running this statement won't clash, because the temp
/// table is private to each connection and dropped on commit
const CREATE_STAGE_QUERY: &str =
    "CREATE TEMP TABLE trades_stage (LIKE trades INCLUDING DEFAULTS) ON COMMIT DROP";

/// COPY reclaimed messages into `trades_stage` table
const STAGE_COPY_QUERY: &str = "COPY trades_stage (trade_id, account_id, user_id, direction, symbol_ticker, created_at, updated_at, quantity, price, other_account) FROM STDIN WITH (FORMAT text, DELIMITER '\t', NULL '\\N')";

/// upsert staged rows from `trades_stage` into `trades` table.
/// `DISTINCT ON` guards against duplicate ids within a single reclaim batch
/// (which would otherwise abort the `ON CONFLICT`).
const UPSERT_QUERY: &str = "INSERT INTO trades (trade_id, account_id, user_id, direction, symbol_ticker, created_at, updated_at, quantity, price, other_account) \
    SELECT DISTINCT ON (trade_id) trade_id, account_id, user_id, direction, symbol_ticker, created_at, updated_at, quantity, price, other_account \
    FROM trades_stage ORDER BY trade_id, updated_at DESC NULLS LAST \
    ON CONFLICT (trade_id) DO UPDATE SET \
    account_id = EXCLUDED.account_id, user_id = EXCLUDED.user_id, direction = EXCLUDED.direction, \
    symbol_ticker = EXCLUDED.symbol_ticker, created_at = EXCLUDED.created_at, updated_at = EXCLUDED.updated_at, \
    quantity = EXCLUDED.quantity, price = EXCLUDED.price, other_account = EXCLUDED.other_account";

#[tokio::main]
async fn main() {
    let _ = dotenv();

    if let Err(err) = helpers::init_tracing("trade-writer") {
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
    let stream_name = helpers::require_env("REDIS_STREAM_NAME")?;
    let consumer_group = helpers::require_env("REDIS_CONSUMER_GROUP")?;
    let worker_name = helpers::require_env("WORKER_NAME")?;

    debug!("read env vars");

    let mut pg_client = helpers::connect_postgres(&pg_config).await;
    let mut redis_conn = helpers::connect_redis(redis_url).await;

    // Create Redis Consumer Group dynamically
    let group_create_result: Result<(), redis::RedisError> = redis_conn
        .xgroup_create_mkstream(&stream_name, &consumer_group, "0")
        .await;

    if let Err(e) = group_create_result {
        if e.to_string().contains("BUSYGROUP") {
            debug!("Consumer group '{}' already exists", consumer_group);
        } else {
            helpers::fatal("initializing consumer group failed", e).await;
        }
    }

    info!("Pipeline engaged for stream '{}'", stream_name);

    // buffer to hold bulk COPY data. Pre-allocating ~500KB to avoid reallocations
    let mut copy_payload_buffer = String::with_capacity(512_000);

    // redis will wait for either BATCH_COUNT messages or 100ms, whichever is first
    let opts = StreamReadOptions::default()
        .group(&consumer_group, &worker_name)
        .count(BATCH_COUNT)
        .block(100);

    // new messages
    let new_message_id: [&str; 1] = [">"];

    // (needs to be assigned because of lifetime witchcraft in the select macro)
    let stream_name_arr = [&stream_name];

    // On startup, immediately reclaim messages abandoned by crashed workers
    reclaim_abandoned(
        &mut pg_client,
        &mut redis_conn,
        &stream_name,
        &consumer_group,
        &worker_name,
        &mut copy_payload_buffer,
    )
    .await;
    let mut last_reclaim = Instant::now();

    loop {
        // Select between waiting for Redis stream entries or a shutdown signal:
        let reply: StreamReadReply = tokio::select! {
            res = redis_conn.xread_options(&stream_name_arr, &new_message_id, &opts) => {
                res.context("Redis stream read failed")?
            }
            () = helpers::shutdown_signal() => {
                info!("Shutdown signal received");
                return Ok(());
            }
        };

        if !(reply.keys.is_empty() || reply.keys[0].ids.is_empty()) {
            let ids: Vec<StreamId> = reply.keys.into_iter().flat_map(|key| key.ids).collect();
            debug!("read {} new message(s) from stream", ids.len());
            process_batch(
                &mut pg_client,
                &mut redis_conn,
                &stream_name,
                &consumer_group,
                &mut copy_payload_buffer,
                ids,
            )
            .await;
        }

        // Periodically sweep for messages abandoned by workers that have since
        // crashed while we were running.
        if last_reclaim.elapsed() >= RECLAIM_INTERVAL {
            reclaim_abandoned(
                &mut pg_client,
                &mut redis_conn,
                &stream_name,
                &consumer_group,
                &worker_name,
                &mut copy_payload_buffer,
            )
            .await;
            last_reclaim = Instant::now();
        }
    }
}

/// Reclaim messages that have been pending for longer than
/// [`RECLAIM_MIN_IDLE_MS`], and process them into `copy_payload_buffer`.
///
/// This recovers messages orphaned when a worker crashes and is restarted under
/// a new `WORKER_NAME`, and also retries this worker's own batches that failed
/// to write and were never ACKed.
async fn reclaim_abandoned(
    pg_client: &mut tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
    stream_name: &str,
    consumer_group: &str,
    worker_name: &str,
    copy_payload_buffer: &mut String,
) {
    trace!("sweeping pending list for abandoned messages");

    // XAUTOCLAIM walks the group's pending list from this cursor; "0-0" starts at
    // the beginning and each reply tells us where to resume (or "0-0" when done).
    let mut cursor = "0-0".to_string();

    loop {
        let opts = StreamAutoClaimOptions::default().count(BATCH_COUNT);
        let reply: StreamAutoClaimReply = match redis_conn
            .xautoclaim_options(
                stream_name,
                consumer_group,
                worker_name,
                RECLAIM_MIN_IDLE_MS,
                &cursor,
                opts,
            )
            .await
        {
            Ok(r) => r,
            Err(err) => {
                error!(?err, "failed to XAUTOCLAIM abandoned messages");
                return;
            }
        };

        if !reply.claimed.is_empty() {
            info!("Reclaiming {} pending message(s)", reply.claimed.len());
            process_batch(
                pg_client,
                redis_conn,
                stream_name,
                consumer_group,
                copy_payload_buffer,
                reply.claimed,
            )
            .await;
        }

        // "0-0" means we've swept the whole pending list.
        if reply.next_stream_id == "0-0" {
            break;
        }
        cursor = reply.next_stream_id;
    }
}

/// Decode a batch of stream entries, write them to postgres, and ACK+trim them
/// in redis on success.
async fn process_batch(
    pg_client: &mut tokio_postgres::Client,
    redis_conn: &mut redis::aio::MultiplexedConnection,
    stream_name: &str,
    consumer_group: &str,
    copy_payload_buffer: &mut String,
    ids: Vec<StreamId>,
) {
    let msg_ids = build_payload_buffer(copy_payload_buffer, &ids);
    if msg_ids.is_empty() {
        return;
    }

    // If we parsed 0 valid rows but have msg_ids, we must ACK them so they don't get stuck.
    if copy_payload_buffer.is_empty() {
        warn!(
            "Decoded no valid rows, ACK+trimming {} bad messages to discard them.",
            msg_ids.len()
        );
        if let Err(err) =
            ack_and_trim_stream(redis_conn, stream_name, consumer_group, &msg_ids).await
        {
            error!(?err, "Failed to ACK and trim bad messages in Redis");
        }
        return;
    }

    let write_result = copy_via_staging(pg_client, copy_payload_buffer).await;

    // xack and trim messages in redis ONLY after postgres confirms the write.
    match write_result {
        Ok(()) => {
            info!("Successfully copied {} rows", msg_ids.len());

            match ack_and_trim_stream(redis_conn, stream_name, consumer_group, &msg_ids).await {
                Ok(()) => debug!("ACK+trimmed {} messages from redis stream", msg_ids.len()),
                Err(err) => error!(
                    ?err,
                    "Failed to ACK+trim {} messages from redis stream",
                    msg_ids.len()
                ),
            }
        }
        Err(err) => error!(
            ?err,
            "postgres write failed; leaving messages un-ACKed for retry"
        ),
    }
}

/// COPY the payload buffer into a transient per-transaction staging table, then
/// upsert into `trades`.
///
/// updates on primary-key conflict instead of crashing
async fn copy_via_staging(
    pg_client: &mut tokio_postgres::Client,
    copy_payload_buffer: &str,
) -> Result<()> {
    // use single `Transaction` for the whole thing
    let tx = pg_client
        .transaction()
        .await
        .map_err(helpers::pg_error)
        .context("Failed to open db transaction")?;

    tx.batch_execute(CREATE_STAGE_QUERY)
        .await
        .map_err(helpers::pg_error)
        .context("Failed to create staging table")?;

    // Scope the sink so it is dropped before we run the upsert on `tx`.
    {
        let sink = tx
            .copy_in(STAGE_COPY_QUERY)
            .await
            .map_err(helpers::pg_error)
            .context("Failed to initialize staging COPY context")?;

        helpers::send_copy_payload(sink, copy_payload_buffer)
            .await
            .map_err(helpers::pg_error)
            .context("COPY into staging table failed")?;
    }

    tx.batch_execute(UPSERT_QUERY)
        .await
        .map_err(helpers::pg_error)
        .context("Upsert from staging table failed")?;

    tx.commit()
        .await
        .map_err(helpers::pg_error)
        .context("Failed to commit postgres transaction")?;

    Ok(())
}

fn build_payload_buffer(copy_payload_buffer: &mut String, ids: &[StreamId]) -> Vec<String> {
    let mut msg_ids = Vec::new();
    copy_payload_buffer.clear(); // Clear the buffer for the new batch

    for record in ids {
        msg_ids.push(record.id.clone());

        let Some(redis::Value::BulkString(bytes)) = record.map.get("d") else {
            warn!("Redis message {} missing binary field 'd'", record.id);
            continue; // Skip malformed record
        };

        let trade: TradePayload = match rmp_serde::from_slice(bytes) {
            Ok(t) => t,
            Err(err) => {
                warn!(?err, "Failed to decode payload for {}", record.id);
                continue; // Skip badly serialized record
            }
        };

        let created = jiff::Timestamp::from_second(trade.created_at).map_or_else(
            |_| "\\N".to_string(),
            |z| z.strftime("%Y-%m-%d %H:%M:%S").to_string(),
        );

        let updated = jiff::Timestamp::from_second(trade.updated_at).map_or_else(
            |_| "\\N".to_string(),
            |z| z.strftime("%Y-%m-%d %H:%M:%S").to_string(),
        );

        let other_acc = trade
            .other_account
            .as_deref()
            .filter(|value| !value.is_empty())
            .unwrap_or("\\N");

        let _ = writeln!(
            copy_payload_buffer,
            "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
            trade.trade_id,
            trade.account_id,
            trade.user_id,
            trade.direction,
            trade.symbol_ticker,
            created,
            updated,
            trade.quantity,
            trade.price,
            other_acc
        );
    }

    msg_ids
}

#[derive(Deserialize)]
struct TradePayload {
    trade_id: String,
    account_id: String,
    user_id: String,
    direction: String,
    symbol_ticker: String,
    created_at: i64,
    updated_at: i64,
    quantity: i32,
    price: String,
    other_account: Option<String>,
}

async fn ack_and_trim_stream(
    redis_conn: &mut redis::aio::MultiplexedConnection,
    stream_name: &str,
    consumer_group: &str,
    msg_ids: &[String],
) -> Result<(), redis::RedisError> {
    let _: usize = redis_conn
        .xack(stream_name, consumer_group, msg_ids)
        .await?;

    let _: usize = redis_conn
        .xtrim_options(
            stream_name,
            &StreamTrimOptions::maxlen(StreamTrimmingMode::Exact, 0)
                .set_deletion_policy(StreamDeletionPolicy::Acked),
        )
        .await?;

    Ok(())
}
