from fastapi import APIRouter
from app.api.api_v1.endpoints import (
    profiles,
    votes,
    auth,
    admin,
    users,
    categories,
    notifications,
    badges,
    reports,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
api_router.include_router(votes.router, prefix="/votes", tags=["votes"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(notifications.router, tags=["notifications"])
api_router.include_router(badges.router, prefix="/badges", tags=["badges"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
