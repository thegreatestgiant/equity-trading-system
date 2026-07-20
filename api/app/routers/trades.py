from fastapi import APIRouter, HTTPException, Depends, Request, Query
from datetime import datetime
from app.core.logging import logger
from app.core.security import verify_cookie
from app.models.trade_models import Trade
from app.services.trade_services import (
    individual_trade,
    verify_account_access,
    verify_ticker_exists,
    verify_other_account,
    verify_trade_details,
    get_user_data,
    get_account_data,
)
from app.services.position_services import edit_position

router = APIRouter(tags=["Trades"])


@router.get("/tickers")
async def get_tickers(user_id: str = Depends(verify_cookie)):
    logger.info("Received request for valid tickers")

    from app.services.ticker_service import valid_tickers

    return {"valid_tickers": list(valid_tickers)}


@router.post("/trade")
async def create_trade(trade: list[Trade], user_id: str = Depends(verify_cookie)):
    logger.info("Received request to book trade data")

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
            logger.warning(f"Trade failed: {e.detail}")
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
    filter_by_my_trades: bool | None = False,
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
    """

    params = []
    param = 1

    if account_id is not None:
        await verify_account_access(account_id, user_id)
        query += f"""
            WHERE account_id = ${param}
        """
        params.append(account_id)
        param += 1
    else:
        user_data = await get_user_data(user_id)
        query += f"""
            WHERE account_id = ANY(${param})
        """
        params.append(user_data["accounts_associated"])
        param += 1

    if filter_by_my_trades:
        query += f"""
            AND user_id = ${param}
        """
        params.append(user_id)
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


@router.get("/trade/{trade_id}")
async def get_trade_by_id(
    trade_id: str,
    request: Request,
    user_id: str = Depends(verify_cookie),
):
    logger.info(f"Received request for trade data with trade_id: {trade_id}")

    query = """
        SELECT *
        FROM trades
        WHERE trade_id = $1 AND user_id = $2
    """

    row = await request.app.state.pg_pool.fetchrow(query, trade_id, user_id)

    if row is None:
        logger.warning(f"Trade with trade_id {trade_id} not found for user {user_id}")
        raise HTTPException(status_code=404, detail="Trade not found")

    return dict(row)


@router.patch("/edit_trade/{trade_id}")
async def update_trade(
    trade_id: str,
    trade: Trade,
    request: Request,
    user_id: str = Depends(verify_cookie),
):
    logger.info(f"Received request to update trade with trade_id: {trade_id}")

    # Check if the trade exists and belongs to the user
    existing_trade = await request.app.state.pg_pool.fetchrow(
        "SELECT * FROM trades WHERE trade_id = $1 AND user_id = $2",
        trade_id,
        user_id,
    )

    if existing_trade is None:
        logger.warning(f"Trade with trade_id {trade_id} not found for user {user_id}")
        raise HTTPException(status_code=404, detail="Trade not found")

    user_data = await get_user_data(user_id)  # Fetch user data from Redis
    await get_account_data(
        trade.account_id
    )  # Ensure this account_id exists in the database
    existing_trade_dict = dict(existing_trade)

    trade.other_account = verify_other_account(
        trade.other_account
    )  # Validate other_account

    await verify_trade_details(trade.model_dump(), user_data)  # Validate trade details

    await edit_position(
        user_id, existing_trade_dict, trade.model_dump(), trade.other_account, trade_id
    )  # Revert the position change from the existing trade and apply the position change from the updated trade

    logger.info(
        f"Trade with trade_id {trade_id} updated successfully for user {user_id}"
    )

    return {
        "status": "accepted",
        "trade_id": trade_id,
    }
