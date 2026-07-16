from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Cookie
from passlib.context import CryptContext
import jwt
from app.core.logging import logger
from app.core.config import DAY_IN_SEC
from app.core.redis import redis_client


def create_cookie(username: str):

    payload = {
        "username": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=DAY_IN_SEC),
    }
    session_token = jwt.encode(payload, secret_key, algorithm=algorithm)
    return session_token


async def verify_cookie(session: str = Cookie(None)):
    if not session:
        logger.warning("No login cookie")
        raise HTTPException(status_code=401, detail="Not authenticated")

    blacklisted = await redis_client.exists(f"blacklist:{session}")

    if blacklisted:
        raise HTTPException(status_code=401, detail="Session expired")

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


secret_key = (
    "mysecretkey"  # Encryption Key for passwords TODO come up with something better
)
algorithm = "HS256"
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
