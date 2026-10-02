from fastapi import APIRouter

from app.api import auth, library, platforms, uploads
from app.config import get_settings

api_router = APIRouter(prefix="/api")

if get_settings().local_mode:
    # Desktop app: no accounts, so no register/login/password/Google sign-in.
    # Only the profile endpoints (handle + YouTube description template) stay.
    local_auth = APIRouter(prefix="/auth", tags=["auth"])
    local_auth.add_api_route("/me", auth.me, methods=["GET"], response_model=auth.UserOut)
    local_auth.add_api_route(
        "/me", auth.update_me, methods=["PATCH"], response_model=auth.UserOut
    )
    api_router.include_router(local_auth)
else:
    api_router.include_router(auth.router)

api_router.include_router(platforms.router)
api_router.include_router(uploads.router)
api_router.include_router(library.router)
