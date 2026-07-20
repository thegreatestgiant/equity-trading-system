from fastapi import HTTPException
from datetime import datetime, timezone
import json
import uuid
import time
import msgpack
from app.core.redis import redis_client, USERS_KEY, ACCOUNTS_KEY, POSITIONS_KEY
from app.core.logging import logger
from app.core.config import TRADE_STREAM
from app.services import ticker_service


async def individual_trade(user_id: str, trade: dict):
    logger.info("Booking a trade")
    start = time.perf_counter()
    # Fetch user and account data in one round trip
    pipe = redis_client.pipeline()
    pipe.hget(USERS_KEY, user_id)
    pipe.hget(ACCOUNTS_KEY, trade["account_id"])
    raw_user, raw_account = await pipe.execute()

    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    if raw_account is None:
        raise HTTPException(
            status_code=404, detail=f"Account number {trade['account_id']} does not exist"
        )
    account_data = json.loads(raw_account)

    await verify_trade_details(trade, user_data)

    other_account = trade.get("other_account")

    trade_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    packed_bytes = create_payload(trade, trade_id, now, None, other_account, user_id)

    lock_names = sorted(
        {
            f"account:{trade['account_id']}",
            f"position:{trade['account_id']}:{trade['ticker']}",
        }
    )
    acquired_locks = []
    locks = [
        redis_client.lock(
            name,
            timeout=30,
            blocking_timeout=5,
        )
        for name in lock_names
    ]

    try:
        # Acquire every lock
        for lock in locks:
            acquired = await lock.acquire()
            if not acquired:
                raise HTTPException(
                    status_code=409, detail="Could not acquire required locks."
                )
            acquired_locks.append(lock)

        new_position = None
        pipe = redis_client.pipeline()

        for position_uuid in account_data["positions"]:
            pipe.hget(POSITIONS_KEY, position_uuid)
        results = await pipe.execute()

        for position_uuid, raw_position in zip(account_data["positions"], results):
            if raw_position is None:
                continue
            real_position_data = json.loads(raw_position)
            if (
                real_position_data["symbol_ticker"] == trade["ticker"]
            ):  # Correct account and ticker
                position_key = position_uuid
                specific_position = real_position_data
                if (
                    trade["direction"] == "Sell"
                    and real_position_data["quantity"] - trade["quantity"] < 0
                    and not account_data["can_short"]
                ):  # Check if trying to short
                    logger.warning("Invalid short attempt")
                    raise HTTPException(
                        status_code=403,
                        detail=f"Account number {trade['account_id']} does not have permission to short",
                    )
                new_position = (
                    real_position_data["quantity"] + trade["quantity"]
                    if trade["direction"] == "Buy"
                    else real_position_data["quantity"] - trade["quantity"]
                )  # Save what the new position will be

                break  # only one account and one ticker
        if new_position is None:  # This position does not currently exist
            if trade["direction"] != "Buy" and not account_data["can_short"]:
                logger.warning("Invalid short attempt")
                raise HTTPException(
                    status_code=403,
                    detail=f"Account number {trade['account_id']} does not have permission to short",
                )

            new_position = (
                trade["quantity"]
                if trade["direction"] == "Buy"
                else 0 - trade["quantity"]
            )

            average_cost = trade["price"]
            total_realized_gains = 0

            position_key = str(uuid.uuid4())
            position_data = {
                "account_id": trade["account_id"],
                "symbol_ticker": trade["ticker"],
                "quantity": new_position,
                "average_cost": average_cost,
                "total_realized_gains": total_realized_gains,
                "created_at": now_str,
                "updated_at": now_str,
            }
            account_data["positions"].append(position_key)
            account_data["updated_at"] = now_str

            pipe = redis_client.pipeline(transaction=True)
            pipe.hset(  # Set the new position
                POSITIONS_KEY, position_key, json.dumps(position_data)
            )
            pipe.hset(
                ACCOUNTS_KEY, trade["account_id"], json.dumps(account_data)
            )
            # High Efficiency: Save to a single field named "d"
            pipe.xadd(TRADE_STREAM, {"d": packed_bytes})
            await pipe.execute()
            logger.info("Created new position for account")
        else:  # Editing existing position
            # Reuse the position already read above instead of re-fetching it
            # Edit the existing position data
            new_average_cost, realized_pnl = calculate_p_and_l_changes(
                trade, specific_position, new_position
            )
            specific_position["average_cost"] = new_average_cost
            specific_position["total_realized_gains"] = (
                specific_position["total_realized_gains"] + realized_pnl
            )
            specific_position["quantity"] = new_position
            specific_position["updated_at"] = now_str

            pipe = redis_client.pipeline(transaction=True)
            pipe.hset(
                POSITIONS_KEY, position_key, json.dumps(specific_position)
            )
            # High Efficiency: Save to a single field named "d"
            pipe.xadd(TRADE_STREAM, {"d": packed_bytes})
            await pipe.execute()
            logger.info("Updated existing position for account")

    finally:
        # Always release, even if something throws
        for lock in reversed(acquired_locks):
            try:
                await lock.release()
            except Exception:
                logger.error("Failed to release Redis lock")

    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(f"Successfully booked a trade. Completed in {duration_ms:.2f}ms")

    return {"status": "success", "trade_id": f"{trade_id}"}


