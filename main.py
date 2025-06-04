from contextlib import asynccontextmanager
from datetime import datetime, timezone
from Postgres_DB.DB_PG17 import ChatDB
from Redis_DB.ST_DB_Redis import (
    redis_init, Redis, store_log_redis, get_logs_before, make_redis_log_id)
from LLM_Agents.agentslib import log_agent, configure_model
import logfire
from fastapi import FastAPI, BackgroundTasks, Depends, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, RedirectResponse, StreamingResponse
import json
from schemas import ChatMessage
from pydantic_ai import RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage, ModelRequest, ModelResponse,
    TextPart,
    UserPromptPart,
    )
from typing import Annotated, AsyncGenerator
from utilslib import log_to_json, send_to_discord
from datetime import timedelta

# Configure logfire telemetry — only sends data if token is present
logfire.configure(send_to_logfire='if-token-present')

logfire.instrument_pydantic_ai()
logfire.instrument_redis()

# log agent context decorator
# Define system prompt for LLM agent — used later in `ask_AI` funct
@log_agent.system_prompt
def explain_log(ctx: RunContext[str]) -> str:
    instr_prompt = "Analyze main_log, as instructed in system prompt. Use earlier_logs if useful."
    return f"{instr_prompt}: {ctx.deps}"

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

app.mount("/static", StaticFiles(directory = "Mock_UI"), name = "static")

# Enable FastAPI instrumentation to use logfire
logfire.instrument_fastapi(app)


######################################### SIMPLIFIED SENT TO UI ######################################

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
            }
        
    # Raise exception in case model reply is incorrect (wrong reply structure)
    raise UnexpectedModelBehavior(f'Unexpected message type for chat app: {input_msg}')


@app.post('/chat/')
async def post_chat(
    prompt: Annotated[str, Form()],
    model: Annotated[str, Form()] = "openai",  # Default to OpenAI if not specified
    db: ChatDB = Depends(get_db)
) -> StreamingResponse:
    """
    Handle chat messages with support for different LLM models.
    Available models: openai, anthropic, deepseek, ollama
    """
    return StreamingResponse(stream_chat_response(prompt, db, model), media_type='text/plain')

async def stream_chat_response(prompt: str, db: ChatDB, model: str = "openai") -> AsyncGenerator[bytes, None]:
    """
    Stream chat response from the LLM agent, including the original user message.
    Supports different LLM models through configuration.
    """
    yield json.dumps(
        {
        'role': 'user',
        'timestamp': datetime.now(tz = timezone.utc).isoformat(),
        'content': prompt,
        }
        ).encode('utf-8') + b'\n'

    messages = await db.get_messages()

    try:
        # Configure the agent based on selected model
        configure_model(model)
        
        # Stream model response with low-latency updates
        async with log_agent.run_stream(prompt, message_history = messages) as result:
            async for text in result.stream(debounce_by = 0.01):
                model_response = ModelResponse(parts = [TextPart(text)], timestamp = result.timestamp())
                yield json.dumps(to_chat_message(model_response)).encode('utf-8') + b'\n'
        
        # updated chat history to DB
        await db.add_messages(result.new_messages_json())
        
    except Exception as e:
        print(f"An error occurred with model {model}: ", e)
        # Return a user-friendly error message
        error_response = ModelResponse(
            parts=[TextPart(f"Sorry, there was an error with the {model} model. Please try another model or try again later.")],
            timestamp=datetime.now(tz=timezone.utc)
        )
        yield json.dumps(to_chat_message(error_response)).encode('utf-8') + b'\n'

######################################### Log Analysis Agent Area ############################

# async initial process log 
async def ask_AI(log_bundle: dict) -> bytes:
    

    trigger_log: dict = log_bundle['main_log']
    # main log that triggered Agent

#--------------------------------------------------------------------------------------------------
# To be transfered to utillibs mod (later):
    warning_level = trigger_log['level']

    if warning_level == "ERROR":
        signal_icon: str = "🔥"
    else:
        signal_icon: str = "⚠️"


    log_parsed: str = f"""
    Provided log message:

    **🕒 Timestamp**: {trigger_log['timestamp']}
    **{signal_icon} Level**: {trigger_log['level']}
    **💬 Message**: {trigger_log['component']} {trigger_log['message']} {trigger_log['source']}
    """


#--------------------------------------------------------------------------------------------------

    try:
        AI_reply = await log_agent.run(user_prompt=log_parsed, 
                                       deps=log_bundle)

        return AI_reply.new_messages_json()

    except Exception as e:
        print("An unextepcet error occurred: ", e)
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

    doc for background_tasks: https://fastapi.tiangolo.com/tutorial/background-tasks/#dependency-injection
    """

    request_body = await request.body() # raw bytes

    log_text: str = json.loads(request_body)  # JSON to string

    validated_log: dict = log_to_json(log_text) # log vaidation

    redis_log_id: str = make_redis_log_id()

    await store_log_redis(redis_db, redis_log_id, validated_log) # add to redis db

    if validated_log.get('valid_log'):
    # log is valid, else get returns None

        unpacked_log = validated_log['valid_log'] # extract log content

        if unpacked_log.get('level') in ('ERROR', 'WARN'):
        # check log lvl (must be at least 'WARN')

            # TODO(Optional):
            # trim what goes to agent currently to much redundant data
            # eliminate repeating logs
            
            earlier_logs: list = await get_logs_before(redis_db, redis_log_id)
            # gather 5 logs before

            log_bundle: dict = {'main_log': unpacked_log, 'earlier_logs': earlier_logs}

            # sent to Agent and DB
            background_tasks.add_task(ask_and_save, log_bundle, db) 

            # sent to Discord:
            msg_to_disc = f"""I have got problem with the following log: {log_text}
            \n Please find proposal solution at http://127.0.0.1:8000/"""

            send_to_discord(msg_to_disc)

    else:
        unpacked_log = validated_log['invalid_log'] # extract core log content

        msg_to_disc = f"""I have encountered unstructured log:\n {log_text}
        \n Please have a look at http://127.0.0.1:8000/"""

        send_to_discord(msg_to_disc)
        
        # TODO(Optional):
        # Add log IDs (case ID)
        # CHECK if the log is in DB (need new table)
        # if not then sent is to Agent
        # Agent inform user about new unstructured log (e.g. via mail, or via mail and chat)
        # decides if the log can be ignored, if yes, then save new log to db

    return {"status": "received"}

######################################### RUN #######################################################

if __name__ == '__main__':
    import uvicorn

    uvicorn.run("main:app", host = "127.0.0.1", port = 8000, reload = True)

    # in cmd: uvicorn main:app --host 127.0.0.1 --port 8000 --reload
    # Remember to Run Docker mainDBcontainer17 first!

