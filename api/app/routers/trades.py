from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime
from app.core.logging import logger
from app.core.security import verify_cookie
from app.models.trade_models import Trade
from app.services.trade_services import individual_trade, verify_account_access

router = APIRouter(tags=["Trades"])


@router.post("/trade")
async def create_trade(trade: list[Trade], user_id: str = Depends(verify_cookie)):
    logger.info("Recieved request to book trade data")

    if len(trade) == 0:  # Didn't send any trade data
        logger.warning("There was no trade data")
        raise HTTPException(status_code=422, detail="Invalid Trade Data")

    trade_return = []

    for trade_item in trade:  # Loop through each trade one at a time
        trade_return.append(
            await individual_trade(user_id, trade_item.model_dump())
        )  # Converts from class to dictionary for sorting

    return {"message": trade_return}


@router.get("/trades")
async def get_all_user_trades(request: Request, user_id: str = Depends(verify_cookie)):
    logger.info("Recieved request for trade data")

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 30
        """,
        user_id,
    )

    return [dict(row) for row in rows]


@router.get("/trades/account/{account_id}")
async def get_all_user_trades_for_account(
    account_id: str, request: Request, user_id: str = Depends(verify_cookie)
):
    logger.info("Recieved request for trade data")

    await verify_account_access(account_id, user_id)

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND account_id = $2
        ORDER BY created_at DESC
        LIMIT 30
        """,
        user_id,
        account_id,
    )

    return [dict(row) for row in rows]


@router.get("/trades/ticker/{ticker}")
async def get_all_user_trades_for_ticker(
    ticker: str, request: Request, user_id: str = Depends(verify_cookie)
):
    logger.info("Recieved request for trade data")

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND symbol_ticker = $2
        ORDER BY created_at DESC
        LIMIT 30
        """,
        user_id,
        ticker,
    )

    return [dict(row) for row in rows]


@router.get("/trades/account/{account_id}/ticker/{ticker}")
async def get_all_user_trades_for_account_for_ticker(
    account_id: str,
    ticker: str,
    request: Request,
    user_id: str = Depends(verify_cookie),
):
    logger.info("Recieved request for trade data")

    await verify_account_access(account_id, user_id)

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND account_id = $2
            AND symbol_ticker = $3
        ORDER BY created_at DESC
        LIMIT 30
        """,
        user_id,
        account_id,
        ticker,
    )

    return [dict(row) for row in rows]


@router.get("/trades/{trade_id}")
async def get_specific_trade(
    trade_id: str, request: Request, user_id: str = Depends(verify_cookie)
):
    logger.info("Recieved request for trade data")

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE trade_id = $1
        ORDER BY created_at DESC
        LIMIT 30
        """,
        trade_id,
    )

    return [dict(row) for row in rows]


@router.get("/trades/time")
async def get_all_user_trades_for_time(
    request: Request,
    time_start: datetime,
    time_end: datetime,
    user_id: str = Depends(verify_cookie),
):
    logger.info("Recieved request for trade data")

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND created_at BETWEEN $2 AND $3
        ORDER BY created_at DESC
        LIMIT 30
        """,
        user_id,
        time_start,
        time_end,
    )

    return [dict(row) for row in rows]


@router.get("/trades/account/{account_id}/time")
async def get_all_user_trades_for_account_for_time(
    account_id: str,
    request: Request,
    time_start: datetime,
    time_end: datetime,
    user_id: str = Depends(verify_cookie),
):
    logger.info("Recieved request for trade data")

    await verify_account_access(account_id, user_id)

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND account_id = $2
            AND created_at BETWEEN $3 AND $4
        ORDER BY created_at DESC
        LIMIT 30
        """,
        user_id,
        account_id,
        time_start,
        time_end,
    )

    return [dict(row) for row in rows]


@router.get("/trades/ticker/{ticker}/time")
async def get_all_user_trades_for_ticker_for_time(
    ticker: str,
    request: Request,
    time_start: datetime,
    time_end: datetime,
    user_id: str = Depends(verify_cookie),
):
    logger.info("Recieved request for trade data")

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND symbol_ticker = $2
            AND created_at BETWEEN $3 AND $4
        ORDER BY created_at DESC
        LIMIT 30
        """,
        user_id,
        ticker,
        time_start,
        time_end,
    )

    return [dict(row) for row in rows]


@router.get("/trades/account/{account_id}/ticker/{ticker}/time")
async def get_all_user_trades_for_account_for_ticker_for_time(
    account_id: str,
    ticker: str,
    request: Request,
    time_start: datetime,
    time_end: datetime,
    user_id: str = Depends(verify_cookie),
):
    logger.info("Recieved request for trade data")

    await verify_account_access(account_id, user_id)

    rows = await request.app.state.pg_pool.fetch(
        """
        SELECT *
        FROM trades
        WHERE user_id = $1
            AND account_id = $2
            AND symbol_ticker = $3
            AND created_at BETWEEN $4 AND $5
        ORDER BY created_at DESC
        LIMIT 30
        """,
        user_id,
        account_id,
        ticker,
        time_start,
        time_end,
    )

    return [dict(row) for row in rows]
