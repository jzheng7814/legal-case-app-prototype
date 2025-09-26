from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/pulse")
async def health_pulse() -> dict[str, str]:
    return {"status": "ok"}
