from contextlib import asynccontextmanager
from datetime import datetime, timezone
from app.Postgres_DB.DB_PG17 import ChatDB
from app.Redis_DB.ST_DB_Redis import (
    redis_init, Redis, store_log_redis, get_logs_before,
    make_redis_log_id)
from app.LLM_Agents.agentslib import LogAgent
import logfire
import os
from fastapi import FastAPI, BackgroundTasks, Depends, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, RedirectResponse, StreamingResponse, JSONResponse
import json
from pathlib import Path
import asyncio
from app.schemas import ChatMessage, ChatDeleteRequest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage, ModelRequest, ModelResponse,
    TextPart, UserPromptPart)
from typing import Annotated, AsyncGenerator
from app.utilslib import (log_to_json, send_to_discord,
                      format_trigger_log, generate_chat_id)
from datetime import timedelta



######################################### LOG CONFIG ##############################################

# Configure logfire telemetry — only sends data if token is present
logfire.configure(send_to_logfire='if-token-present')

logfire.instrument_pydantic_ai()
logfire.instrument_redis()


######################################### AI LOG AGENT CONFIG #####################################
# Initiate the log agent:
log_agent = LogAgent()

# log agent context decorator
# Define system prompt for LLM agent — used later in `ask_AI` funct
@log_agent.agent.system_prompt
def explain_log(ctx: RunContext[str]) -> str:
    instr_prompt = "Analyze main_log, as instructed in system prompt. Use earlier_logs if useful."
    return f"{instr_prompt}: {ctx.deps}"


######################################### FASTAPI CONFIG ##########################################

# Set up application lifespan: attach databases connections
@asynccontextmanager
async def lifespan(_app: FastAPI):

    db = await ChatDB.connect()
    redis_db = await redis_init()
    try:
        yield {'db': db, 'redis_db': redis_db}
    finally:
        await db.close()
        if not redis_db :
        # if connection was established
            await redis_db.close()


app = FastAPI(lifespan = lifespan)

app.mount("/static", StaticFiles(directory = "../Mock_UI"), name = "static")

# Enable FastAPI instrumentation to use logfire
logfire.instrument_fastapi(app)


######################################### SIMPLIFIED SENT TO UI ###################################

@app.get('/')
async def index() -> RedirectResponse:
    """Redirect root to the main chat UI mockup html page."""
    return RedirectResponse(url = "/static/chat_app.html")


@app.get('/chat_app.ts')
async def main_ts() -> RedirectResponse:
    """Redirect to raw TypeScript frontend file."""
    return RedirectResponse(url = "/static/chat_app.ts")

######################################### Database Dependencies ######################################

# POSTGRESQL17: Chat converstions and main DB:
async def get_db(request: Request) -> ChatDB:
    return request.state.db

# Redis: temp logs (TTL 15min) for Agent:
async def get_redis_db(request: Request) -> Redis:
    return request.state.redis_db

######################################################################################################

@app.get('/chat/')
async def get_chat(db: ChatDB = Depends(get_db)) -> Response:
    msgs = await db.get_messages()
    return Response(
        json.dumps([to_chat_message(msg) for msg in msgs]),
        media_type='application/json',
    )


def to_chat_message(input_msg: ModelMessage) -> ChatMessage:
    if isinstance(input_msg, ModelRequest):
        for part in input_msg.parts:
            if isinstance(part, UserPromptPart):
                assert isinstance(part.content, str)
                
                return {
                    'role': 'user',
                    'timestamp': part.timestamp.isoformat(),
                    'content': part.content,
                    'chatId': getattr(part, 'chat_id', None)  # Get chat_id if it exists
                }
        
    elif isinstance(input_msg, ModelResponse):
        msg_text_content = input_msg.parts[0]
        if isinstance(msg_text_content, TextPart):
            later_timestamp = input_msg.timestamp + timedelta(seconds=1)
            # make sure that ModelResponse message is always later

            return {
                'role': 'model',
                'timestamp': later_timestamp.isoformat(),
                'content': msg_text_content.content,
                'chatId': getattr(msg_text_content, 'chat_id', None)  # Get chat_id if it exists
            }
        
    # Raise exception in case model reply is incorrect (wrong reply structure)
    raise UnexpectedModelBehavior(f'Unexpected message type for chat app: {input_msg}')

