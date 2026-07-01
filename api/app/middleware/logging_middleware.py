from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
import time
import asyncpg
from app.core.logging import logger


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
        logger.exception(f"PostgreSQL failure: {e}")
        return JSONResponse(
            status_code=503,
            content={"detail": "Database unavailable"},
        )

    except RedisError as e:
        logger.exception(f"Redis failure: {e}")
        return JSONResponse(
            status_code=503,
            content={"detail": "Redis unavailable"},
        )

    except Exception:
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