def create_payload(
    trade: dict,
    trade_id: str,
    now: datetime,
    old_time: datetime,
    other_account: str | None,
    user_id: str,
):
    now_int = int(now.timestamp())
    payload = {
        "trade_id": trade_id,
        "account_id": trade["account_id"],
        "user_id": user_id,
        "direction": trade["direction"],  # Must be exact string: 'Buy' or 'Sell'
        "symbol_ticker": trade["ticker"],
        "created_at": int(old_time.timestamp()) if old_time else now_int,
        "updated_at": now_int,
        "quantity": int(trade["quantity"]),
        "price": str(trade["price"]),  # Kept as string for Postgres NUMERIC ingestion
        "other_account": other_account,  # Can be None/Null
    }
    packed_bytes = msgpack.packb(payload, use_bin_type=True)
    return packed_bytes


async def verify_trade_details(trade: dict, user_data: dict):
    # Confirm you have access to this account
    if trade["account_id"] not in user_data["accounts_associated"]:
        logger.warning("Invalid account_id for user")
        raise HTTPException(
            status_code=401,
            detail=f"You do not have access to account {trade['account_id']}",
        )

    # Check ticker exists
    await verify_ticker_exists(trade["ticker"])

    # Ensure valid direction
    if trade["direction"] not in ("Buy", "Sell"):
        logger.warning("Invalid direction for trade")
        raise HTTPException(status_code=422, detail="Not a valid Direction")

    # Ensure valid quantity
    if trade["quantity"] < 1:
        logger.warning("Invalid quantity for trade")
        raise HTTPException(status_code=422, detail="Not a valid quantity value")


async def verify_account_access(account_id: str, user_id: str):
    raw_user = await redis_client.hget(USERS_KEY, user_id)
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts_associated"]:
        logger.warning("Invalid account_id for user")
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )


async def verify_ticker_exists(ticker: str):
    if ticker not in ticker_service.valid_tickers:
        logger.warning("Invalid ticker")
        raise HTTPException(status_code=422, detail=f"Ticker {ticker} does not exist")


async def get_user_data(user_id: str) -> dict:
    raw_user = await redis_client.hget(USERS_KEY, user_id)
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    return json.loads(raw_user)


async def get_account_data(account_id: str) -> dict:
    raw_account = await redis_client.hget(ACCOUNTS_KEY, account_id)
    if raw_account is None:
        raise HTTPException(
            status_code=404, detail=f"Account number {account_id} does not exist"
        )
    return json.loads(raw_account)


def calculate_p_and_l_changes(trade: dict, specific_position: dict, new_position: int):
    qty = specific_position["quantity"]
    avg = specific_position["average_cost"]

    trade_qty = trade["quantity"]
    trade_price = trade["price"]

    new_avg_cost = specific_position["average_cost"]
    realized_gains = 0

    if qty == 0:
        return trade_price, 0

    if qty > 0 and trade["direction"] == "Buy":
        new_avg_cost = (avg * qty + trade_price * trade_qty) / (qty + trade_qty)

    elif qty > 0 and trade["direction"] == "Sell":
        if new_position > 0:
            realized_gains = (trade_price - avg) * trade_qty
        elif new_position == 0:
            realized_gains = (trade_price - avg) * trade_qty
            new_avg_cost = 0
        else:
            realized_gains = (trade_price - avg) * qty
            new_avg_cost = trade_price

    elif qty < 0 and trade["direction"] == "Sell":
        new_avg_cost = (avg * abs(qty) + trade_price * trade_qty) / (
            abs(qty) + trade_qty
        )

    elif qty < 0 and trade["direction"] == "Buy":
        if new_position < 0:
            realized_gains = (avg - trade_price) * trade_qty
        elif new_position == 0:
            realized_gains = (avg - trade_price) * trade_qty
            new_avg_cost = 0
        else:
            realized_gains = (avg - trade_price) * abs(qty)
            new_avg_cost = trade_price

    return new_avg_cost, realized_gains
