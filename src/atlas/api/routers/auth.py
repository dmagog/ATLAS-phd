from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from atlas.core.logging import logger
from atlas.core.rate_limit import check_login_attempt, reset_login_attempts
from atlas.core.security import burn_dummy_verify, create_access_token, verify_password
from atlas.db.session import get_db
from atlas.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # Rate-limit ДО запроса в БД, чтобы атакующий не мог превратить
    # /auth/login в инструмент перебора паролей или энумерации
    # пользователей по 200/401.
    check_login_attempt(request, body.email)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Constant-time defense: если пользователь не существует или soft-deleted,
    # всё равно вызываем verify против dummy-хеша, чтобы время ответа не
    # отличалось от случая «пароль неверный, но email существует».
    client_ip = request.client.host if request.client else None
    if user is None or user.deleted_at is not None:
        burn_dummy_verify(body.password)
        logger.info("login_failed", reason="unknown_or_deleted",
                    email=body.email, ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(body.password, user.hashed_password):
        logger.info("login_failed", reason="bad_password",
                    user_id=str(user.id), ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Успешный логин — сбрасываем счётчик, чтобы пользователь с прежними
    # опечатками не блокировался.
    reset_login_attempts(request, body.email)

    # role is TEXT (M4.A), no .value needed. jwt_version snapshots into the
    # token so role-revocation (M4.C) can invalidate it (BDD 7.5).
    token = create_access_token(str(user.id), user.role, user.jwt_version)
    logger.info("login_success", user_id=str(user.id), role=user.role)
    return TokenResponse(access_token=token)
