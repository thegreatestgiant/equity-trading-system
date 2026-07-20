from fastapi import HTTPException
from datetime import datetime, timezone
import json
import uuid
from app.core.redis import redis_client, USERS_KEY, USERNAMES_KEY
from app.core.security import pwd_context
from app.core.logging import logger
from app.core.config import DAY_IN_SEC


async def register_valid_user(username: str, password: str):
    # Check if the username already exists in Redis
    old_uuid = await redis_client.hget(USERNAMES_KEY, username)

    if old_uuid:
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
    # send new User to redis (both writes atomically so neither can land alone)
    pipe = redis_client.pipeline(transaction=True)
    pipe.hset(USERS_KEY, user_id, json.dumps(user_data))
    pipe.hset(USERNAMES_KEY, username, user_id)
    await pipe.execute()

    return user_id


async def login_valid_user(username: str, password: str):
    # Get the User data from redis
    old_uuid = await redis_client.hget(USERNAMES_KEY, username)

    if not old_uuid:
        logger.warning("Invalid login attempt")
        raise HTTPException(status_code=401, detail="Wrong Username or Password")

    old_uuid = old_uuid.decode() if isinstance(old_uuid, bytes) else old_uuid

    raw_user_data = await redis_client.hget(USERS_KEY, old_uuid)
    if raw_user_data is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    real_user_data = json.loads(raw_user_data)

    if not pwd_context.verify(password, real_user_data["oauth_key"]):
        logger.warning("Invalid login attempt")
        raise HTTPException(status_code=401, detail="Wrong Username or Password")

    return old_uuid


async def blacklist_cookie(cookie):
    await redis_client.set(f"blacklist:{cookie}", "true", ex=DAY_IN_SEC)
