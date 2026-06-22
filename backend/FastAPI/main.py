from fastapi import FastAPI, Response, HTTPException, Cookie, Depends, Request
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError
import jwt
import uuid
import json
import time
import msgpack
import asyncpg
import os
import csv
import sys
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from datetime import time as Time
from pydantic import BaseModel
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
import logbook
from pathlib import Path

valid_tickers = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global valid_tickers
    try:
        logger.info("Starting up API")
        app.state.pg_pool = await asyncpg.create_pool(
            host=postgres_docker_name,
            port=postgres_port_number,
            user=postgres_user,
            password=postgres_password,
            database=postgres_db,
        )
        logger.info("Synced with postgres")
    except Exception as e:
        logger.error(f"PostgreSQL startup failure: {e}")
        raise

    try:
        app.state.redis = AsyncRedis(host=redis_host, port=redis_port_number, db=0)
        await app.state.redis.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.error(f"Redis startup failure: {e}")
        raise

    with open("sp500.csv", newline="") as file:
        reader = csv.DictReader(file)
        valid_tickers = {row["ticker"].upper() for row in reader}
    logger.info("Loaded S&P Tickers")
    yield
    await app.state.pg_pool.close()
    await app.state.redis.close()
    logger.info("Closed connection to Postgress")
    logger.info("Closing down API")


postgres_port_number = int(os.getenv("POSTGRES_PORT", "5432"))
postgres_docker_name = os.getenv("POSTGRES_HOST", "localhost")
postgres_user = os.getenv("POSTGRES_USER", "postgres")
postgres_password = os.getenv("POSTGRES_PASSWORD", "password")
postgres_db = os.getenv("POSTGRES_DB", "trading")

app = FastAPI(lifespan=lifespan)  # TODO lifespan=lifespan

# Initalize Data
# region


Instrumentator().instrument(app).expose(app, endpoint="/metrics")

redis_port_number = int(os.getenv("REDIS_PORT", "6379"))
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_dictionaries = [
    "users",
    "accounts",
    "positions",
]  # redis dicts TODO update these tables once agrred upon naming convention


try:
    stream_handler = logbook.StreamHandler(
        sys.stdout,
        level="INFO",
        format_string="[{record.time:%Y-%m-%d %H:%M:%S}] {record.level_name}: {record.channel}: {record.message}",
    )

    stream_handler.push_application()

except Exception as e:
    print(f"LOGGING FAILED: {e}")
    raise

logger = logbook.Logger("FastAPI")

day_in_sec = 24 * 60 * 60  # Number of seconds in a day

secret_key = (
    "mysecretkey"  # Encryption Key for passwords TODO come up with something better
)
algorithm = "HS256"
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Initialize Redis client
redis_client = AsyncRedis(host=redis_host, port=redis_port_number, db=0)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start = time.perf_counter()

    try:
        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000

        message = (
            f"{request.method} {request.url.path} "
            f"-> {response.status_code} "
            f"in {duration_ms:.2f}ms"
        )

        if response.status_code >= 500:
            logger.error(message)
        elif response.status_code >= 400:
            logger.warning(message)
        else:
            logger.info(message)

        return response

    except HTTPException:
        raise

    except asyncpg.PostgresError as e:
        logger.error(f"PostgreSQL failure: {e}")

        raise HTTPException(status_code=503, detail="Database unavailable")

    except RedisError as e:
        logger.error(f"Redis failure: {e}")

        raise HTTPException(status_code=503, detail="Redis unavailable")

    except Exception as e:
        logger.error(f"Unhandled exception: {e}")

        raise HTTPException(status_code=500, detail="Internal server error")


def create_cookie(username: str):

    payload = {
        "username": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=day_in_sec),
    }
    session_token = jwt.encode(payload, secret_key, algorithm=algorithm)
    return session_token


# endregion

# Login details
# region


class RegisterRequest(BaseModel):  # Register class for json body
    username: str
    password: str


class LoginRequest(BaseModel):  # Login class for json body
    username: str
    password: str


