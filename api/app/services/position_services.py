from fastapi import HTTPException
import uuid
import json
from datetime import datetime, timezone
from app.core.redis import redis_client, USERS_KEY, ACCOUNTS_KEY, POSITIONS_KEY, MARKET_PRICES_KEY
from app.core.logging import logger
from app.core.config import TRADE_STREAM
from app.services.trade_services import create_payload


async def get_all_users_positions(user_id: str):
    # Get User data to check their accounts
    raw_user = await redis_client.hget(USERS_KEY, user_id)
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    # Gather all of the user's accounts
    pipe = redis_client.pipeline()

    users_accounts = set(user_data["accounts_associated"])

    for account in users_accounts:
        pipe.hget(ACCOUNTS_KEY, account)

    accounts = await pipe.execute()

    # Gathering all positions for each account
    pipe = redis_client.pipeline()

    position_uuid_to_account_name = {}
    position_uuid_keys = []

    for raw_account_data in accounts:
        if raw_account_data is None:
            continue
        account_data = json.loads(raw_account_data)
        for position_uuid in account_data["positions"]:
            position_uuid_to_account_name[position_uuid] = account_data["account_name"]
            position_uuid_keys.append(position_uuid)
            pipe.hget(POSITIONS_KEY, position_uuid)

    results = await pipe.execute()

    pipe = redis_client.pipeline()

    position_uuid_to_position_data = {}
    all_symbols_for_positions = []
    seen_symbols = set()

    for position_uuid, raw_position_data in zip(position_uuid_keys, results):
        if raw_position_data is None:
            continue
        real_position_data = json.loads(raw_position_data)
        position_uuid_to_position_data[position_uuid] = real_position_data
        ticker = real_position_data["symbol_ticker"]

        if ticker not in seen_symbols:
            all_symbols_for_positions.append(ticker)
            seen_symbols.add(ticker)
            pipe.hget(MARKET_PRICES_KEY, ticker)

    # Gathering market data for each ticker
    results = await pipe.execute()

    symbol_market_data = {}

    for ticker, value in zip(all_symbols_for_positions, results):
        if value is None:
            continue
        symbol_market_data[ticker] = json.loads(value)

    # Actually loading the position data
    positions = {}

    for position_uuid in position_uuid_keys:
        if position_uuid not in position_uuid_to_position_data:
            continue
        position = position_uuid_to_position_data[position_uuid]
        market = symbol_market_data.get(position["symbol_ticker"])
        if market is None:
            continue
        positions.setdefault(position["account_id"], []).append(
            {
                "account_name": position_uuid_to_account_name[position_uuid],
                "symbol_ticker": position["symbol_ticker"],
                "quantity": position["quantity"],
                "latest_price": market["latest_price"],
                "open_price": market["open_price"],
                "position_value": position["quantity"] * market["latest_price"],
                "average_cost": position["average_cost"],
                "realized_pnl": position["total_realized_gains"],
                "unrealized_pnl": (market["latest_price"] - position["average_cost"])
                * position["quantity"],
                "created_at": position["created_at"],
                "updated_at": position["updated_at"],
            }
        )

    return positions


async def get_all_accounts_positions(account_id: str, user_id: str):
    # Get User data
    raw_user = await redis_client.hget(USERS_KEY, user_id)
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    # Confirm it's your account
    if account_id not in user_data["accounts_associated"]:
        logger.warning("Attempt to access account that the user does not own")
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    raw_account = await redis_client.hget(ACCOUNTS_KEY, account_id)
    account_data = json.loads(raw_account)

    positions = {}

    pipe = redis_client.pipeline()

    for position_uuid in account_data["positions"]:
        pipe.hget(POSITIONS_KEY, position_uuid)

    results = await pipe.execute()

    pipe = redis_client.pipeline()

    real_positions = []
    all_symbols_for_positions = []
    seen_symbols = set()

    for position in results:
        real_position = json.loads(position)
        real_positions.append(real_position)
        ticker = real_position["symbol_ticker"]

        if ticker not in seen_symbols:
            all_symbols_for_positions.append(ticker)
            seen_symbols.add(ticker)
            pipe.hget(MARKET_PRICES_KEY, ticker)

    results = await pipe.execute()

    symbol_market_data = {}

    for ticker, value in zip(all_symbols_for_positions, results):
        if value is None:
            continue
        symbol_market_data[ticker] = json.loads(value)

    for x_positions in real_positions:
        market = symbol_market_data.get(x_positions["symbol_ticker"])
        if not market:
            continue
        positions[x_positions["symbol_ticker"]] = {
            "quantity": x_positions["quantity"],
            "latest_price": market["latest_price"],
            "open_price": market["open_price"],
            "position_value": x_positions["quantity"] * market["latest_price"],
            "average_cost": x_positions["average_cost"],
            "realized_pnl": x_positions["total_realized_gains"],
            "unrealized_pnl": (market["latest_price"] - x_positions["average_cost"])
            * x_positions["quantity"],
            "created_at": x_positions["created_at"],
            "updated_at": x_positions["updated_at"],
        }
    return positions


