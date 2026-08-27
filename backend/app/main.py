from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import auth, runs, ws
from app.services import mcp_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Fail loudly and immediately if the sibling mcp-toolkit-ai checkout isn't where expected,
    # rather than lazily on the first run a user happens to submit.
    mcp_config.resolve_toolkit_path()
    yield


app = FastAPI(title="Agent Ops Dashboard", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(runs.router)
app.include_router(ws.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