@app.post("/register")
async def register_user(request: RegisterRequest, response: Response):
    logger.info("Recieved new user request")

    username = request.username
    password = request.password

    # Check if the username already exists in Redis
    all_user_ids = await redis_client.hgetall(redis_dictionaries[0])

    positions = {
        key.decode() if isinstance(key, bytes) else key: json.loads(value)
        for key, value in all_user_ids.items()
    }  # Turn all positions into valid dictionaries and not bytes

    for user in positions.values():
        if username == user["username"]:
            logger.warning("Pre-existing username was used")
            raise HTTPException(status_code=409, detail="Username already exists")

    # Create new User data
    user_id = str(uuid.uuid4())
    account_ids = []
    now = datetime.now(timezone.utc).isoformat()
    user_data = {
        "username": username,
        "oauth_key": pwd_context.hash(password),
        "accounts_associated": account_ids,
        "created_at": now,
        "updated_at": now,
    }

    # send new User to redis
    await redis_client.hset(redis_dictionaries[0], user_id, json.dumps(user_data))

    # Create token for authentication
    authentication_cookie = create_cookie(user_id)
    response.set_cookie(
        key="session",
        value=authentication_cookie,
        httponly=True,
        samesite="lax",
        max_age=day_in_sec,
    )

    return {
        "message": f"User registered successfully, your user_id is {user_id}. Save it somewhere safe."
    }


@app.post("/login")
async def login_user(request: LoginRequest, response: Response):
    logger.info("Recieved new login request")

    username = request.username
    password = request.password

    # Get the User data from redis
    all_user_ids = await redis_client.hgetall(redis_dictionaries[0])

    positions = {
        key.decode() if isinstance(key, bytes) else key: json.loads(value)
        for key, value in all_user_ids.items()
    }  # Turn all positions into valid dictionaries and not bytes

    valid = False
    id = None

    for user_id, user in positions.items():
        if username == user["username"] and pwd_context.verify(
            password, user["oauth_key"]
        ):
            valid = True
            id = user_id

    if not valid:  # No such user exists or wrong password
        logger.warning("Invalid login attempt")
        raise HTTPException(status_code=401, detail="Wrong Username or Password")

    # Create token for authentication
    authentication_cookie = create_cookie(id)
    response.set_cookie(
        key="session",
        value=authentication_cookie,
        httponly=True,
        samesite="lax",
        max_age=day_in_sec,
    )

    return {"message": "login succesful."}


@app.post("/logout")
async def logout(response: Response):
    logger.info("Recieved new logout request")
    response.delete_cookie(key="session", httponly=True, samesite="lax")

    return {"message": "logged out"}


# endregion


async def verify_cookie(session: str = Cookie(None)):
    if not session:
        logger.warning("No login cookie")
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(session, secret_key, algorithms=[algorithm])
        user_id = payload.get("username")
        if not user_id:
            logger.warning("Invalid cookie")
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.ExpiredSignatureError:
        logger.warning("Invalid cookie")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        logger.warning("Invalid cookie")
        raise HTTPException(status_code=401, detail="Invalid token")


# Account details
# region
@app.post("/users/account")
async def create_account(
    account_name: str, can_short: bool, user_id: str = Depends(verify_cookie)
):
    logger.info("Recieved new account request")

    # Create account
    account_id = str(uuid.uuid4())
    positions = []
    now = datetime.now(timezone.utc).isoformat()
    account_data = {
        "account_name": account_name,
        "positions": positions,
        "can_short": can_short,
        "created_at": now,
        "updated_at": now,
    }

    await redis_client.hset(redis_dictionaries[1], account_id, json.dumps(account_data))

    # Grab User to add Account to them
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    user_data["accounts_associated"].append(account_id)
    user_data["updated_at"] = now

    await redis_client.hset(redis_dictionaries[0], user_id, json.dumps(user_data))

    return {
        "message": f"Account created, here is you account_id {account_id}. Save it somewhere safe"
    }


@app.post("/users/accounts/{account_id}")
async def add_account(account_id: str, user_id: str = Depends(verify_cookie)):
    logger.info("Recieved new account sync to user request")

    # Get account to ensure it exists
    raw_account = await redis_client.hget(redis_dictionaries[1], account_id)
    if not raw_account:
        logger.warning("Invalid account given")
        raise HTTPException(status_code=404, detail="This account does not exist")

    # Grab User to add account to them
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    user_data["accounts_associated"].append(account_id)
    user_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await redis_client.hset(redis_dictionaries[0], user_id, json.dumps(user_data))

    return {"message": f"Account added to user {user_data['username']}"}


@app.get("/users/allaccounts")
async def get_all_accounts(user_id: str = Depends(verify_cookie)):
    logger.info("Recieved new get all user's accounts request")

    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    account_name = []
    for account in user_data["accounts_associated"]:
        account_raw = await redis_client.hget(redis_dictionaries[1], account)
        accont_real = json.loads(account_raw)
        account_name.append(accont_real["account_name"])

    account_details = dict(zip(account_name, user_data["accounts_associated"]))

    return {"accounts": account_details}