@app.post('/set_model/')
async def set_model(request: Request):
    data = await request.json()

    model_name = data.get('model')

    if model_name:

        log_agent.change_model(model_name)

        logfire.info(f"Your are using: {log_agent.agent.model}")

        return {"status": "ok", "model": model_name}
    
    return {"status": "error", "reason": "No model specified"}

@app.post('/chat/')
async def post_chat(
    prompt: Annotated[str, Form()],
    db: ChatDB = Depends(get_db)
) -> StreamingResponse:
    """
    Handle chat messages with support for different LLM models.
    Available models: openai, anthropic, deepseek, ollama(local)
    """

    return StreamingResponse(stream_chat_response(prompt, db), media_type='text/plain')

async def stream_chat_response(prompt: str, db: ChatDB) -> AsyncGenerator[bytes, None]:
    """
    Stream chat response from the LLM agent, including the original user message.
    Supports different LLM models through configuration.
    """
    try:
        # Parse the message data
        message_data = json.loads(prompt)
        chat_id = message_data.get('chatId')
        content = message_data.get('content')

        if not content:
            raise ValueError("Message content is required")

        # Send user message with chatId
        user_message = {
            'role': 'user',
            'timestamp': datetime.now(tz = timezone.utc).isoformat(),
            'content': content,
            'chatId': chat_id
        }
        yield json.dumps(user_message).encode('utf-8') + b'\n'

        messages = await db.get_messages()

        try:
            # Stream model response with low-latency updates
            async with log_agent.agent.run_stream(content, message_history=messages, 
                                                  model=log_agent.agent.model) as result:
                async for text in result.stream(debounce_by=0.01):
                    # Create a regular TextPart without chat_id
                    model_response = ModelResponse(
                        parts=[TextPart(text)],
                        timestamp=result.timestamp()
                    )
                    # Add chat_id to the message after conversion
                    response_message = to_chat_message(model_response)
                    response_message['chatId'] = chat_id
                    yield json.dumps(response_message).encode('utf-8') + b'\n'
            
            # Save history to DB with the correct chat_id
            messages_json = result.new_messages_json()
            messages_data = json.loads(messages_json)
            # Add chat_id to each message
            for msg in messages_data:
                msg['chatId'] = chat_id
            await db.add_messages(json.dumps(messages_data))
            
        except Exception as e:
            print(f"An error occurred with model {log_agent.agent.model}: ", e)
            # Return a user-friendly error message
            error_response = ModelResponse(
                parts=[TextPart(f"Sorry, there was an error with the {log_agent.agent.model} "
                                "model. Please try another model or try again later.")],
                timestamp=datetime.now(tz=timezone.utc)
            )
            error_message = to_chat_message(error_response)
            error_message['chatId'] = chat_id
            yield json.dumps(error_message).encode('utf-8') + b'\n'

    except json.JSONDecodeError:
        # If prompt is not a valid JSON, treat it as plain text
        print("Warning: Received plain text prompt instead of JSON")
        yield json.dumps({
            'role': 'user',
            'timestamp': datetime.now(tz=timezone.utc).isoformat(),
            'content': prompt,
            'chatId': None
        }).encode('utf-8') + b'\n'
        
        try:
            async with log_agent.agent.run_stream(prompt, message_history=messages) as result:
                async for text in result.stream(debounce_by=0.01):
                    model_response = ModelResponse(parts=[TextPart(text)], timestamp=result.timestamp())
                    response_message = to_chat_message(model_response)
                    yield json.dumps(response_message).encode('utf-8') + b'\n'
            
            await db.add_messages(result.new_messages_json())
        except Exception as e:
            print(f"Error in fallback mode: {e}")
            error_response = ModelResponse(
                parts=[TextPart("Sorry, an error occurred while processing your message.")],
                timestamp=datetime.now(tz=timezone.utc)
            )
            yield json.dumps(to_chat_message(error_response)).encode('utf-8') + b'\n'


