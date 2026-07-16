from fastapi import HTTPException
from datetime import datetime, timezone
import uuid
import json
from app.core.redis import redis_client, redis_dictionaries
from app.core.logging import logger


async def create_new_account(account_name: str, can_short: bool, user_id: str):
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
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    user_data["accounts_associated"].append(account_id)
    user_data["updated_at"] = now

    await redis_client.hset(redis_dictionaries[0], user_id, json.dumps(user_data))

    return account_id


async def add_account_to_user(account_id: str, other_user: str, user_id: str):
    # Grab User to add account to them
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    if account_id not in user_data["accounts_associated"]:
        logger.warning("Invalid account_id for user")
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    other_uuid = await redis_client.hget(redis_dictionaries[3], other_user)

    if other_uuid is None:
        logger.warning("User does not exist")
        raise HTTPException(status_code=401, detail="The requested user does not exist")
    else:
        raw_other_data = await redis_client.hget(redis_dictionaries[0], other_uuid)
        other_data = json.loads(raw_other_data)
        other_data["accounts_associated"].append(account_id)
        other_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await redis_client.hset(
            redis_dictionaries[0], other_uuid, json.dumps(other_data)
        )


async def change_account_short_perms(
    account_id: str, account_name: str, can_short: bool, user_id: str
):
    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    # Get account to ensure it exists
    raw_account = await redis_client.hget(redis_dictionaries[1], account_id)
    if not raw_account:
        logger.warning("Invalid account given")
        raise HTTPException(status_code=404, detail="This account does not exist")

    if account_id not in user_data["accounts_associated"]:
        logger.warning("Invalid accound_id for user")
        raise HTTPException(
            status_code=401, detail="You do not have access to this account"
        )

    return_message = {}

    account_data = json.loads(raw_account)
    if account_name is not None:
        account_data["account_name"] = account_name
        return_message["account_name"] = account_name
    else:
        return_message["account_name"] = account_data["account_name"]
    if can_short is not None:
        account_data["can_short"] = can_short
        return_message["can_short"] = can_short
    else:
        return_message["can_short"] = account_data["can_short"]

    await redis_client.hset(redis_dictionaries[1], account_id, json.dumps(account_data))

    return return_message


async def get_all_users_accounts(user_id: str):

    raw_user = await redis_client.hget(redis_dictionaries[0], user_id)
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    account_name = []
    for account in user_data["accounts_associated"]:
        account_raw = await redis_client.hget(redis_dictionaries[1], account)
        accont_real = json.loads(account_raw)
        account_name.append(accont_real["account_name"])

    return dict(zip(account_name, user_data["accounts_associated"]))
