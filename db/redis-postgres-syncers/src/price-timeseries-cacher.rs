//! store historical market data of s&p 500 stocks' prices in redis as time series
//!
//! Each symbol gets a 1-minute series that feeds three coarser tiers through
//! compaction rules. Every tier carries its own retention, so history
//! automatically decays into progressively coarser buckets as it ages:
//!
//!   price_history:{SYM}       raw 1m samples, kept 1 day
//!   price_history:{SYM}:1h    hourly bars,    kept 1 week
//!   price_history:{SYM}:1d    daily bars,     kept 1 year
//!
//! The API can read a window at the appropriate resolution with TS.RANGE, e.g.
//! `TS.RANGE price_history:AAPL:1d - +` for the last year of daily closes.

use anyhow::{Context, Result};
use dotenvy::dotenv;
use redis::aio::MultiplexedConnection;
use tracing::{debug, info, trace, warn};
use yahoo_finance_api as yahoo;

/// Retention of the raw 1-minute source series (1 day, in milliseconds).
const RAW_RETENTION_MS: i64 = 24 * 60 * 60 * 1000;

/// A compacted tier derived from the raw series: how wide each bucket is and
/// how long the downsampled bars are kept before they expire.
struct Tier {
    suffix: &'static str,
    bucket_ms: i64,
    retention_ms: i64,
}

const TIERS: &[Tier] = &[
    // hourly bars, kept for a week
    Tier {
        suffix: "1h",
        bucket_ms: 60 * 60 * 1000,
        retention_ms: 7 * 24 * 60 * 60 * 1000,
    },
    // daily bars, kept for a year
    Tier {
        suffix: "1d",
        bucket_ms: 24 * 60 * 60 * 1000,
        retention_ms: 365 * 24 * 60 * 60 * 1000,
    },
];

#[tokio::main]
async fn main() {
    let _ = dotenv();

    if let Err(err) = helpers::init_tracing("price-timeseries-cacher") {
        eprintln!("failed to initialize tracing: {:?}", err);
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        std::process::exit(1);
    }

    if let Err(err) = run().await {
        helpers::fatal("Fatal error", err).await;
    }
}

async fn run() -> Result<()> {
    let redis_url = helpers::require_env("REDIS_URL")?;
    let interval: u64 = helpers::require_env("DELAY")?
        .parse()
        .context("DELAY must be an int")?;

    debug!(interval, "read env vars");

    let mut redis_conn = helpers::connect_redis(redis_url).await;

    let symbols = helpers::fetch_sp500_symbols()
        .await
        .context("could not fetch S&P 500 symbol list")?;

    info!(
        "ensuring time series and compaction rules for {} symbols",
        symbols.len()
    );
    for symbol in &symbols {
        // already-provisioned symbols are skipped by ensure_series
        ensure_series(&mut redis_conn, symbol)
            .await
            .with_context(|| format!("failed to provision time series for {symbol}"))?;
    }
    debug!("ensured {} time series", symbols.len());

    loop {
        let appended = append_all_latest_samples(&mut redis_conn, &symbols)
            .await
            .context("failed to append latest samples to redis")?;
        info!("appended {appended} latest samples");

        debug!(interval, "sleeping until next append cycle");
        tokio::select! {
            () = tokio::time::sleep(std::time::Duration::from_secs(interval)) => {}
            () = helpers::shutdown_signal() => {
                info!("Shutdown signal received");
                return Ok(());
            }
        }
    }
}

/// Key of the raw 1-minute source series for a symbol.
fn raw_key(symbol: &str) -> String {
    format!("price_history:{symbol}")
}

/// Create the raw source series and its compaction tiers for a symbol.
///
/// Skips symbols whose raw series already exists so restarts stay cheap, and
/// tolerates "already exists" errors in case provisioning was interrupted.
async fn ensure_series(redis_conn: &mut MultiplexedConnection, symbol: &str) -> Result<()> {
    let raw = raw_key(symbol);

    let exists: bool = redis::cmd("EXISTS")
        .arg(&raw)
        .query_async(redis_conn)
        .await
        .with_context(|| format!("EXISTS check for {raw} failed"))?;
    if exists {
        trace!(symbol, "raw series already provisioned, skipping");
        return Ok(());
    }

    debug!(symbol, "provisioning raw series and compaction tiers");
    // raw 1-minute source that everything else is compacted from
    create_series(redis_conn, &raw, RAW_RETENTION_MS, symbol, "1m").await?;

    for tier in TIERS {
        let dest = format!("{raw}:{}", tier.suffix);
        create_series(redis_conn, &dest, tier.retention_ms, symbol, tier.suffix).await?;
        create_rule(redis_conn, &raw, &dest, tier.bucket_ms).await?;
        trace!(symbol, tier = tier.suffix, "provisioned tier");
    }

    Ok(())
}

