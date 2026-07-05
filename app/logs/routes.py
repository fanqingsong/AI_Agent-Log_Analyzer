"""HTTP routes for the logs service (ingest + simulator)."""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.chat.repository import ChatDB
from app.deps import get_db, get_log_agent, get_redis_db
from app.logs.repository import Redis
from app.logs.service import process_single_log
from app.logs.simulator import resolve_source, simulate, list_sources
from app.llm.agent import LogAgent

router = APIRouter()


@router.post("/logs/ingest")
async def log_receiver(
    request: Request,
    background_tasks: BackgroundTasks,
    db: ChatDB = Depends(get_db),
    redis_db: Redis = Depends(get_redis_db),
    log_agent: LogAgent = Depends(get_log_agent),
):
    """Receive a log (as string) and trigger async LLM analysis in the background."""
    request_body = await request.body()
    log_text: str = json.loads(request_body)

    result = await process_single_log(
        log_text, db, redis_db, log_agent,
        background_tasks=background_tasks,
        notify_email=True,
    )
    return {"status": "received", **{k: v for k, v in result.items() if k != 'raw'}}


@router.get("/logs/sources")
async def list_log_sources() -> JSONResponse:
    """List bundled sample log files available for simulation."""
    return JSONResponse(status_code=200, content={"sources": list_sources()})


@router.post("/logs/simulate")
async def simulate_logs(
    request: Request,
    db: ChatDB = Depends(get_db),
    redis_db: Redis = Depends(get_redis_db),
    log_agent: LogAgent = Depends(get_log_agent),
) -> StreamingResponse:
    """Stream a bundled sample log file through the pipeline line by line.

    Body (JSON): ``{"source", "limit", "delay", "realtime"}``.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    source_name = body.get("source", "deanonymized_server_backup.log")
    limit = int(body.get("limit", 100))
    delay = float(body.get("delay", 0.0))
    realtime = bool(body.get("realtime", False))

    source_path = resolve_source(source_name)
    if source_path is None:
        async def err():
            yield json.dumps(
                {"error": f"source '{source_name}' not found"}
            ).encode("utf-8") + b"\n"
        return StreamingResponse(err(), media_type="text/plain")

    return StreamingResponse(
        simulate(source_path, limit, delay, realtime, db, redis_db, log_agent),
        media_type="text/plain",
    )
