#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "msgpack>=1.2.1",
#     "redis>=8.0.0",
# ]
# ///

# for testing the trade writer. send A LOT of trades to redis

import asyncio
import random
import string
import os
import time
import uuid
import msgpack
import redis.asyncio as aioredis
# import itertools

# # AAA, AAB, ..., ZZY, ZZZ
# # 17_576 combinations
# TICKERS = ["".join(c) for c in itertools.product(string.ascii_uppercase, repeat=3)]

# just 26 tickers
TICKERS = [c * 3 for c in string.ascii_uppercase]

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

# 2. Update line 27
redis_client = aioredis.Redis(host=REDIS_HOST, port=6379, db=0)


async def individual_trade(trade: dict):
    """
    copied from important bits of corresponding fn in API, to guarantee compatibility
    """

    payload = {
        "trade_id": str(uuid.uuid4()),
        "account_id": trade["account_id"],
        "user_id": trade["user_id"],
        "direction": trade["direction"],
        "symbol_ticker": trade["ticker"],
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "quantity": int(trade["quantity"]),
        "price": str(trade["price"]),
        "other_account": trade.get("other_account"),
    }
    packed_bytes = msgpack.packb(payload)
    await redis_client.xadd("trade_stream", {"d": packed_bytes})


async def generate_fake_trades():
    redis_client = aioredis.from_url(f"redis://{REDIS_HOST}:6379")

    try:
        for symbol in TICKERS:
            direction = random.choice(["Buy", "Sell"])
            quantity = random.randint(1, 500)
            price = f"{random.uniform(10.0, 1500.0):.2f}"
            other_account = str(uuid.uuid4()) if random.random() < 0.3 else None

            trade = {
                "account_id": str(uuid.uuid4()),
                "user_id": str(uuid.uuid4()),
                "direction": direction,
                "ticker": symbol,
                "quantity": quantity,
                "price": price,
                "other_account": other_account,
            }

            await individual_trade(trade)

            print(f"[SENT] {direction} {quantity} {symbol} @ {price}")

            # # Throttle the loop so it doesn't overwhelm redis
            # await asyncio.sleep(0.1)

    except asyncio.CancelledError:
        print("\nStopping the generator safely...")
    finally:
        # Gracefully close the Redis connection pool
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(generate_fake_trades())
