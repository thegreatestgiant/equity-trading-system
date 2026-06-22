from fastapi import FastAPI, Response, HTTPException, Cookie, Depends, Request
from redis.asyncio import Redis as AsyncRedis
import jwt
import uuid
import json
import time
import msgpack
import asyncpg
import os
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from datetime import time as Time
from pydantic import BaseModel
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pg_pool = await asyncpg.create_pool(
        host=postgres_docker_name,
        port=postgres_port_number,
        user=postgres_user,
        password=postgres_password,
        database=postgres_db,
    )
    yield
    await app.state.pg_pool.close()


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
    "Tickers",
    "positions",
]  # redis dicts TODO update these tables once agrred upon naming convention

day_in_sec = 24 * 60 * 60  # Number of seconds in a day

secret_key = (
    "mysecretkey"  # Encryption Key for passwords TODO come up with something better
)
algorithm = "HS256"
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def create_cookie(username: str):

    payload = {
        "username": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=day_in_sec),
    }
    session_token = jwt.encode(payload, secret_key, algorithm=algorithm)
    return session_token


# Initialize Redis client
redis_client = AsyncRedis(host=redis_host, port=redis_port_number, db=0)


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

    response.delete_cookie(key="session", httponly=True, samesite="lax")

    return {"message": "logged out"}


# endregion


async def verify_cookie(session: str = Cookie(None)):
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(session, secret_key, algorithms=[algorithm])
        user_id = payload.get("username")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# Account details
# region
@app.post("/users/account")
async def create_account(
    account_name: str, can_short: bool, user_id: str = Depends(verify_cookie)
):

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

    # Get account to ensure it exists
    raw_account = await redis_client.hget(redis_dictionaries[1], account_id)
    if not raw_account:
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

    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    return {"message": user_data["accounts_associated"]}


# endregion


# Positions
# region


@app.get("/positions")
async def get_users_positions(user_id: str = Depends(verify_cookie)):

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

    # Get User data
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    # Confirm it's your account
    if account_id not in user_data["accounts_associated"]:
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

    # Confirm it's a real ticker
    raw_ticker = await redis_client.hget(redis_dictionaries[2], ticker)
    if not raw_ticker:
        raise HTTPException(status_code=404, detail="This ticker does not exist")

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

    # Check ticker exists
    raw_ticker = await redis_client.hget(redis_dictionaries[2], ticker)
    if not raw_ticker:
        raise HTTPException(status_code=404, detail="This ticker does not exist")

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

    if len(trade) == 0:  # Didn't send any trade data
        raise HTTPException(status_code=422, detail="Invalid Trade Data")

    for trade_item in trade:  # Loop through each trade one at a time
        await individual_trade(
            user_id, trade_item.model_dump()
        )  # Converts from class to dictionary for sorting

    return {"status": "success"}


async def individual_trade(user_id: str, trade: dict):

    # Ensure it's a valid user
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    if not raw_user:
        raise HTTPException(status_code=404, detail="This user does not exist")
    user_data = json.loads(raw_user)

    # Ensure it's a valid account
    raw_account = await redis_client.hget(redis_dictionaries[1], trade["account_id"])
    if not raw_account:
        raise HTTPException(status_code=404, detail="This account does not exist")
    account_data = json.loads(raw_account)

    # Ensure you are trading for you
    if trade["user_id"] != user_id:
        raise HTTPException(
            status_code=401, detail="This user_id does not match your user_id"
        )

    # Confirm you have access to this account
    if trade["account_id"] not in user_data["accounts_associated"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    # Check ticker exists
    raw_ticker = await redis_client.hget(redis_dictionaries[2], trade["ticker"])
    if not raw_ticker:
        raise HTTPException(status_code=422, detail="This ticker does not exist")

    # Ensure calid direction
    if trade["direction"] not in ("Buy", "Sell"):
        raise HTTPException(status_code=422, detail="Not a valid Direction")

    # Ensure valid quantity
    if trade["quantity"] < 0:
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

    # High Efficiency: Save to a single field named "d"
    await redis_client.xadd("trade_stream", {"d": packed_bytes})

    return {"status": f"success, here is your trade_id {trade_id}"}


# endregion


# Get trade data
# region


@app.get("/trades")
async def get_all_user_trades(request: Request, user_id: str = Depends(verify_cookie)):

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

    raw_ticker = await redis_client.hget(redis_dictionaries[2], ticker)
    if not raw_ticker:
        raise HTTPException(status_code=404, detail="This ticker does not exist")

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

    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    raw_ticker = await redis_client.hget(redis_dictionaries[2], ticker)
    if not raw_ticker:
        raise HTTPException(status_code=404, detail="This ticker does not exist")

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

    raw_ticker = await redis_client.hget(redis_dictionaries[2], ticker)
    if not raw_ticker:
        raise HTTPException(status_code=404, detail="This ticker does not exist")

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

    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    raw_ticker = await redis_client.hget(redis_dictionaries[2], ticker)
    if not raw_ticker:
        raise HTTPException(status_code=404, detail="This ticker does not exist")

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
