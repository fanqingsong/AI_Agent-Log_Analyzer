"""Stream-replay of bundled sample logs through the pipeline."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from app.chat.repository import ChatDB
from app.llm.agent import LogAgent
from app.logs.repository import Redis
from app.logs.service import process_single_log

# test_logs/ lives at the project root, one level above the app/ package.
LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "test_logs"
MAX_SIMULATE_LINES = 500  # safety cap to avoid runaway streams


def list_sources() -> list[dict]:
    """Return metadata for every bundled ``.log`` sample file."""
    if not LOGS_DIR.is_dir():
        return []

    sources = []
    for p in sorted(LOGS_DIR.iterdir()):
        if p.is_file() and p.suffix == ".log":
            try:
                with p.open("rb") as f:
                    line_count = sum(1 for _ in f)
            except OSError:
                line_count = 0
            sources.append({
                "name": p.name,
                "size": p.stat().st_size,
                "lines": line_count,
            })
    return sources


def resolve_source(source_name: str) -> Path | None:
    """Return the path of a sample file, or None if it does not exist."""
    path = LOGS_DIR / source_name
    return path if path.is_file() else None


async def simulate(
    source_path: Path,
    limit: int,
    delay: float,
    realtime: bool,
    db: ChatDB,
    redis_db: Redis,
    log_agent: LogAgent,
) -> AsyncGenerator[bytes, None]:
    """Replay a sample file line by line, yielding NDJSON outcome events."""
    limit = min(limit, MAX_SIMULATE_LINES)
    sent = 0
    prev_ts = None
    try:
        with source_path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                if sent >= limit:
                    break
                line = raw_line.rstrip("\n")
                if not line.strip():
                    continue

                if realtime:
                    ts_str = line.split("]")[0].strip("[]")
                    try:
                        cur_ts = datetime.strptime(
                            ts_str, "%Y-%m-%d %H:%M:%S,%f"
                        )
                        if prev_ts is not None:
                            delta = (cur_ts - prev_ts).total_seconds()
                            if 0 < delta < 30:
                                await asyncio.sleep(delta)
                        prev_ts = cur_ts
                    except ValueError:
                        prev_ts = None
                elif delay > 0:
                    await asyncio.sleep(delay)

                result = await process_single_log(
                    line, db, redis_db, log_agent, notify_discord=False
                )
                sent += 1
                result["sent"] = sent
                result["total"] = limit
                yield json.dumps(result).encode("utf-8") + b"\n"
    except Exception as e:
        yield json.dumps({"error": str(e)}).encode("utf-8") + b"\n"
