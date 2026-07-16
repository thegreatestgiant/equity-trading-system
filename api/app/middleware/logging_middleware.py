# import os
# import socket

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
import time
import asyncpg

# import asyncio
from app.core.logging import logger
# from app.core import request_counter


async def logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    # request_counter.active_requests += 1
    # logger.warning(
    #     f"REQUEST START {request.method} {request.url.path} "
    #     f"pod={socket.gethostname()} pid={os.getpid()}"
    # )

    # if request_counter.active_requests > request_counter.active_high_water:
    #     request_counter.active_high_water = request_counter.active_requests
    #     logger.warning(
    #         f"New high water mark for active requests: {request_counter.active_high_water}"
    #     )

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

        # if duration_ms > 1000:
        #     logger.warning(
        #         f"SLOW_REQUEST "
        #         f"{request.method} "
        #         f"{request.url.path} "
        #         f"{duration_ms:.1f}ms "
        #         f"active={request_counter.active_requests}"
        #     )

        return response

    except HTTPException:
        raise

    except asyncpg.PostgresError as e:
        logger.error(f"PostgreSQL failure: {e}")
        return JSONResponse(
            status_code=503,
            content={"detail": "Database unavailable"},
        )

    except RedisError as e:
        logger.error(f"Redis failure: {e}")
        return JSONResponse(
            status_code=503,
            content={"detail": "Redis unavailable"},
        )

    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
    # except asyncio.CancelledError:
    #     logger.warning(f"Request cancelled, pod={socket.gethostname()}")
    #     raise
    # finally:
    #     logger.warning(
    #         f"REQUEST END {request.method} {request.url.path} "
    #         f"pod={socket.gethostname()} pid={os.getpid()}"
    #     )
    #     request_counter.active_requests -= 1
