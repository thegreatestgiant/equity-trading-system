from fastapi import APIRouter, Response, Request, Depends
from app.core.logging import logger
from app.core.security import create_cookie, verify_cookie
from app.core.config import DAY_IN_SEC
from app.models.auth_models import RegisterRequest, LoginRequest
from app.services.auth_services import (
    register_valid_user,
    login_valid_user,
    blacklist_cookie,
)

router = APIRouter(tags=["Login"])


@router.post("/register")
async def register_user(request: RegisterRequest, response: Response):
    logger.info("Received new user request")

    user_id = await register_valid_user(
        username=request.username, password=request.password
    )

    # Create token for authentication
    authentication_cookie = create_cookie(user_id)
    response.set_cookie(
        key="session",
        value=authentication_cookie,
        httponly=True,
        samesite="lax",
        max_age=DAY_IN_SEC,
    )

    return {"message": "User registered successfully", "user_id": f"{user_id}"}


@router.post("/login")
async def login_user(request: LoginRequest, response: Response):
    logger.info("Received new login request")

    id = await login_valid_user(username=request.username, password=request.password)

    # Create token for authentication
    authentication_cookie = create_cookie(id)
    response.set_cookie(
        key="session",
        value=authentication_cookie,
        httponly=True,
        samesite="lax",
        max_age=DAY_IN_SEC,
    )

    return {"message": "login successful."}


@router.post("/logout")
async def logout(response: Response, request: Request):
    logger.info("Received new logout request")
    cookie = request.cookies.get("session")

    if cookie:
        await blacklist_cookie(cookie)

    response.delete_cookie(key="session", httponly=True, samesite="lax")

    return {"message": "logged out"}


@router.get("/me")
async def get_current_user(user_id: str = Depends(verify_cookie)):
    return {"user_id": user_id, "status": "success"}
