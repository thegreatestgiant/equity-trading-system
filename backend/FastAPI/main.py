from fastapi import FastAPI, Response, HTTPException, Cookie, Depends
from redis.asyncio import Redis
import jwt
import uuid
import json
import time
import msgpack
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone

app = FastAPI()

redis_port_number = (
    6379  # Default Redis port TODO update this port once agreed upon port
)
redis_host = "localhost"  # Redis host address TODO update this address once agreed upon
redis_dictionaries = [
    "Users",
    "Accounts",
    "Tickers",
    "Positions",
]  # redis dicts TODO update these tables once agrred upon naming convention

day_in_sec = 24 * 60 * 60  # Number of seconds in a day

secret_key = (
    "mysecretkey"  # Encryption Key for passwords TODO come up with something better
)
algorithm = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_cookie(username: str):

    payload = {
        "name": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=day_in_sec),
    }
    authentication_cookie = jwt.encode(payload, secret_key, algorithm=algorithm)
    return authentication_cookie


# Initialize Redis client
redis_client = Redis(host=redis_host, port=redis_port_number, db=0)
async_redis_client = Redis(host=redis_host, port=redis_port_number, db=0)


# Login details
# region
@app.post("/register")
def register_user(username: str, password: str, response: Response):

    # Check if the username already exists in Redis
    if redis_client.hexists(redis_dictionaries[0], username):
        raise HTTPException(status_code=409, detail="Username already exists")

    # Create new User data
    user_id = str(uuid.uuid4())
    uuid_account_array = []
    now = datetime.now(timezone.utc).isoformat()
    user_data = {
        "user_id": user_id,
        "password_hash": pwd_context.hash(password),
        "accounts": uuid_account_array,
        "created_at": now,
        "updated_at": now,
    }

    # send new User to redis
    redis_client.hset(redis_dictionaries[0], username, json.dumps(user_data))

    # Create token for authentication
    authentication_cookie = create_cookie(username)
    response.set_cookie(
        key="session",
        value=authentication_cookie,
        httponly=True,
        samesite="lax",
        max_age=day_in_sec,
    )

    return {"message": "User registered successfully."}


@app.get("/login")
def login_user(username: str, password: str, response: Response):

    # Get the User data from redis
    raw_user = redis_client.hget(redis_dictionaries[0], username)
    if not raw_user:  # No such user exists
        raise HTTPException(status_code=401, detail="Wrong Username or Password")

    user_data = json.loads(raw_user)
    if not pwd_context.verify(password, user_data["password_hash"]):  # Wrong password
        raise HTTPException(status_code=401, detail="Wrong Username or Password")

    # Create token for authentication
    authentication_cookie = create_cookie(username)
    response.set_cookie(
        key="session",
        value=authentication_cookie,
        httponly=True,
        samesite="lax",
        max_age=day_in_sec,
    )

    return {"message": "login succesful."}


@app.post("/logout")
def logout(response: Response):

    response.delete_cookie(key="session", httponly=True, samesite="lax")

    return {"message": "logged out"}


# endregion


def verify_cookie(session: str = Cookie(None)):
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(session, secret_key, algorithms=[algorithm])
        user_id = payload.get("name")
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
def create_account(can_short: bool, username: str = Depends(verify_cookie)):

    # Create account
    account_UUID = str(uuid.uuid4())
    positions = []
    now = datetime.now(timezone.utc).isoformat()
    account_data = {
        "Positions": positions,
        "can_short": can_short,
        "Created_at": now,
        "Updated_at": now,
    }

    redis_client.hset(redis_dictionaries[1], account_UUID, json.dumps(account_data))

    # Grab User to add Account to them
    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    user_data["accounts"].append(account_UUID)
    user_data["updated_at"] = now

    redis_client.hset(redis_dictionaries[0], username, json.dumps(user_data))

    return {"message": "Account created"}


@app.post("/users/accounts/{account_id}")
def add_account(account_id: str, username: str = Depends(verify_cookie)):

    raw_account = redis_client.hget(redis_dictionaries[1], account_id)
    if not raw_account:
        raise HTTPException(status_code=404, detail="This account does not exist")

    # Grab User to add account to them
    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    user_data["accounts"].append(account_id)
    user_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    redis_client.hset(redis_dictionaries[0], username, json.dumps(user_data))

    return {"message": f"Account added to user {username}"}


# endregion


# Positions
# region
@app.get("/positions")
def get_users_positions(username: str = Depends(verify_cookie)):

    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    positions = {}

    raw_positions = redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if (
            x_positions["Account_id"] in user_data["accounts"]
        ):  # This positions is your account
            if (
                x_positions["Account_id"] not in positions
            ):  # First time adding a position for that account
                positions[x_positions["Account_id"]] = [
                    {
                        "Ticker": x_positions["Ticker"],
                        "Quantity": x_positions["Quantity"],
                        "Created_at": x_positions["Created_at"],
                        "Update_at": x_positions["Updated_at"],
                    }
                ]
            else:  # This account already processed at least one position
                positions[x_positions["Account_id"]].append(
                    {
                        "Ticker": x_positions["Ticker"],
                        "Quantity": x_positions["Quantity"],
                        "Created_at": x_positions["Created_at"],
                        "Update_at": x_positions["Updated_at"],
                    }
                )

    return {"message": positions}