# endregion


# Positions
# region


@app.get("/positions")
async def get_users_positions(user_id: str = Depends(verify_cookie)):
    logger.info("Recieved request to get all of a user's positions")

    # Get User data to check their accounts
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    positions = {}

    # Grab all positions for checking
    raw_positions = await redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if (
            x_positions["account_id"] in user_data["accounts_associated"]
        ):  # This positions is your account
            if (
                x_positions["account_id"] not in positions
            ):  # First time adding a position for that account
                positions[x_positions["Account_id"]] = [
                    {
                        "symbol_ticker": x_positions["symbol_ticker"],
                        "quantity": x_positions["quantity"],
                        "created_at": x_positions["created_at"],
                        "updated_at": x_positions["updated_at"],
                    }
                ]
            else:  # This account already processed at least one position
                positions[x_positions["account_id"]].append(
                    {
                        "symbol_ticker": x_positions["ticker"],
                        "quantity": x_positions["quantity"],
                        "created_at": x_positions["created_at"],
                        "updated_at": x_positions["updated_at"],
                    }
                )

    return {"message": positions}


@app.get("/positions/accounts/{account_id}")
async def get_accounts_positions(
    account_id: str, user_id: str = Depends(verify_cookie)
):
    logger.info("Recieved request for all of an account's positions")

    # Get User data
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    # Confirm it's your account
    if account_id not in user_data["accounts_associated"]:
        logger.warning("Attempt to access account that the user does now own")
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    positions = {}

    # Grab all positions for checking
    raw_positions = await redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if x_positions["account_id"] == account_id:  # If this position is your account
            positions[x_positions["symbol_ticker"]] = {
                "quantity": x_positions["quantity"],
                "created_at": x_positions["created_at"],
                "updated_at": x_positions["updated_at"],
            }

    return {"message": positions}


@app.get("/positions/ticker/{ticker}")
async def get_users_positions_for_ticker(
    ticker: str, user_id: str = Depends(verify_cookie)
):
    logger.info("Recieved request for user's positions for a ticker")

    # Get User data
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    positions = {}

    # Grab all positions for checking
    raw_positions = await redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if (
            x_positions["account_id"] in user_data["accounts_associated"]
            and x_positions["symbol_ticker"] == ticker
        ):  # You own this account and it's the right ticker
            positions[x_positions["Account_id"]] = [
                {
                    "symbol_ticker": x_positions["symbol_ticker"],
                    "quantity": x_positions["quantity"],
                    "created_at": x_positions["created_at"],
                    "updated_at": x_positions["updated_at"],
                }
            ]

    return {"message": positions}


