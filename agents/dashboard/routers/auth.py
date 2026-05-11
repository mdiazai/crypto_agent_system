from datetime import timedelta
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm

from shared.config import settings
from agents.dashboard.auth import create_access_token, get_current_user, verify_credentials
from agents.dashboard.schemas import LoginRequest, TokenResponse, MessageResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    if not verify_credentials(form.username, form.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(form.username)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.jwt_access_token_expire_minutes,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(current_user: dict = Depends(get_current_user)):
    token = create_access_token(current_user["username"])
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.jwt_access_token_expire_minutes,
    )


@router.get("/me", response_model=MessageResponse)
async def me(current_user: dict = Depends(get_current_user)):
    return MessageResponse(message=f"Autenticado como: {current_user['username']}")
