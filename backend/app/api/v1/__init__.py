from fastapi import APIRouter

from app.api.v1.approvals import router as approvals_router
from app.api.v1.runs import router as runs_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(runs_router)
v1_router.include_router(approvals_router)