@app.get("/positions/accounts/{account_id}/ticker/{ticker}")
async def get_accounts_positions_for_ticker(
    ticker: str, account_id: str, user_id: str = Depends(verify_cookie)
):
    logger.info("Recieved request for an account's position by ticker")

    # Grab User data
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    # Confirm you have access to this account
    if account_id not in user_data["accounts_associated"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    positions = {}

    # Grab all positions for checking
    raw_positions = await redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if (
            x_positions["account_id"] == account_id
            and x_positions["symbol_ticker"] == ticker
        ):  # Correct account and ticker
            positions[x_positions["symbol_ticker"]] = x_positions["quantity"]
            break  # only one account and one ticker

    return {"message": positions}


# endregion


# Trades
# region


# Create Trade class so can verify the data in json not query and to ensure all fields are filled out
class Trade(BaseModel):
    account_id: str
    user_id: str
    direction: str
    ticker: str
    quantity: int
    price: str
    other_account: str | None = None


@app.post("/trade")
async def create_trade(trade: list[Trade], user_id: str = Depends(verify_cookie)):
    logger.info("Recieved request to book trade data")

    if len(trade) == 0:  # Didn't send any trade data
        logger.warning("There was no trade data")
        raise HTTPException(status_code=422, detail="Invalid Trade Data")

    for trade_item in trade:  # Loop through each trade one at a time
        await individual_trade(
            user_id, trade_item.model_dump()
        )  # Converts from class to dictionary for sorting

    return {"status": "success"}


async def individual_trade(user_id: str, trade: dict):
    logger.info("Booking a trade")
    start = time.perf_counter()

    # Ensure it's a valid user
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    if not raw_user:
        logger.warning("Invalid user_id for booking")
        raise HTTPException(status_code=404, detail="This user does not exist")
    user_data = json.loads(raw_user)

    # Ensure it's a valid account
    raw_account = await redis_client.hget(redis_dictionaries[1], trade["account_id"])
    if not raw_account:
        logger.warning("Invalid account_id for booking")
        raise HTTPException(status_code=404, detail="This account does not exist")
    account_data = json.loads(raw_account)

    # Ensure you are trading for you
    if trade["user_id"] != user_id:
        logger.warning("Invalid user_id for booking")
        raise HTTPException(
            status_code=401, detail="This user_id does not match your user_id"
        )

    # Confirm you have access to this account
    if trade["account_id"] not in user_data["accounts_associated"]:
        logger.warning("Invalid account_id for booking")
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    # Check ticker exists
    if trade["ticker"] not in valid_tickers:
        logger.warning("Invalid ticker for booking")
        raise HTTPException(status_code=422, detail="Ticker does not exist")

    # Ensure calid direction
    if trade["direction"] not in ("Buy", "Sell"):
        logger.warning("Invalid direction for booking")
        raise HTTPException(status_code=422, detail="Not a valid Direction")

    # Ensure valid quantity
    if trade["quantity"] < 0:
        logger.warning("Invalid quantity for booking")
        raise HTTPException(status_code=422, detail="Not a valid quantity value")

    # Grab all positions for editing
    raw_positions = await redis_client.hgetall(redis_dictionaries[3])
    position_key = None
    new_position = None

    positions = {
        key.decode() if isinstance(key, bytes) else key: json.loads(value)
        for key, value in raw_positions.items()
    }  # Turn all positions into valid dictionaries and not bytes

    for key, x in positions.items():
        if (
            x["account_id"] == trade["account_id"]
            and x["symbol_ticker"] == trade["ticker"]
        ):  # Correct account and ticker
            position_key = key  # Grab the key of the position to edit
            if (
                trade["direction"] == "Sell"
                and x["quantity"] - trade["quantity"] < 0
                and not account_data["can_short"]
            ):  # Check if trying to short
                logger.warning("Invalid short attempt")
                raise HTTPException(
                    status_code=403, detail="You do not have permission to short"
                )
            new_position = (
                x["quantity"] + trade["quantity"]
                if trade["direction"] == "Buy"
                else x["quantity"] - trade["quantity"]
            )  # Save what the new position will be

            break  # only one account and one ticker

    if new_position is None:  # This position does not currently exist
        if trade["direction"] != "Buy" and not account_data["can_short"]:
            logger.warning("Invalid short attempt")
            raise HTTPException(
                status_code=403, detail="You do not have permission to short"
            )

    trade_id = str(uuid.uuid4())
    payload = {
        "trade_id": trade_id,
        "account_id": trade["account_id"],
        "user_id": trade["user_id"],
        "direction": trade["direction"],  # Must be exact string: 'Buy' or 'Sell'
        "symbol_ticker": trade["ticker"],
        "created_at": int(
            time.time()
        ),  # Unix timestamps for lightning-fast serializing
        "updated_at": int(time.time()),
        "quantity": int(trade["quantity"]),
        "price": str(trade["price"]),  # Kept as string for Postgres NUMERIC ingestion
        "other_account": trade.get("other_account"),  # Can be None/Null
    }

    # Pack to raw binary
    packed_bytes = msgpack.packb(payload)

    now = datetime.now(timezone.utc).isoformat()

    if position_key is None:  # The position does not exist, create new one
        new_position = (
            trade["quantity"] if trade["direction"] == "Buy" else 0 - trade["quantity"]
        )
        position_key = str(uuid.uuid4())
        position_data = {
            "account_id": trade["account_id"],
            "symbol_ticker": trade["ticker"],
            "quantity": new_position,
            "created_at": now,
            "updated_at": now,
        }
        await redis_client.hset(  # Set the new position
            redis_dictionaries[3], position_key, json.dumps(position_data)
        )
        logger.info("Created new position for account")
    else:  # Editing existing position
        # Grab the existing positions data
        raw_specific_position = await redis_client.hget(
            redis_dictionaries[3], position_key
        )
        specific_position = json.loads(raw_specific_position)

        # Edit the existing position data
        specific_position["quantity"] = new_position
        specific_position["updated_at"] = now
        await redis_client.hset(
            redis_dictionaries[3], position_key, json.dumps(specific_position)
        )
        logger.info("Updated existing position for account")

    # High Efficiency: Save to a single field named "d"
    await redis_client.xadd("trade_stream", {"d": packed_bytes})
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(f"Succesfully booked a trade. Completed in {duration_ms:2f}ms")

    return {"status": f"success, here is your trade_id {trade_id}"}


# endregion


# Get trade data
# region


@app.get("/trades")
async def get_all_user_trades(request: Request, user_id: str = Depends(verify_cookie)):
    logger.info("Recieved request for trade data")

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
        ORDER BY created_at DESC
        """,
        user_id,
    )

    return [dict(row) for row in rows]


@app.get("/trades/account/{account_id}")
async def get_all_user_trades_for_account(
    account_id: str, request: Request, user_id: str = Depends(verify_cookie)
):
    logger.info("Recieved request for trade data")

    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND account_id = $2
        ORDER BY created_at DESC
        """,
        user_id,
        account_id,
    )

    return [dict(row) for row in rows]


