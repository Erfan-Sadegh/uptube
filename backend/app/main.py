from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, jobs, me
from app.core.config import get_settings
from app.db import init_db

settings = get_settings()
allowed_origins = {
    settings.frontend_base_url.rstrip("/"),
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}

app = FastAPI(title="Uptube API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(jobs.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    try:
        from app.tasks import cleanup_expired_artifacts

        cleanup_expired_artifacts()
    except Exception:
        pass


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
