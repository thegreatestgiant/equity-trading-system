//! pull market prices of S&P 500 from yahoo finance API
//! and cache them in redis for fast access by the API

use anyhow::{Context, Result};
use dotenvy::dotenv;
use jiff::Timestamp;
use redis::aio::MultiplexedConnection;
use serde::Serialize;
use tracing::{debug, info, trace, warn};
use yahoo_finance_api::{self as yahoo, YahooConnector};

#[tokio::main]
async fn main() {
    let _ = dotenv();

    if let Err(err) = helpers::init_tracing("price-cacher") {
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

    loop {
        let cached = update_all_cached_prices(&mut redis_conn, &symbols)
            .await
            .context("failed to write cached prices to redis")?;
        info!("updated {cached} cached prices");

        debug!(interval, "sleeping until next sync cycle");
        tokio::select! {
            () = tokio::time::sleep(std::time::Duration::from_secs(interval)) => {}
            () = helpers::shutdown_signal() => {
                info!("Shutdown signal received");
                return Ok(());
            }
        }
    }
}

/// a symbol with no usable quote will be skipped rather than aborting the whole
/// cycle. only a redis write failure is reported as an error.
/// returns the number of quotes written.
async fn update_all_cached_prices(
    redis_conn: &mut MultiplexedConnection,
    symbols: &[String],
) -> Result<usize> {
    let mut pipe = redis::pipe();
    let mut queued = 0;
    let mut skipped = 0;

    let provider = yahoo::YahooConnector::new().context("could not construct yahoo client")?;

    for symbol in symbols {
        match get_quote_json(symbol, &provider).await {
            Ok(quote) => {
                trace!("queued {symbol} quote for caching");
                pipe.hset("market_prices", symbol, &quote);
                queued += 1;
            }
            Err(err) => {
                warn!(?err, "could not get quote for {symbol}. skipping");
                skipped += 1;
            }
        }
    }

    if skipped > 0 {
        warn!("skipped {skipped} symbols with no usable quote");
    }

    if queued == 0 {
        warn!("no usable quotes for any symbol. cycle aborted");
        return Ok(0);
    }

    debug!("writing {queued} quotes to redis in one pipeline");
    pipe.query_async::<()>(redis_conn)
        .await
        .context("failed to execute redis pipeline")?;
    debug!("redis pipeline executed");

    Ok(queued)
}

#[derive(Serialize)]
struct MarketData {
    open_price: f64,
    latest_price: f64,
    latest_time: String,
}

async fn get_quote_json(symbol: &str, provider: &YahooConnector) -> Result<String> {
    // 1-minute intervals for the current day
    let response = provider
        .get_quote_range(symbol, "1m", "1d")
        .await
        .context("yahoo quote request failed")?;

    let quotes = response
        .quotes()
        .context("yahoo response had no usable quotes")?;

    // first bar in day is open, last is latest available
    let first_quote = quotes.first().context("no opening price data found")?;
    let last_quote = quotes.last().context("no current price data found")?;

    let data = MarketData {
        open_price: first_quote.open,
        latest_price: last_quote.close,
        // ts will be string formatted in ISO 8601 - YYYY-MM-DDTHH:MM:SSZ
        latest_time: Timestamp::from_second(last_quote.timestamp as i64)
            .with_context(|| format!("invalid latest timestamp {}", last_quote.timestamp))?
            .to_string(),
    };

    trace!(symbol, latest = data.latest_price, "built market data");
    serde_json::to_string(&data)
        .with_context(|| format!("could not serialize market data for {symbol}"))
}
