from fastapi import APIRouter, FastAPI

app = FastAPI(title="CompaBook API")

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router)
