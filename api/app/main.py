from fastapi import FastAPI
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
from app.core.database import create_pool
from app.core.redis import redis_client
from app.core.logging import logger
from app.services import ticker_service
from app.middleware.logging_middleware import logging_middleware
import asyncio
import logbook.compat

from app.routers import (
    auth,
    accounts,
    positions,
    trades,
    health,
)

logbook.compat.redirect_logging()  # call before uvicorn starts logging


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting up API")

    try:
        app.state.pg_pool = await create_pool()

        logger.info("Synced with postgres")

    except Exception as e:
        logger.error(f"PostgreSQL startup failure: {e}")
        raise

    try:
        await redis_client.ping()

        logger.info("Redis connected")

    except Exception as e:
        logger.error(f"Redis startup failure: {e}")
        raise

    start = 0

    while start < 5:
        ticker_service.valid_tickers = await ticker_service.load_sp500()
        if len(ticker_service.valid_tickers) == 0:
            logger.warning("No valid tickers found, retrying in 5 seconds")
            start += 1
            await asyncio.sleep(5)
        else:
            logger.info("Loaded S&P Tickers")
            break
    if len(ticker_service.valid_tickers) == 0:
        logger.error("No valid tickers found after 5 attempts")
        raise Exception("No valid tickers found after 5 attempts")

    yield

    await app.state.pg_pool.close()
    await redis_client.aclose()

    logger.info("Closed connection to Postgres")
    logger.info("Closing down API")


app = FastAPI(lifespan=lifespan)
Instrumentator(should_instrument_requests_inprogress=True).instrument(app).expose(
    app, endpoint="/metrics"
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(positions.router)
app.include_router(trades.router)
app.include_router(health.router)

app.middleware("http")(logging_middleware)
