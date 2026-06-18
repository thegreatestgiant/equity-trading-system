//! Write trades from redis stream (sent by API) to postgres

use dotenvy::dotenv;
use futures_util::SinkExt;
use redis::AsyncCommands;
use redis::streams::{StreamReadOptions, StreamReadReply};
use serde::Deserialize;
use std::env;
use std::error::Error;
use std::{thread::sleep, time};
use tokio_postgres::NoTls;

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

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    // get config from env vars
    let _ = dotenv();

    let pg_config =
        env::var("DATABASE_URL").expect("DATABASE_URL environment variable must be set");

    let redis_url = env::var("REDIS_URL").expect("REDIS_URL environment variable must be set");

    let stream_name =
        env::var("REDIS_STREAM_NAME").expect("REDIS_STREAM_NAME environment variable must be set");

    let consumer_group = env::var("REDIS_CONSUMER_GROUP")
        .expect("REDIS_CONSUMER_GROUP environment variable must be set");

    let worker_name =
        env::var("WORKER_NAME").expect("WORKER_NAME environment variable must be set");

    println!("read env vars");

    let dur = time::Duration::from_secs(5);
    sleep(dur);

    // connect to postgres
    let (pg_client, connection) = tokio_postgres::connect(&pg_config, NoTls).await?;
    tokio::spawn(async move {
        if let Err(e) = connection.await {
            eprintln!("PostgreSQL connection driver error: {}", e);
        }
    });

    println!("connected to postgres");

    // connect to redis
    let redis_client = redis::Client::open(redis_url)?;
    let mut redis_conn = redis_client.get_multiplexed_async_connection().await?;

    println!("connected to redis");

    // Create Redis Consumer Group dynamically and ensure the stream exists
    let group_create_result: Result<(), redis::RedisError> = redis_conn
        .xgroup_create_mkstream(&stream_name, &consumer_group, "0")
        .await;

    match group_create_result {
        Ok(_) => println!("Consumer group '{}' verified/created", consumer_group),
        Err(e) => {
            // If the group already exists (BUSYGROUP), we can safely ignore the error on restart.
            if !e.to_string().contains("BUSYGROUP") {
                eprintln!("Initializing consumer group failed: {}", e);
            }
        }
    }
    println!(
        "Pipeline engaged for stream '{}'",
        stream_name
    );

    loop {
        // Fetch batches from the configured redis stream
        let opts = StreamReadOptions::default()
            .group(&consumer_group, &worker_name)
            .count(3)
            .block(100);

        let reply: StreamReadReply = match redis_conn
            .xread_options(&[&stream_name], &[">"], &opts)
            .await
        {
            Ok(r) => r,
            Err(e) => {
                eprintln!("Redis stream read failed: {}", e);
                tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
                continue;
            }
        };

        let mut msg_ids = Vec::new();
        let mut copy_buffer = String::new();

        for stream_key in reply.keys {
            for record in stream_key.ids {
                msg_ids.push(record.id.clone());

                // Extract binary payload from the single field "d"
                if let Some(redis::Value::BulkString(bytes)) = record.map.get("d")
                    && let Ok(trade) = rmp_serde::from_slice::<TradePayload>(bytes)
                {
                    // format dates for postgres text input
                    let created = jiff::Timestamp::from_second(trade.created_at)
                        .map(|z| z.strftime("%Y-%m-%d %H:%M:%S").to_string())
                        .unwrap_or_else(|_| "\\N".to_string());

                    let updated = jiff::Timestamp::from_second(trade.updated_at)
                        .map(|z| z.strftime("%Y-%m-%d %H:%M:%S").to_string())
                        .unwrap_or_else(|_| "\\N".to_string());

                    let other_acc = trade.other_account.unwrap_or_else(|| "\\N".to_string());

                    // Generate a standard Tab-Separated line format for standard COPY protocol
                    let row = format!(
                        "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n",
                        trade.trade_id,
                        trade.account_id,
                        trade.user_id,
                        trade.direction, // Maps to Postgres ENUM directly via text
                        trade.symbol_ticker,
                        created,
                        updated,
                        trade.quantity,
                        trade.price,
                        other_acc
                    );
                    copy_buffer.push_str(&row);
                }
            }
        }

        // If no records were processed, loop back and block again
        if msg_ids.is_empty() {
            continue;
        }

        // postgres bulk COPY operation
        let copy_query = "COPY trade (trade_id, account_id, user_id, direction, symbol_ticker, created_at, updated_at, quantity, price, other_account) FROM STDIN WITH (FORMAT text, DELIMITER '\t', NULL '\\N')";

        match pg_client.copy_in(copy_query).await {
            Ok(sink) => {
                tokio::pin!(sink);

                // Stream the memory buffer directly to the database system
                if let Err(e) = sink.send(bytes::Bytes::from(copy_buffer)).await {
                    eprintln!("Streaming buffer via COPY failed: {}", e);
                    continue;
                }

                if let Err(e) = sink.close().await {
                    eprintln!("Finalizing COPY transaction failed: {}", e);
                    continue;
                }

                // 4. Acknowledge messages in Redis only after Postgres safe-write confirmation
                let _: Result<(), _> = redis_conn
                    .xack(&stream_name, &consumer_group, &msg_ids)
                    .await;
            }
            Err(e) => {
                eprintln!("Failed to initialize Postgres COPY stream context: {}", e);
            }
        }
    }
}
