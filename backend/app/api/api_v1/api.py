from fastapi import APIRouter
from app.api.api_v1.endpoints import profiles, votes, auth, admin, users, categories

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
api_router.include_router(votes.router, prefix="/votes", tags=["votes"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
