from fastapi import APIRouter, HTTPException, Depends, Request, Query
from datetime import datetime
from app.core.logging import logger
from app.core.security import verify_cookie
from app.models.trade_models import Trade
from app.services.trade_services import (
    individual_trade,
    verify_account_access,
    verify_ticker_exists,
)

router = APIRouter(tags=["Trades"])


@router.post("/trade")
async def create_trade(trade: list[Trade], user_id: str = Depends(verify_cookie)):
    logger.info("Recieved request to book trade data")

    if len(trade) == 0:  # Didn't send any trade data
        logger.warning("There was no trade data")
        raise HTTPException(status_code=422, detail="Invalid Trade Data")

    trade_successes = []
    trade_failures = []

    for trade_item in trade:  # Loop through each trade one at a time
        try:
            trade_successes.append(
                await individual_trade(user_id, trade_item.model_dump())
            )  # Converts from class to dictionary for sorting
        except HTTPException as e:
            logger.error(f"Trade failed: {e.detail}")
            trade_failures.append({"Failure Reason": e.detail})

    return {
        "message": f"Trades processed. Successes: {len(trade_successes)}, Failures: {len(trade_failures)}",
        "successes": trade_successes,
        "failures": trade_failures,
    }


@router.get("/trades")
async def get_user_trades(
    request: Request,
    user_id: str = Depends(verify_cookie),
    account_id: str | None = None,
    ticker: str | None = None,
    time_start: datetime | None = None,
    time_end: datetime | None = None,
    cursor_created_at: datetime | None = None,
    cursor_trade_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    logger.info("Received request for trade data")

    query = """
        SELECT *
        FROM trades
        WHERE user_id = $1
    """

    params = [user_id]
    param = 2

    if account_id is not None:
        await verify_account_access(account_id, user_id)
        query += f"""
            AND account_id = ${param}
        """
        params.append(account_id)
        param += 1

    if ticker is not None:
        await verify_ticker_exists(ticker)
        query += f"""
            AND symbol_ticker = ${param}
        """
        params.append(ticker)
        param += 1

    if time_start is not None:
        query += f"""
            AND created_at >= ${param}
        """
        params.append(time_start)
        param += 1

    if time_end is not None:
        query += f"""
            AND created_at <= ${param}
        """
        params.append(time_end)
        param += 1

    if cursor_created_at is not None and cursor_trade_id is not None:
        query += f"""
            AND (created_at, trade_id) < (${param}, ${param + 1})
        """
        params.append(cursor_created_at)
        params.append(cursor_trade_id)
        param += 2

    query += f"""
        ORDER BY created_at DESC, trade_id DESC
        LIMIT ${param}
    """

    params.append(limit)

    rows = await request.app.state.pg_pool.fetch(query, *params)

    trades = [dict(row) for row in rows]

    next_cursor = None
    if rows:
        next_cursor = {
            "created_at": rows[-1]["created_at"],
            "trade_id": rows[-1]["trade_id"],
        }

    return {
        "trades": trades,
        "next_cursor": next_cursor,
    }
