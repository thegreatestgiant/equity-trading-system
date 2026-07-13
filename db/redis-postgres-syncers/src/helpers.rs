//! common functions for these bins

use anyhow::{Context, Result};
use bytes::Bytes;
use futures_util::SinkExt;
use serde::Deserialize;
use std::env;
use tokio_postgres::{Client, CopyInSink, NoTls};
use tracing::{debug, error, info, trace, warn};
use tracing_loki::url::Url;
use tracing_subscriber::{filter::LevelFilter, layer::SubscriberExt, util::SubscriberInitExt};

/// Read a required environment variable, or return a descriptive error.
pub fn require_env(name: &str) -> Result<String> {
    env::var(name).with_context(|| format!("{name} must be set"))
}

/// Log a specific fatal error, wait 1/2 sec, then exit
///
/// Returns `!` so it can be used directly in a `match` arm
pub async fn fatal(message: &str, err: impl std::fmt::Debug) -> ! {
    error!(message, ?err);
    tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    std::process::exit(1);
}

/// Open a multiplexed async redis connection, or log the error and exit.
pub async fn connect_redis(url: String) -> redis::aio::MultiplexedConnection {
    let client = match redis::Client::open(url) {
        Ok(client) => client,
        Err(e) => fatal("failed to open redis client", e).await,
    };
    match client.get_multiplexed_async_connection().await {
        Ok(conn) => {
            debug!("connected to redis");
            conn
        }
        Err(e) => fatal("failed to connect to redis", e).await,
    }
}

/// Connect to postgres and spawn the connection driver, or log the error and exit.
pub async fn connect_postgres(config: &str) -> Client {
    let (client, connection) = match tokio_postgres::connect(config, NoTls).await {
        Ok(pair) => pair,
        Err(e) => fatal("failed to connect to postgres", e).await,
    };
    tokio::spawn(async move {
        if let Err(err) = connection.await {
            fatal("postgres connection driver error", err).await;
        }
    });
    debug!("connected to postgres");
    client
}

/// Convert a postgres-related error into an `anyhow::Error` that includes
/// postgres info if it was a `DbError`
pub fn pg_error(err: tokio_postgres::Error) -> anyhow::Error {
    match err.as_db_error() {
        Some(db_error) => anyhow::anyhow!("{db_error:?}"),
        None => anyhow::Error::new(err),
    }
}

/// Send an entire COPY payload over a sink in one chunk and close it.
pub async fn send_copy_payload(
    sink: CopyInSink<Bytes>,
    payload: &str,
) -> Result<(), tokio_postgres::Error> {
    tokio::pin!(sink);
    sink.send(Bytes::from(payload.to_owned())).await?;
    sink.close().await?;
    Ok(())
}

pub fn init_tracing(app_name: &str) -> Result<()> {
    let loki_url = env::var("LOKI_URL").context("LOKI_URL must be set")?;
    let worker_name = env::var("WORKER_NAME").context("WORKER_NAME must be set")?;

    let loki_url = Url::parse(&loki_url).context("LOKI_URL is not a valid URL")?;
    let (loki_layer, loki_task) = tracing_loki::builder()
        .label("app", app_name)?
        .label("pod", worker_name)?
        .build_url(loki_url)?;

    tracing_subscriber::registry()
        .with(LevelFilter::DEBUG)
        .with(loki_layer)
        // .with(tracing_subscriber::fmt::layer().with_writer(std::io::stdout))
        .init();

    tokio::spawn(loki_task);

    info!(build = %build_info(), "=== STARTING {app_name} ===");

    Ok(())
}

/// build metadata captured at compile time by `build.rs`
pub fn build_info() -> String {
    // env!() "Inspects an environment variable at compile time"
    let source = env!("BUILD_SOURCE");
    let hash = env!("BUILD_GIT_HASH");
    let built = env!("BUILD_UNIX_SECS")
        .parse::<i64>()
        .ok()
        .and_then(|secs| jiff::Timestamp::from_second(secs).ok())
        .map(|ts| ts.strftime("%Y-%m-%d %H:%M:%S UTC").to_string())
        .unwrap_or_else(|| "unknown".to_string());
    format!("built by {source}, from commit {hash}, on {built}")
}

pub async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install SIGTERM handler");
    };

    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    tokio::select! {
        () = ctrl_c => {},
        () = terminate => {},
    }
}

#[derive(Debug, Deserialize)]
struct Record {
    #[serde(rename = "Symbol")]
    symbol: String,
}

pub async fn fetch_sp500_symbols() -> Result<Vec<String>> {
    const URL: &str = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv";
    let response = reqwest::get(URL)
        .await
        .context("request for S&P 500 csv failed")?
        .text()
        .await
        .context("reading S&P 500 csv body failed")?;
    debug!("fetched S&P 500 csv ({} bytes)", response.len());

    let mut rdr = csv::Reader::from_reader(response.as_bytes());
    let mut symbols = Vec::new();

    for result in rdr.deserialize() {
        let record: Record = result.context("malformed row in S&P 500 csv")?;
        // Fix for symbols that Yahoo represents differently (e.g., BRK.B instead of BRK-B)
        let formatted_symbol = record.symbol.replace('.', "-");
        trace!(symbol = %formatted_symbol, "parsed symbol");
        symbols.push(formatted_symbol);
    }

    if symbols.len() == 500 {
        info!("fetched S&P 500 symbol list");
    } else {
        warn!("got {} symbols instead of 500", symbols.len());
    }

    Ok(symbols)
}