@app.get("/positions/accounts/{account_id}")
def get_accounts_positions(account_id: str, username: str = Depends(verify_cookie)):

    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    # Confirm it's your account
    if account_id not in user_data["accounts"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    positions = {}

    raw_positions = redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if x_positions["Account_id"] == account_id:  # If this position is your account
            positions[x_positions["Ticker"]] = {
                "Quantity": x_positions["Quantity"],
                "Created_at": x_positions["Created_at"],
                "Update_at": x_positions["Updated_at"],
            }

    return {"message": positions}


@app.get("/positions/ticker/{ticker}")
def get_users_positions_for_ticker(ticker: str, username: str = Depends(verify_cookie)):

    # Confirm it's a real ticker
    raw_ticker = redis_client.hget(redis_dictionaries[2], ticker)
    if not raw_ticker:
        raise HTTPException(status_code=404, detail="This ticker does not exist")

    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    positions = {}

    raw_positions = redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if (
            x_positions["Account_id"] in user_data["accounts"]
            and x_positions["Ticker"] == ticker
        ):  # You own this account and it's the right ticker
            positions[x_positions["Account_id"]] = [
                {
                    "Ticker": x_positions["Ticker"],
                    "Quantity": x_positions["Quantity"],
                    "Created_at": x_positions["Created_at"],
                    "Update_at": x_positions["Updated_at"],
                }
            ]

    return {"message": positions}


@app.get("/positions/accounts/{account_id}/ticker/{ticker}")
def get_accounts_positions_for_ticker(
    ticker: str, account_id: str, username: str = Depends(verify_cookie)
):

    # Check ticker exists
    raw_ticker = redis_client.hget(redis_dictionaries[2], ticker)
    if not raw_ticker:
        raise HTTPException(status_code=404, detail="This ticker does not exist")

    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    # Confirm you have access to this account
    if account_id not in user_data["accounts"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    positions = {}

    raw_positions = redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if (
            x_positions["Account_id"] == account_id and x_positions["Ticker"] == ticker
        ):  # Correct account and ticker
            positions[x_positions["Ticker"]] = x_positions["Quantity"]
            break  # only one account and one ticker

    return {"message": positions}


# endregion

#Trades
#region
@app.post("/trade")
async def create_trade(trade: dict, username: str = Depends(verify_cookie)):

    # Check ticker exists
    raw_ticker = await async_redis_client.hget(redis_dictionaries[2], trade["ticker"])
    if not raw_ticker:
        raise HTTPException(status_code=404, detail="This ticker does not exist")

    raw_user = await async_redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    # Confirm you have access to this account
    if trade["account_id"] not in user_data["accounts"]:
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )
    elif trade["user_id"] != username:
        raise HTTPException(status_code=404, detail="This user does not match your username")
    elif trade["direction"] not in ("Buy", "Sell"):
        raise HTTPException(status_code=422, detail="Not a valid Direction")
    
    
    raw_account = await async_redis_client.hget(redis_dictionaries[1], trade["account_id"])
    account_data = json.loads(raw_account)

    raw_positions = await async_redis_client.hgetall(redis_dictionaries[3])
    position_key = None
    new_position = None

    for key, x in raw_positions.items():
        x_positions = json.loads(x)
        if (
            x_positions["Account_id"] == trade["account_id"] and x_positions["Ticker"] == trade["ticker"]
        ):  # Correct account and ticker
            position_key = key.decode() if isinstance(key, bytes) else key
            if x_positions["Quantity"]-trade["quantity"] < 0 and not account_data["can_short"]:
                raise HTTPException(status_code=403, detail="You do not have permission to short")
            new_position = x_positions["Quantity"]+trade["quantity"] if trade["direction"] == "Buy" else x_positions["Quantity"]-trade["quantity"]
            
            break  # only one account and one ticker

    payload = {
        "trade_id": str(uuid.uuid4()),
        "account_id": trade["account_id"],
        "user_id": trade["user_id"],
        "direction": trade["direction"],  # Must be exact string: 'Buy' or 'Sell'
        "ticker": trade["ticker"],
        "created_at": int(time.time()),   # Unix timestamps for lightning-fast serializing
        "updated_at": int(time.time()),
        "quantity": int(trade["quantity"]),
        "price": str(trade["price"]),     # Kept as string for Postgres NUMERIC ingestion
        "other_account": trade.get("other_account") # Can be None/Null
    }
    
    # Pack to raw binary
    packed_bytes = msgpack.packb(payload)
    
    # High Efficiency: Save to a single field named "d"
    await async_redis_client.xadd("trade_stream", {"d": packed_bytes})
    
    now = datetime.now(timezone.utc).isoformat()

    if position_key is None:
        position_key = len(raw_positions.keys())
        position_data = {
            "Account_id": trade["account_id"],
            "Ticker": trade["ticker"],
            "Quantity": new_position,
            "Created_at": now,
            "Updated_at": now
        }
        await async_redis_client.hset(redis_dictionaries[3], position_key, json.dumps(position_data))
    else:
        raw_specific_position = await async_redis_client.hget(redis_dictionaries[3], position_key)
        specific_position = json.loads(raw_specific_position)

        specific_position["Quantity"] = new_position
        specific_position["Updated_at"] = now
        await async_redis_client.hset(redis_dictionaries[3], position_key, json.dumps(specific_position))
    

    return {"status": "success"}

#endregion