async fn create_series(
    redis_conn: &mut MultiplexedConnection,
    key: &str,
    retention_ms: i64,
    symbol: &str,
    tier: &str,
) -> Result<()> {
    let mut cmd = redis::cmd("TS.CREATE");
    cmd.arg(key)
        .arg("RETENTION")
        .arg(retention_ms)
        .arg("DUPLICATE_POLICY")
        .arg("LAST")
        .arg("LABELS")
        .arg("symbol")
        .arg(symbol)
        .arg("tier")
        .arg(tier);

    run_ignoring_exists(redis_conn, &cmd, &format!("TS.CREATE {key}")).await
}

async fn create_rule(
    redis_conn: &mut MultiplexedConnection,
    source: &str,
    dest: &str,
    bucket_ms: i64,
) -> Result<()> {
    // "last" downsamples each bucket to its closing price, matching how a
    // coarser candlestick's close is defined.
    let mut cmd = redis::cmd("TS.CREATERULE");
    cmd.arg(source)
        .arg(dest)
        .arg("AGGREGATION")
        .arg("last")
        .arg(bucket_ms);

    run_ignoring_exists(
        redis_conn,
        &cmd,
        &format!("TS.CREATERULE {source} -> {dest}"),
    )
    .await
}

/// Run a command, swallowing the benign errors RedisTimeSeries returns when a
/// series or rule was already created by a previous run. `label` names the
/// command for logging and for the error message on a genuine failure.
async fn run_ignoring_exists(
    redis_conn: &mut MultiplexedConnection,
    cmd: &redis::Cmd,
    label: &str,
) -> Result<()> {
    match cmd.query_async::<()>(redis_conn).await {
        Ok(()) => {
            trace!("{label} ok");
            Ok(())
        }
        Err(e) => {
            let msg = e.to_string().to_lowercase();
            if msg.contains("already exists") || msg.contains("already has") {
                trace!("{label} already provisioned, ignoring");
                Ok(())
            } else {
                Err(anyhow::Error::new(e).context(format!("{label} failed")))
            }
        }
    }
}

/// Fetch the latest price for every symbol and append it to the raw series in a
/// single pipeline. The compaction rules fan each sample out to the tiers.
async fn append_all_latest_samples(
    redis_conn: &mut MultiplexedConnection,
    symbols: &[String],
) -> Result<usize> {
    let mut pipe = redis::pipe();
    let mut queued = 0;
    let mut skipped = 0;

    for symbol in symbols {
        let (timestamp_ms, price) = match get_latest_sample(symbol).await {
            Ok(sample) => sample,
            Err(err) => {
                warn!(symbol, ?err, "skipping symbol with no usable price");
                skipped += 1;
                continue;
            }
        };

        trace!(symbol, timestamp_ms, price, "queued sample");
        pipe.cmd("TS.ADD")
            .arg(raw_key(symbol))
            .arg(timestamp_ms)
            .arg(price)
            .arg("ON_DUPLICATE")
            .arg("LAST");
        queued += 1;
    }

    if skipped > 0 {
        warn!("skipped {skipped} symbols with no usable price this cycle");
    }

    if queued == 0 {
        warn!("no usable price for any symbol this cycle; nothing appended");
        return Ok(0);
    }

    debug!("appending {queued} samples to redis in one pipeline");
    pipe.query_async::<()>(redis_conn)
        .await
        .with_context(|| format!("redis pipeline TS.ADD of {queued} samples failed"))?;
    debug!("redis pipeline executed");

    Ok(queued)
}

/// Latest `(timestamp_ms, price)` for a symbol from yahoo's 1-minute intraday
/// feed. Walks back from the most recent bar to skip trailing empty candles,
/// whose close yahoo reports as NaN.
async fn get_latest_sample(symbol: &str) -> Result<(i64, f64)> {
    let provider = yahoo::YahooConnector::new().context("could not construct yahoo client")?;

    let response = provider
        .get_quote_range(symbol, "1m", "1d")
        .await
        .context("yahoo quote request failed")?;
    let quotes = response
        .quotes()
        .context("yahoo response had no usable quotes")?;

    let quote = quotes
        .iter()
        .rev()
        .find(|quote| quote.close.is_finite())
        .context("no finite price data found")?;

    // yahoo reports seconds; RedisTimeSeries works in milliseconds
    let timestamp_ms = (quote.timestamp as i64) * 1000;

    Ok((timestamp_ms, quote.close))
}
