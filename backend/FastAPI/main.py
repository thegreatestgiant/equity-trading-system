from fastapi import FastAPI, Response, HTTPException, Cookie, Depends
from redis import Redis
import jwt
import uuid
import json
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

    account_UUID = str(uuid.uuid4())
    positions = []
    now = datetime.now(timezone.utc).isoformat()
    account_data = {
        "Positions": positions,
        "can_short": can_short,
        "Created_at": now,
        "Updated_at": now,
    }

    redis_client.hset(redis_dictionaries[1], account_UUID, account_data)

    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    user_data["accounts"].append(account_UUID)
    user_data["Update_at"] = now

    redis_client.hset(redis_dictionaries[0], username, json.dumps(user_data))

    return {"message": "Account created"}

@app.post("/users/accounts/{account_id}")
def add_account(account_id: uuid, username: str = Depends(verify_cookie)):

    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    user_data["accounts"].append(account_id)
    user_data["Update_at"] = datetime.now(timezone.utc).isoformat()

    redis_client.hset(redis_dictionaries[0], username, json.dumps(user_data))

    return {"message": "Account added to user {username}"}
# endregion

#Positions
#region
@app.get("/positions")
def get_users_positions(username: str = Depends(verify_cookie)):

    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    positions = {}

    raw_positions = redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if x_positions["Account_id"] in user_data["accounts"]:
            if x_positions["Account_id"] not in positions:
                positions[x_positions["Account_id"]] = [x_positions[1:]]
            else:
                positions[x_positions["Account_id"]].append(x_positions[1:])
    
    return {"message": "{positions}"}


@app.get("/positions/{account_id}")
def get_accounts_positions(account_id = uuid, username: str = Depends(verify_cookie)):

    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts"]:
         raise HTTPException(status_code=401, detail="You do not have access to this account")
    
    positions = {}

    raw_positions = redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if x_positions["Account_id"] == account_id:
            positions[x_positions["Ticker"]] = x_positions[3:]
    
    return {"message": "{positions}"}

@app.get("/positions/{ticker}")
def get_users_positions_for_ticker(ticker: str, username: str = Depends(verify_cookie)):

    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    positions = {}

    raw_positions = redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if x_positions["Account_id"] in user_data["accounts"] and x_positions["Ticker"] == ticker:
            if x_positions["Account_id"] not in positions:
                positions[x_positions["Account_id"]] = [x_positions[1:]]
            else:
                positions[x_positions["Account_id"]].append(x_positions[1:])
    
    return {"message": "{positions}"}


@app.get("/positions/{account_id}/{ticker}")
def get_accounts_positions_for_ticker(ticker: str, account_id = uuid, username: str = Depends(verify_cookie)):

    raw_user = redis_client.hget(redis_dictionaries[0], username)
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts"]:
         raise HTTPException(status_code=401, detail="You do not have access to this account")
    
    positions = {}

    raw_positions = redis_client.hgetall(redis_dictionaries[3])

    for x in raw_positions.values():
        x_positions = json.loads(x)
        if x_positions["Account_id"] == account_id and x_positions["ticker"] == ticker:
            positions[x_positions["Ticker"]] = x_positions["Quantity"]
    
    return {"message": "{positions}"}
#endregion
