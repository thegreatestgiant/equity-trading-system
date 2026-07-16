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
    # time_user_lookup_start = time.perf_counter()
    user_data = await get_user_data(user_id)  # Fetch user data from Redis
    # time_user_lookup_end = time.perf_counter()
    # time_account_lookup_verification_plus_json_load_start = time.perf_counter()
    # Ensure it's a valid account
    account_data = await get_account_data(
        trade["account_id"]
    )  # Fetch account data from Redis
    # time_account_lookup_verifcation_plus_json_load_end = time.perf_counter()

    # time_trade_details_verification_start = time.perf_counter()
    await verify_trade_details(trade, user_data)
    # time_trade_details_verification_end = time.perf_counter()

    # time_other_account_verification_start = time.perf_counter()

    other_account = trade.get("other_account")

    other_account = verify_other_account(other_account)
    # time_other_account_verification_end = time.perf_counter()
    # time_create_payload_start = time.perf_counter()

    trade_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    packed_bytes = create_payload(trade, trade_id, now, None, other_account, user_id)
    # time_create_payload_end = time.perf_counter()
    # time_lock_acquisition_start = time.perf_counter()

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
        # time_lock_acquisition_end = time.perf_counter()

        new_position = None
        pipe = redis_client.pipeline()

        for position_uuid in account_data["positions"]:
            pipe.hget(redis_dictionaries[2], position_uuid)
        # time_position_redis_start = time.perf_counter()
        results = await pipe.execute()
        # time_position_redis_end = time.perf_counter()
        # time_position_json_load_plus_verification_start = time.perf_counter()

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
                        status_code=403,
                        detail=f"Account number {trade['account_id']} does not have permission to short",
                    )
                new_position = (
                    real_position_data["quantity"] + trade["quantity"]
                    if trade["direction"] == "Buy"
                    else real_position_data["quantity"] - trade["quantity"]
                )  # Save what the new position will be

                break  # only one account and one ticker
        # time_position_json_load_plus_verification_end = time.perf_counter()
        # time_position_update_start = time.perf_counter()
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
            position_key = str(uuid.uuid4())
            position_data = {
                "account_id": trade["account_id"],
                "symbol_ticker": trade["ticker"],
                "quantity": new_position,
                "created_at": now_str,
                "updated_at": now_str,
            }
            account_data["positions"].append(position_key)
            account_data["updated_at"] = now_str

            pipe = redis_client.pipeline(transaction=True)
            pipe.hset(  # Set the new position
                redis_dictionaries[2], position_key, json.dumps(position_data)
            )
            pipe.hset(
                redis_dictionaries[1], trade["account_id"], json.dumps(account_data)
            )
            # High Efficiency: Save to a single field named "d"
            pipe.xadd(TRADE_STREAM, {"d": packed_bytes})
            # time_pipe_execute_start = time.perf_counter()
            await pipe.execute()
            # time_pipe_execute_end = time.perf_counter()
            # time_position_update_end = time.perf_counter()
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

            pipe = redis_client.pipeline(transaction=True)
            pipe.hset(
                redis_dictionaries[2], position_key, json.dumps(specific_position)
            )
            # High Efficiency: Save to a single field named "d"
            pipe.xadd(TRADE_STREAM, {"d": packed_bytes})
            # time_pipe_execute_start = time.perf_counter()
            await pipe.execute()
            # time_pipe_execute_end = time.perf_counter()
            # time_position_update_end = time.perf_counter()
            logger.info("Updated existing position for account")

    finally:
        # Always release, even if something throws
        # time_release_locks_start = time.perf_counter()
        for lock in reversed(acquired_locks):
            try:
                await lock.release()
            except Exception:
                logger.error("Failed to release Redis lock")
        # time_release_locks_end = time.perf_counter()

    duration_ms = (time.perf_counter() - start) * 1000

    # logger.warning(
    #     f"time user lookup start: {time_user_lookup_start}, time user lookup end: {time_user_lookup_end}\n"
    #     f"time account lookup and verification plus json load start: {time_account_lookup_verification_plus_json_load_start}, time account lookup and verification plus json load end: {time_account_lookup_verifcation_plus_json_load_end}\n"
    #     f"time trade details verification start: {time_trade_details_verification_start}, time trade details verification end: {time_trade_details_verification_end}\n"
    #     f"time other account verification start: {time_other_account_verification_start}, time other account verification end: {time_other_account_verification_end}\n"
    #     f"time create payload start: {time_create_payload_start}, time create payload end: {time_create_payload_end}\n"
    #     f"time lock acquisition start: {time_lock_acquisition_start}, time lock acquisition end: {time_lock_acquisition_end}\n"
    #     f"time position redis start: {time_position_redis_start}, time position redis end: {time_position_redis_end}\n"
    #     f"time position json load plus verification start: {time_position_json_load_plus_verification_start}, time position json load plus verification end: {time_position_json_load_plus_verification_end}\n"
    #     f"time position update start: {time_position_update_start}, time position update end: {time_position_update_end}\n"
    #     f"time pipe execute start: {time_pipe_execute_start}, time pipe execute end: {time_pipe_execute_end}\n"
    #     f"time release locks start: {time_release_locks_start}, time release locks end: {time_release_locks_end}"
    # )

    logger.info(f"Succesfully booked a trade. Completed in {duration_ms:2f}ms")

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
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
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


def verify_other_account(other_account: str | None) -> str | None:
    if other_account:
        try:
            uuid.UUID(other_account, version=4)
        except ValueError:
            return None
    else:
        return None


async def get_user_data(user_id: str) -> dict:
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    return json.loads(raw_user)


async def get_account_data(account_id: str) -> dict:
    raw_account = await redis_client.hget(redis_dictionaries[1], account_id)
    if raw_account is None:
        raise HTTPException(
            status_code=404, detail=f"Account number {account_id} does not exist"
        )
    return json.loads(raw_account)
