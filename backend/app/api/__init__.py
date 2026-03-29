from fastapi import APIRouter

api_v1_router = APIRouter()


@api_v1_router.get("/ping")
async def ping():
    return {"message": "pong", "version": "v1"}
