from fastapi import APIRouter, Depends
from app.core.logging import logger
from app.core.security import verify_cookie
from app.services.position_services import (
    get_all_users_positions,
    get_all_accounts_positions,
    get_all_users_ticker_positions,
    get_account_ticker_position,
)

router = APIRouter(tags=["Positions"])


@router.get("/positions")
async def get_users_positions(user_id: str = Depends(verify_cookie)):
    logger.info("Received request to get all of a user's positions")

    positions = await get_all_users_positions(user_id)

    return {"message": positions}


@router.get("/positions/accounts/{account_id}")
async def get_accounts_positions(
    account_id: str, user_id: str = Depends(verify_cookie)
):
    logger.info("Received request for all of an account's positions")

    positions = await get_all_accounts_positions(account_id, user_id)

    return {"message": positions}


@router.get("/positions/ticker/{ticker}")
async def get_users_positions_for_ticker(
    ticker: str, user_id: str = Depends(verify_cookie)
):
    logger.info("Received request for user's positions for a ticker")

    positions = await get_all_users_ticker_positions(ticker, user_id)

    return {"message": positions}


@router.get("/positions/accounts/{account_id}/ticker/{ticker}")
async def get_accounts_positions_for_ticker(
    ticker: str, account_id: str, user_id: str = Depends(verify_cookie)
):
    logger.info("Received request for an account's position by ticker")

    positions = await get_account_ticker_position(ticker, account_id, user_id)

    return {"message": positions}
