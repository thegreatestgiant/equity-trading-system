from fastapi import HTTPException
from datetime import datetime, timezone
import json
import uuid
import time
import msgpack
from app.core.redis import redis_client, redis_dictionaries
from app.core.logging import logger
from app.core.config import TRADE_STREAM
from app.services import ticker_service


async def individual_trade(user_id: str, trade: dict):
    logger.info("Booking a trade")
    start = time.perf_counter()

    # Ensure it's a valid user
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    #redis_user_get_duration = time.perf_counter() - start

    # Ensure it's a valid account
    raw_account = await redis_client.hget(redis_dictionaries[1], trade["account_id"])
    if not raw_account:
        logger.warning("Invalid account_id for booking")
        raise HTTPException(status_code=404, detail=f"Account number {trade['account_id']} does not exist")
    account_data = json.loads(raw_account)

    #redis_account_get_duration = time.perf_counter() - redis_user_get_duration - start

    # Confirm you have access to this account
    if trade["account_id"] not in user_data["accounts_associated"]:
        logger.warning("Invalid account_id for booking")
        raise HTTPException(
            status_code=401, detail=f"You do not have access to account {trade['account_id']}"
        )

    # Check ticker exists
    if trade["ticker"] not in ticker_service.valid_tickers:
        logger.warning("Invalid ticker for booking")
        raise HTTPException(status_code=422, detail=f"Ticker {trade['ticker']} does not exist")

    # Ensure calid direction
    if trade["direction"] not in ("Buy", "Sell"):
        logger.warning("Invalid direction for booking")
        raise HTTPException(status_code=422, detail="Not a valid Direction")

    # Ensure valid quantity
    if trade["quantity"] < 0:
        logger.warning("Invalid quantity for booking")
        raise HTTPException(status_code=422, detail="Not a valid quantity value")

    other_account = trade.get("other_account")

    if other_account:
        try:
            uuid.UUID(other_account, version=4)
        except ValueError:
            trade["other_account"] = None
    else:
        trade["other_account"] = None

    # trade_validation_duration = (
    #     time.perf_counter()
    #     - redis_account_get_duration
    #     - redis_user_get_duration
    #     - start
    # )

    trade_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    now_int = int(now.timestamp())
    payload = {
        "trade_id": trade_id,
        "account_id": trade["account_id"],
        "user_id": user_id,
        "direction": trade["direction"],  # Must be exact string: 'Buy' or 'Sell'
        "symbol_ticker": trade["ticker"],
        "created_at": now_int,
        "updated_at": now_int,
        "quantity": int(trade["quantity"]),
        "price": str(trade["price"]),  # Kept as string for Postgres NUMERIC ingestion
        "other_account": trade["other_account"],  # Can be None/Null
    }

    # Pack to raw binary
    packed_bytes = msgpack.packb(payload)

    # lock_init_duration = (
    #     time.perf_counter()
    #     - trade_validation_duration
    #     - redis_account_get_duration
    #     - redis_user_get_duration
    #     - start
    # )

    lock = redis_client.lock(
        f"position:{trade['account_id']}:{trade['ticker']}",
        timeout=30,
        blocking_timeout=5,
    )

    async with lock:
        new_position = None
        pipe = redis_client.pipeline()

        for position_uuid in account_data["positions"]:
            pipe.hget(redis_dictionaries[2], position_uuid)

        results = await pipe.execute()

        # redis_position_get_duration = (
        #     time.perf_counter()
        #     - lock_init_duration
        #     - trade_validation_duration
        #     - redis_account_get_duration
        #     - redis_user_get_duration
        #     - start
        # )

        for position_uuid, raw_position in zip(account_data["positions"], results):
            if raw_position is None:
                continue
            real_position_data = json.loads(raw_position)
            if (
                real_position_data["symbol_ticker"] == trade["ticker"]
            ):  # Correct account and ticker
                position_key = position_uuid
                if (
                    trade["direction"] == "Sell"
                    and real_position_data["quantity"] - trade["quantity"] < 0
                    and not account_data["can_short"]
                ):  # Check if trying to short
                    logger.warning("Invalid short attempt")
                    raise HTTPException(
                        status_code=403, detail=f"Account number {trade['account_id']} does not have permission to short"
                    )
                new_position = (
                    real_position_data["quantity"] + trade["quantity"]
                    if trade["direction"] == "Buy"
                    else real_position_data["quantity"] - trade["quantity"]
                )  # Save what the new position will be

                break  # only one account and one ticker

        # position_calculation_duration = (
        #     time.perf_counter()
        #     - redis_position_get_duration
        #     - lock_init_duration
        #     - trade_validation_duration
        #     - redis_account_get_duration
        #     - redis_user_get_duration
        #     - start
        # )

        if new_position is None:  # This position does not currently exist
            if trade["direction"] != "Buy" and not account_data["can_short"]:
                logger.warning("Invalid short attempt")
                raise HTTPException(
                    status_code=403, detail=f"Account number {trade['account_id']} does not have permission to short"
                )
            new_position = (
                trade["quantity"]
                if trade["direction"] == "Buy"
                else 0 - trade["quantity"]
            )
            position_key = str(uuid.uuid4())
            position_data = {
                "account_id": trade["account_id"],
                "symbol_ticker": trade["ticker"],
                "quantity": new_position,
                "created_at": now_str,
                "updated_at": now_str,
            }
            await redis_client.hset(  # Set the new position
                redis_dictionaries[2], position_key, json.dumps(position_data)
            )
            account_data["positions"].append(position_key)
            account_data["updated_at"] = now_str
            await redis_client.hset(
                redis_dictionaries[1], trade["account_id"], json.dumps(account_data)
            )
            logger.info("Created new position for account")
        else:  # Editing existing position
            # Grab the existing positions data
            raw_specific_position = await redis_client.hget(
                redis_dictionaries[2], position_key
            )
            specific_position = json.loads(raw_specific_position)

            # Edit the existing position data
            specific_position["quantity"] = new_position
            specific_position["updated_at"] = now_str
            await redis_client.hset(
                redis_dictionaries[2], position_key, json.dumps(specific_position)
            )
            logger.info("Updated existing position for account")

    # position_update_duration = (
    #     time.perf_counter()
    #     - position_calculation_duration
    #     - redis_position_get_duration
    #     - lock_init_duration
    #     - trade_validation_duration
    #     - redis_account_get_duration
    #     - redis_user_get_duration
    #     - start
    # )

    # High Efficiency: Save to a single field named "d"
    await redis_client.xadd(TRADE_STREAM, {"d": packed_bytes})
    duration_ms = (time.perf_counter() - start) * 1000
    # Xadd_to_stream_duration = (
    #     time.perf_counter()
    #     - position_update_duration
    #     - position_calculation_duration
    #     - redis_position_get_duration
    #     - lock_init_duration
    #     - trade_validation_duration
    #     - redis_account_get_duration
    #     - redis_user_get_duration
    #     - start
    # )
    # logger.warning(
    #     f"Trade validation took {trade_validation_duration * 1000:2f}ms, "
    #     f"Redis user get took {redis_user_get_duration * 1000:2f}ms, "
    #     f"Redis account get took {redis_account_get_duration * 1000:2f}ms, "
    #     f"Lock init took {lock_init_duration * 1000:2f}ms, "
    #     f"Redis position get took {redis_position_get_duration * 1000:2f}ms, "
    #     f"Position calculation took {position_calculation_duration * 1000:2f}ms, "
    #     f"Position update took {position_update_duration * 1000:2f}ms, "
    #     f"Xadd to stream took {Xadd_to_stream_duration * 1000:2f}ms, "
    #     f"Succesfully booked a trade. Completed in {duration_ms:2f}ms"
    # )
    logger.info(f"Succesfully booked a trade. Completed in {duration_ms:2f}ms")

    return {"status": "success", "trade_id": f"{trade_id}"}


async def verify_account_access(account_id: str, user_id: str):
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts_associated"]:
        logger.warning("Invalid accound_id for user")
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )
