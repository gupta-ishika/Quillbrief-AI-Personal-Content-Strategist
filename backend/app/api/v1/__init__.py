from fastapi import APIRouter

from app.api.v1.approvals import router as approvals_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.plans import router as plans_router
from app.api.v1.runs import router as runs_router
from app.api.v1.settings import router as settings_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(runs_router)
v1_router.include_router(approvals_router)
v1_router.include_router(plans_router)
v1_router.include_router(settings_router)
v1_router.include_router(onboarding_router)
