from fastapi import HTTPException
from datetime import datetime, timezone
import uuid
import json
from app.core.redis import redis_client, USERS_KEY, ACCOUNTS_KEY, USERNAMES_KEY
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

    # Grab User first so a missing user does not leave an orphan account
    raw_user = await redis_client.hget(USERS_KEY, user_id)
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    user_data["accounts_associated"].append(account_id)
    user_data["updated_at"] = now

    # Write the account and the updated user atomically
    pipe = redis_client.pipeline(transaction=True)
    pipe.hset(ACCOUNTS_KEY, account_id, json.dumps(account_data))
    pipe.hset(USERS_KEY, user_id, json.dumps(user_data))
    await pipe.execute()

    return account_id


async def add_account_to_user(account_id: str, other_user: str, user_id: str):
    # Grab the acting user and resolve the other user's uuid in one round trip
    pipe = redis_client.pipeline()
    pipe.hget(USERS_KEY, user_id)
    pipe.hget(USERNAMES_KEY, other_user)
    raw_user, other_uuid = await pipe.execute()

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

    if other_uuid is None:
        logger.warning("User does not exist")
        raise HTTPException(status_code=401, detail="The requested user does not exist")
    else:
        raw_other_data = await redis_client.hget(USERS_KEY, other_uuid)
        other_data = json.loads(raw_other_data)
        other_data["accounts_associated"].append(account_id)
        other_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await redis_client.hset(
            USERS_KEY, other_uuid, json.dumps(other_data)
        )


async def change_account_short_perms(
    account_id: str, account_name: str, can_short: bool, user_id: str
):
    # Grab the user and the account in one round trip
    pipe = redis_client.pipeline()
    pipe.hget(USERS_KEY, user_id)
    pipe.hget(ACCOUNTS_KEY, account_id)
    raw_user, raw_account = await pipe.execute()

    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    # Get account to ensure it exists
    if not raw_account:
        logger.warning("Invalid account given")
        raise HTTPException(status_code=404, detail="This account does not exist")

    if account_id not in user_data["accounts_associated"]:
        logger.warning("Invalid account_id for user")
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

    await redis_client.hset(ACCOUNTS_KEY, account_id, json.dumps(account_data))

    return return_message


async def get_all_users_accounts(user_id: str):

    raw_user = await redis_client.hget(USERS_KEY, user_id)
    if raw_user is None:
        raise HTTPException(
            status_code=503, detail="The database has crashed, try again later"
        )
    user_data = json.loads(raw_user)

    pipe = redis_client.pipeline()

    for account_id in user_data["accounts_associated"]:
        pipe.hget(ACCOUNTS_KEY, account_id)

    results = await pipe.execute()

    accounts = []

    for account_id, raw_account in zip(user_data["accounts_associated"], results):
        account_real = json.loads(raw_account)
        accounts.append(
            {
                "account_id": account_id,
                "account_name": account_real["account_name"],
                "can_short": account_real["can_short"],
            }
        )

    return accounts
