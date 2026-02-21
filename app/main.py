"""
main.py — FastAPI entrypoint.

Exposes: POST /fix
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.agent_runner import run_agent

# ── logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("main")

# ── app ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Codex Agent",
    description="Autonomous AI-powered GitHub code-fixing agent.",
    version="1.0.0",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/fix")
async def fix_endpoint(
    repo_url: str = Form(..., description="HTTPS GitHub repository URL"),
    bug_description: str = Form(..., description="Human-readable bug description"),
    image: Optional[UploadFile] = File(None, description="Optional screenshot"),
) -> JSONResponse:
    """
    Receive a bug report, apply an AI-generated fix, and open a Pull Request.
    """
    logger.info("POST /fix  repo=%s", repo_url)

    # Read optional image
    image_bytes: bytes | None = None
    if image is not None:
        image_bytes = await image.read()
        if len(image_bytes) == 0:
            image_bytes = None

    try:
        result = await run_agent(
            repo_url=repo_url,
            bug_description=bug_description,
            image_bytes=image_bytes,
        )
    except ValueError as exc:
        logger.warning("validation error: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("agent error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal agent error") from exc

    return JSONResponse(content=result)
