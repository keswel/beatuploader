from fastapi import APIRouter

from app.api import auth, library, platforms, uploads

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(platforms.router)
api_router.include_router(uploads.router)
api_router.include_router(library.router)
