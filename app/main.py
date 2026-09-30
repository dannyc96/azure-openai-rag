"""FastAPI entry point.

Routes:
  POST /api/chat  question in, grounded answer + citations out
  GET  /healthz   liveness probe
  GET  /          static single-page chat UI
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import load_settings
from app.rag import RagEngine

logger = logging.getLogger("azure-openai-rag")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STATIC_DIR = Path(__file__).parent / "static"


class HistoryTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=20)


class Citation(BaseModel):
    title: str
    source: str
    content: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[Citation]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Build clients once at startup. DefaultAzureCredential resolves to the
    # Container App's managed identity in Azure, or az login locally.
    app.state.engine = RagEngine(load_settings())
    logger.info("RAG engine initialized")
    yield


app = FastAPI(
    title="Northwind Robotics Knowledge Assistant",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    engine: RagEngine = app.state.engine
    history = [turn.model_dump() for turn in request.history]
    try:
        # The Azure SDK calls are synchronous, keep them off the event loop.
        result = await run_in_threadpool(engine.answer, request.message, history)
    except Exception:
        logger.exception("chat request failed")
        raise HTTPException(
            status_code=502,
            detail="Upstream Azure call failed. Check the app's role assignments and logs.",
        ) from None
    return ChatResponse(
        answer=result.answer,
        sources=[Citation(**chunk.as_dict()) for chunk in result.sources],
    )


# Mounted last so /api and /healthz take precedence.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
