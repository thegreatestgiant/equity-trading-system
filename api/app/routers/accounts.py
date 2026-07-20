from fastapi import APIRouter, Depends
from app.core.logging import logger
from app.core.security import verify_cookie
from app.models.edit_account_details_models import Details
from app.services.account_services import (
    create_new_account,
    add_account_to_user,
    get_all_users_accounts,
    change_account_short_perms,
)

router = APIRouter(tags=["Accounts"])


@router.post("/users/account")
async def create_account(
    account_name: str, can_short: bool, user_id: str = Depends(verify_cookie)
):
    logger.info("Received new account request")

    account_id = await create_new_account(account_name, can_short, user_id)

    return {"message": "Account created", "account_id": f"{account_id}"}


@router.post("/users/send_account_to_other/{account_id}")
async def add_account(
    account_id: str, other_user: str, user_id: str = Depends(verify_cookie)
):
    logger.info("Received new account sync to user request")

    await add_account_to_user(account_id, other_user, user_id)

    return {"message": f"Account added to user {other_user}"}


@router.patch("/users/update_account_details/{account_id}")
async def change_short_perms(
    account_id: str, request: Details, user_id: str = Depends(verify_cookie)
):
    logger.info("Received new short change request")

    details = await change_account_short_perms(
        account_id,
        user_id=user_id,
        account_name=request.account_name,
        can_short=request.can_short,
    )

    details["message"] = "Perms changed"
    return details


@router.get("/users/allaccounts")
async def get_all_accounts(user_id: str = Depends(verify_cookie)):
    logger.info("Received new get all user's accounts request")

    account_details = await get_all_users_accounts(user_id)

    return {"accounts": account_details}