async def get_all_users_ticker_positions(ticker: str, user_id: str):
    # Get User and ticker data in one round trip
    pipe = redis_client.pipeline()
    pipe.hget(USERS_KEY, user_id)
    pipe.hget(MARKET_PRICES_KEY, ticker)
    raw_user, raw_symbol_data = await pipe.execute()

    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    if raw_symbol_data is None:
        raise HTTPException(status_code=422, detail="Ticker does not exist")
    real_symbol_data = json.loads(raw_symbol_data)

    pipe = redis_client.pipeline()

    users_accounts = set(user_data["accounts_associated"])

    for account in users_accounts:
        pipe.hget(ACCOUNTS_KEY, account)

    accounts = await pipe.execute()
    pipe = redis_client.pipeline()

    position_uuid_set = {}
    position_uuid_keys = []

    for raw_account_data in accounts:
        account_data = json.loads(raw_account_data)
        for position_uuid in account_data["positions"]:
            position_uuid_set[position_uuid] = account_data["account_name"]
            position_uuid_keys.append(position_uuid)
            pipe.hget(POSITIONS_KEY, position_uuid)

    results = await pipe.execute()

    positions = {}

    for position_uuid, raw_position in zip(position_uuid_keys, results):
        if raw_position is None:
            continue
        real_position_data = json.loads(raw_position)
        if (
            real_position_data["symbol_ticker"] == ticker
        ):  # You own this account and it's the right ticker
            positions[real_position_data["account_id"]] = [
                {
                    "account_name": position_uuid_set[position_uuid],
                    "symbol_ticker": real_position_data["symbol_ticker"],
                    "quantity": real_position_data["quantity"],
                    "latest_price": real_symbol_data["latest_price"],
                    "open_price": real_symbol_data["open_price"],
                    "position_value": real_position_data["quantity"]
                    * real_symbol_data["latest_price"],
                    "average_cost": real_position_data["average_cost"],
                    "realized_pnl": real_position_data["total_realized_gains"],
                    "unrealized_pnl": (
                        real_symbol_data["latest_price"]
                        - real_position_data["average_cost"]
                    )
                    * real_position_data["quantity"],
                    "created_at": real_position_data["created_at"],
                    "updated_at": real_position_data["updated_at"],
                }
            ]
    return positions


