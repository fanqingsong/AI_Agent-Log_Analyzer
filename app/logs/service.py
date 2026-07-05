"""Core log-analysis business logic.

``process_single_log`` is the single entry point for the logs pipeline,
shared by both ``/logs/ingest`` and ``/logs/simulate``.
"""

import asyncio
import json
from typing import Optional

from fastapi import BackgroundTasks
from pydantic_ai import RunContext

from app.chat.repository import ChatDB
from app.llm.agent import LogAgent
from app.logs.parsing import (
    format_trigger_log, generate_chat_id, log_to_json, send_email,
)
from app.logs.repository import Redis, get_logs_before, make_redis_log_id, store_log_redis


def register_system_prompt(log_agent: LogAgent) -> None:
    """Attach the DevOps analysis system-prompt decorator to the agent."""

    @log_agent.agent.system_prompt
    def explain_log(ctx: RunContext[str]) -> str:
        instr_prompt = (
            "Analyze main_log, as instructed in system prompt. "
            "Use earlier_logs if useful."
        )
        return f"{instr_prompt}: {ctx.deps}"


async def process_single_log(
    log_text: str,
    db: ChatDB,
    redis_db: Redis,
    log_agent: LogAgent,
    *,
    background_tasks: Optional[BackgroundTasks] = None,
    notify_email: bool = False,
) -> dict:
    """Process one raw log line end-to-end and return an outcome dict.

    Steps: validate → store Redis → (if ERROR/WARN) enqueue LLM analysis →
    optionally send an email alert.
    """
    log_text = log_text.strip()
    if not log_text:
        return {"status": "skipped", "reason": "empty line"}

    validated_log: dict = log_to_json(log_text)
    redis_log_id: str = make_redis_log_id()
    await store_log_redis(redis_db, redis_log_id, validated_log)

    result: dict = {"log_id": redis_log_id, "raw": log_text}

    if validated_log.get('valid_log'):
        unpacked_log = validated_log['valid_log']
        result["level"] = unpacked_log.get('level')
        result["valid"] = True

        if unpacked_log.get('level') in ('ERROR', 'WARN'):
            earlier_logs: list = await get_logs_before(redis_db, redis_log_id)
            log_bundle: dict = {
                'main_log': unpacked_log,
                'earlier_logs': earlier_logs,
            }

            if background_tasks is not None:
                background_tasks.add_task(ask_and_save, log_bundle, db, log_agent)
            else:
                asyncio.create_task(ask_and_save(log_bundle, db, log_agent))

            if notify_email:
                send_email(
                    f"I have got problem with the following log: {log_text}"
                    f"\n Please find proposal solution at http://127.0.0.1:8000/"
                )

            result["triggered"] = True
        else:
            result["triggered"] = False
    else:
        result["valid"] = False

        if notify_email:
            send_email(
                f"I have encountered unstructured log:\n {log_text}"
                f"\n Please have a look at http://127.0.0.1:8000/"
            )

    return result


async def ask_AI(log_bundle: dict, log_agent: LogAgent) -> str:
    """Run the LLM agent on a log bundle and return messages JSON."""
    trigger_log: dict = log_bundle['main_log']
    log_parsed = format_trigger_log(trigger_log)
    chat_id = generate_chat_id()

    try:
        AI_reply = await log_agent.agent.run(user_prompt=log_parsed, deps=log_bundle)

        messages_json = AI_reply.new_messages_json()
        try:
            messages = json.loads(messages_json)
        except Exception:
            messages = [json.loads(messages_json)]

        for msg in messages:
            msg['chatId'] = chat_id

        return json.dumps(messages)

    except Exception as e:
        print("An unexpected error occurred: ", e)
        raise


async def ask_and_save(log_bundle: dict, db: ChatDB, log_agent: LogAgent) -> None:
    """Run LLM analysis and persist the result to the chat DB."""
    model_json_resp = await ask_AI(log_bundle, log_agent)
    if model_json_resp:
        await db.add_messages(model_json_resp)