@app.delete("/chat/delete")
async def delete_chats(request: ChatDeleteRequest,
    db: ChatDB = Depends(get_db)) -> JSONResponse:
    """
    Delete chat and its messages by chat ID.
    Expects JSON body e.g.: {"chatId": "chat-123456"}
    Returns information about deleted messages.
    """
    result = await db.delete_messages(request.chatId)
    return JSONResponse(
        status_code=200,
        content=result
    )


######################################### Log Analysis Agent Area ############################

async def process_single_log(
    log_text: str,
    db: ChatDB,
    redis_db: Redis,
    *,
    background_tasks: BackgroundTasks | None = None,
    notify_discord: bool = False,
) -> dict:
    """
    Process a single raw log line end-to-end:
      1. validate / parse
      2. store in Redis (always, with TTL)
      3. if ERROR/WARN -> enqueue LLM analysis as a background task
         (requires a BackgroundTasks instance from the endpoint)
      4. optionally send a Discord notification

    Returns a structured dict describing the outcome (used by both
    /logs/ingest and the /logs/simulate streaming endpoint).
    """
    log_text = log_text.strip()
    if not log_text:
        return {"status": "skipped", "reason": "empty line"}

    validated_log: dict = log_to_json(log_text)
    redis_log_id: str = make_redis_log_id()
    await store_log_redis(redis_db, redis_log_id, validated_log)

    result: dict = {
        "log_id": redis_log_id,
        "raw": log_text,
    }

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

            # Enqueue async LLM analysis if a BackgroundTasks sink is available.
            # For the streaming /logs/simulate endpoint we run it inline via
            # asyncio so the task is tracked within the request lifecycle.
            if background_tasks is not None:
                background_tasks.add_task(ask_and_save, log_bundle, db)
            else:
                asyncio.create_task(ask_and_save(log_bundle, db))

            if notify_discord:
                msg_to_disc = (
                    f"I have got problem with the following log: {log_text}"
                    f"\n Please find proposal solution at http://127.0.0.1:8000/"
                )
                send_to_discord(msg_to_disc)

            result["triggered"] = True
        else:
            result["triggered"] = False
    else:
        result["valid"] = False

        if notify_discord:
            msg_to_disc = (
                f"I have encountered unstructured log:\n {log_text}"
                f"\n Please have a look at http://127.0.0.1:8000/"
            )
            send_to_discord(msg_to_disc)

    return result


async def ask_AI(log_bundle: dict) -> str:
    """
    Process a log bundle with the LLM agent and return messages JSON compatible with add_messages function.
    Each message will be assigned a generated chatId.
    """
    trigger_log: dict = log_bundle['main_log']
    # main log that triggered Agent

    log_parsed = format_trigger_log(trigger_log)
    chat_id = generate_chat_id()



    try:
        AI_reply = await log_agent.agent.run(user_prompt=log_parsed, 
                                             deps=log_bundle)

        # Parse the output to a list of messages (if not already)
        messages_json = AI_reply.new_messages_json()
        try:
            messages = json.loads(messages_json)
        except Exception:
            # fallback: wrap as list if single dict
            messages = [json.loads(messages_json)]

        # Add chatId to each message
        for msg in messages:
            msg['chatId'] = chat_id

        return json.dumps(messages)

    except Exception as e:
        print("An unexpected error occurred: ", e)
        raise


# Calls processing and saves to DB
async def ask_and_save(log_bundle: dict, db: ChatDB):
    model_json_resp = await ask_AI(log_bundle)

    if model_json_resp:
        await db.add_messages(model_json_resp)