async def get_account_ticker_position(ticker: str, account_id: str, user_id: str):
    # Grab User, ticker, and account data in one round trip
    pipe = redis_client.pipeline()
    pipe.hget(USERS_KEY, user_id)
    pipe.hget(MARKET_PRICES_KEY, ticker)
    pipe.hget(ACCOUNTS_KEY, account_id)
    raw_user, raw_symbol_data, raw_account = await pipe.execute()

    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    # Confirm you have access to this account
    if account_id not in user_data["accounts_associated"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    if raw_symbol_data is None:
        raise HTTPException(status_code=422, detail="Ticker does not exist")
    real_symbol_data = json.loads(raw_symbol_data)

    account_data = json.loads(raw_account)

    positions = {}

    pipe = redis_client.pipeline()

    for position_uuid in account_data["positions"]:
        pipe.hget(POSITIONS_KEY, position_uuid)

    results = await pipe.execute()

    for x in results:
        x_positions = json.loads(x)
        if x_positions["symbol_ticker"] == ticker:  # Correct account and ticker
            positions[x_positions["symbol_ticker"]] = {
                "quantity": x_positions["quantity"],
                "latest_price": real_symbol_data["latest_price"],
                "open_price": real_symbol_data["open_price"],
                "position_value": x_positions["quantity"]
                * real_symbol_data["latest_price"],
                "average_cost": x_positions["average_cost"],
                "realized_pnl": x_positions["total_realized_gains"],
                "unrealized_pnl": (
                    real_symbol_data["latest_price"] - x_positions["average_cost"]
                )
                * x_positions["quantity"],
            }
            break  # only one account and one ticker
    return positions


async def edit_position(
    user_id: str,
    existing_trade: dict,
    new_trade: dict,
    other_account: str | None,
    trade_id: str,
):

    # Revert the position change from the existing trade
    old_quantity_delta = (
        -existing_trade["quantity"]
        if existing_trade["direction"] == "Buy"
        else existing_trade["quantity"]
    )

    # Apply the position change from the updated trade
    new_quantity_delta = (
        new_trade["quantity"]
        if new_trade["direction"] == "Buy"
        else -new_trade["quantity"]
    )

    lock_names = sorted(
        {
            f"account:{existing_trade['account_id']}",
            f"account:{new_trade['account_id']}",
            f"position:{existing_trade['account_id']}:{existing_trade['symbol_ticker']}",
            f"position:{new_trade['account_id']}:{new_trade['ticker']}",
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

        writes = []

        # Nothing else can modify either position now

        writes.extend(
            await update_position_data(
                str(existing_trade["account_id"]),
                existing_trade["symbol_ticker"],
                old_quantity_delta,
            )
        )

        writes.extend(
            await update_position_data(
                new_trade["account_id"],
                new_trade["ticker"],
                new_quantity_delta,
            )
        )
        pipe = redis_client.pipeline(transaction=True)

        for write in writes:
            pipe.hset(write["dictionary"], write["key"], write["value"])

        packed_bytes = create_payload(
            new_trade,
            trade_id,
            datetime.now(timezone.utc),
            existing_trade["created_at"],
            other_account,
            user_id,
        )

        pipe.xadd(TRADE_STREAM, {"d": packed_bytes})

        await pipe.execute()

    finally:
        # Always release, even if something throws
        for lock in reversed(acquired_locks):
            try:
                await lock.release()
            except Exception:
                logger.error("Failed to release Redis lock")


async def update_position_data(
    account_id: str,
    ticker: str,
    quantity_delta: int,
):

    raw_account = await redis_client.hget(ACCOUNTS_KEY, account_id)
    account_data = json.loads(raw_account)

    pipe = redis_client.pipeline()

    for position_uuid in account_data["positions"]:
        pipe.hget(POSITIONS_KEY, position_uuid)

    results = await pipe.execute()

    now = datetime.now(timezone.utc).isoformat()

    for position_uuid, raw_position in zip(account_data["positions"], results):
        x_positions = json.loads(raw_position)
        if x_positions["symbol_ticker"] == ticker:  # Correct account and ticker
            x_positions["quantity"] += quantity_delta
            if x_positions["quantity"] < 0 and not account_data["can_short"]:
                logger.warning("Invalid short attempt")
                raise HTTPException(
                    status_code=403,
                    detail=f"Account number {account_id} does not have permission to short",
                )
            x_positions["updated_at"] = now
            return [
                {
                    "dictionary": POSITIONS_KEY,
                    "key": position_uuid,
                    "value": json.dumps(x_positions),
                }
            ]

    if quantity_delta < 0 and not account_data["can_short"]:
        logger.warning("Invalid short attempt")
        raise HTTPException(
            status_code=403,
            detail=f"Account number {account_id} does not have permission to short",
        )
    new_position = quantity_delta
    position_key = str(uuid.uuid4())
    position_data = {
        "account_id": account_id,
        "symbol_ticker": ticker,
        "quantity": new_position,
        "created_at": now,
        "updated_at": now,
    }
    account_data["positions"].append(position_key)
    account_data["updated_at"] = now

    return [
        {
            "dictionary": POSITIONS_KEY,
            "key": position_key,
            "value": json.dumps(position_data),
        },
        {
            "dictionary": ACCOUNTS_KEY,
            "key": account_id,
            "value": json.dumps(account_data),
        },
    ]
