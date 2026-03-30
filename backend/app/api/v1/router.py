from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.companions import router as companions_router
from app.api.v1.hospitals import router as hospitals_router
from app.api.v1.orders import router as orders_router
from app.api.v1.patients import router as patients_router
from app.api.v1.users import router as users_router

api_v1_router = APIRouter()


@api_v1_router.get("/ping")
async def ping():
    return {"message": "pong", "version": "v1"}


api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(patients_router)
api_v1_router.include_router(companions_router)
api_v1_router.include_router(hospitals_router)
api_v1_router.include_router(orders_router)