@app.get("/trades/ticker/{ticker}")
async def get_all_user_trades_for_ticker(
    ticker: str, request: Request, user_id: str = Depends(verify_cookie)
):
    logger.info("Recieved request for trade data")

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND symbol_ticker = $2
        ORDER BY created_at DESC
        """,
        user_id,
        ticker,
    )

    return [dict(row) for row in rows]


@app.get("/trades/account/{account_id}/ticker/{ticker}")
async def get_all_user_trades_for_account_for_ticker(
    account_id: str,
    ticker: str,
    request: Request,
    user_id: str = Depends(verify_cookie),
):
    logger.info("Recieved request for trade data")

    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND account_id = $2
            AND symbol_ticker = $3
        ORDER BY created_at DESC
        """,
        user_id,
        account_id,
        ticker,
    )

    return [dict(row) for row in rows]


@app.get("/trades/{trade_id}")
async def get_specific_trade(
    trade_id: str, request: Request, user_id: str = Depends(verify_cookie)
):
    logger.info("Recieved request for trade data")

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND trade_id = $2
        ORDER BY created_at DESC
        """,
        user_id,
        trade_id,
    )

    return [dict(row) for row in rows]


@app.get("/trades/time/{time_start}/{time_end}")
async def get_all_user_trades_for_time(
    request: Request,
    time_start: Time,
    time_end: Time,
    user_id: str = Depends(verify_cookie),
):
    logger.info("Recieved request for trade data")

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND created_at BETWEEN $2 AND $3
        ORDER BY created_at DESC
        """,
        user_id,
        time_start,
        time_end,
    )

    return [dict(row) for row in rows]


@app.get("/trades/account/{account_id}/time/{time_start}/{time_end}")
async def get_all_user_trades_for_account_for_time(
    account_id: str,
    request: Request,
    time_start: Time,
    time_end: Time,
    user_id: str = Depends(verify_cookie),
):
    logger.info("Recieved request for trade data. Completed in {duration_ms:2f}ms")

    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND account_id = $2
            AND created_at BETWEEN $3 AND $4
        ORDER BY created_at DESC
        """,
        user_id,
        account_id,
        time_start,
        time_end,
    )

    return [dict(row) for row in rows]


@app.get("/trades/ticker/{ticker}/time/{time_start}/{time_end}")
async def get_all_user_trades_for_ticker_for_time(
    ticker: str,
    request: Request,
    time_start: Time,
    time_end: Time,
    user_id: str = Depends(verify_cookie),
):
    logger.info("Recieved request for trade data")

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND symbol_ticker = $2
            AND created_at BETWEEN $3 AND $4
        ORDER BY created_at DESC
        """,
        user_id,
        ticker,
        time_start,
        time_end,
    )

    return [dict(row) for row in rows]


@app.get("/trades/account/{account_id}/ticker/{ticker}/time/{time_start}/{time_end}")
async def get_all_user_trades_for_account_for_ticker_for_time(
    account_id: str,
    ticker: str,
    request: Request,
    time_start: Time,
    time_end: Time,
    user_id: str = Depends(verify_cookie),
):
    logger.info("Recieved request for trade data")

    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND account_id = $2
            AND symbol_ticker = $3
            AND created_at BETWEEN $4 AND $5
        ORDER BY created_at DESC
        """,
        user_id,
        account_id,
        ticker,
        time_start,
        time_end,
    )

    return [dict(row) for row in rows]


# endregion