# Endpoint to receive and process log data:
@app.post("/logs/ingest")
async def log_receiver(request: Request, background_tasks: BackgroundTasks, 
                       db: ChatDB = Depends(get_db), 
                       redis_db: Redis = Depends(get_redis_db)
                       ):
    
    """
    Receives a log (as string), validates it, and sends it to the LLM agent for analysis in the background. 
    """

    request_body = await request.body() # raw bytes

    log_text: str = json.loads(request_body)  # JSON to string

    result = await process_single_log(
        log_text, db, redis_db,
        background_tasks=background_tasks,
        notify_discord=True,
    )

    return {"status": "received", **{k: v for k, v in result.items() if k != 'raw'}}


# ---------------------------------------------------------------------------
# Built-in log simulator: lets the UI stream test logs through the pipeline
# without running the Mock_Services notebook.
# ---------------------------------------------------------------------------

# Directory bundled inside the image (see Dockerfile). Allows the UI to pick
# a sample file and stream it line by line.
LOGS_DIR = Path(__file__).resolve().parent.parent / "test_logs"
MAX_SIMULATE_LINES = 500  # safety cap to avoid runaway streams


@app.get("/logs/sources")
async def list_log_sources() -> JSONResponse:
    """List bundled sample log files available for simulation."""
    if not LOGS_DIR.is_dir():
        return JSONResponse(status_code=200, content={"sources": []})

    sources = []
    for p in sorted(LOGS_DIR.iterdir()):
        if p.is_file() and p.suffix == ".log":
            # Count lines cheaply (these files are large but we only scan once)
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
    return JSONResponse(status_code=200, content={"sources": sources})


@app.post("/logs/simulate")
async def simulate_logs(
    request: Request,
    db: ChatDB = Depends(get_db),
    redis_db: Redis = Depends(get_redis_db),
) -> StreamingResponse:
    """
    Stream a bundled sample log file through the pipeline line by line.
    Emits one JSON object per line (NDJSON) describing the outcome of each log.

    Body (JSON):
        {
          "source": "deanonymized_server_backup.log",  # file in test_logs/
          "limit": 100,          # optional, default 100
          "delay": 0.0,          # optional seconds between lines, default 0
          "realtime": false      # optional, replay using log timestamps
        }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    source_name = body.get("source", "deanonymized_server_backup.log")
    limit = min(int(body.get("limit", 100)), MAX_SIMULATE_LINES)
    delay = float(body.get("delay", 0.0))
    realtime = bool(body.get("realtime", False))

    source_path = LOGS_DIR / source_name
    if not source_path.is_file():
        async def err():
            yield json.dumps(
                {"error": f"source '{source_name}' not found"}
            ).encode("utf-8") + b"\n"
        return StreamingResponse(err(), media_type="text/plain")

    async def run_simulation() -> AsyncGenerator[bytes, None]:
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

                    # optional timestamp-paced replay
                    if realtime:
                        ts_str = line.split("]")[0].strip("[]")
                        try:
                            cur_ts = datetime.strptime(
                                ts_str, "%Y-%m-%d %H:%M:%S,%f"
                            )
                            if prev_ts is not None:
                                delta = (cur_ts - prev_ts).total_seconds()
                                if 0 < delta < 30:  # cap absurd gaps
                                    await asyncio.sleep(delta)
                            prev_ts = cur_ts
                        except ValueError:
                            prev_ts = None
                    elif delay > 0:
                        await asyncio.sleep(delay)

                    result = await process_single_log(
                        line, db, redis_db, notify_discord=False
                    )
                    sent += 1
                    result["sent"] = sent
                    result["total"] = limit
                    yield json.dumps(result).encode("utf-8") + b"\n"
        except Exception as e:
            yield json.dumps({"error": str(e)}).encode("utf-8") + b"\n"

    return StreamingResponse(run_simulation(), media_type="text/plain")

######################################### RUN #######################################################

if __name__ == '__main__':
    import uvicorn

    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=True)

    # in cmd (from project root): uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
