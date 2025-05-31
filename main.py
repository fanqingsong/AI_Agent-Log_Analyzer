
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from Postgres_DB.DB_PG17 import ChatDB
from Redis_DB.ST_DB_Redis import redis_init, Redis, test_redis_conn
from LLM_Agents.agentslib import log_agent
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


# Configure logfire telemetry — only sends data if token is present
logfire.configure(send_to_logfire='if-token-present')

logfire.instrument_pydantic_ai()


# log agent context decorator
# Define system prompt for LLM agent — used later in `ask_AI` funct
@log_agent.system_prompt
def explain_log(ctx: RunContext[str]) -> str:
    return f"Analyze this log: {ctx.deps}"

# Set up application lifespan: attach database connection
@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = await ChatDB.connect()
    try:
        yield {'db': db}
    finally:
        await db.close()

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
async def get_redis_db() -> Redis|None:
    print("HERE!")
    redis_client_db = await redis_init()

    if await test_redis_conn(redis_client_db):
        return redis_client_db
        # return rdy to go Redis Client DB
    else:
        return None

######################################################################################################

@app.get('/chat/')
async def get_chat(db: ChatDB = Depends(get_db)) -> Response:
    msgs = await db.get_messages()
    return Response(
        b'\n'.join(json.dumps(to_chat_message(msg)).encode('utf-8') for msg in msgs),
        media_type='text/plain',
    )


def to_chat_message(input_msg: ModelMessage) -> ChatMessage:

    # get the text content to/from model message
    msg_text_content = input_msg.parts[0]

    if isinstance(input_msg, ModelRequest):
        
        if isinstance(msg_text_content, UserPromptPart):
            assert isinstance(msg_text_content.content, str)
            return {
                'role': 'user',
                'timestamp': msg_text_content.timestamp.isoformat(),
                'content': msg_text_content.content,
            }
    elif isinstance(input_msg, ModelResponse):
        if isinstance(msg_text_content, TextPart):
            return {
                'role': 'model',
                'timestamp': input_msg.timestamp.isoformat(),
                'content': msg_text_content.content,
            }
        
    # Fallback: treat as model response if structure is unclear
    return {
        'role': 'model',
        'timestamp': msg_text_content.timestamp.isoformat(),
        'content': msg_text_content.content,
    }
    
    # # Reports unexpected behaviour but this is not suprising
    # raise UnexpectedModelBehavior(f'Unexpected message type for chat app: {msg_text_content}')


async def stream_chat_response(prompt: str, db: ChatDB) -> AsyncGenerator[bytes, None]:
    """
    Stream chat response from the LLM agent, including the original user message.
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
        # Stream model response with low-latency updates
        async with log_agent.run_stream(prompt, message_history = messages) as result:
            async for text in result.stream(debounce_by = 0.01):

                model_response = ModelResponse(parts = [TextPart(text)], timestamp = result.timestamp())

                yield json.dumps(to_chat_message(model_response)).encode('utf-8') + b'\n'
        
        # updated chat history to DB
        await db.add_messages(result.new_messages_json())
        
    except Exception as e:
        print("An error occured: ", e)


@app.post('/chat/')
async def post_chat(prompt: Annotated[str, Form()], db: ChatDB = Depends(get_db)
# max lenght added to prevent token overburn
                    ) -> StreamingResponse:
    return StreamingResponse(stream_chat_response(prompt, db), media_type='text/plain')

######################################### Log Analysis Agent Area ############################

# async initial process log 
async def ask_AI(log) -> bytes:
    try:
        AI_reply = await log_agent.run('Use system prompt', deps=log)

        return AI_reply.new_messages_json()

    except Exception as e:
        print("An unextepcet error occurred: ", e)
        raise 


# Calls processing and saves to DB
async def ask_and_save(log, db: ChatDB):
    model_json_resp = await ask_AI(log)

    if model_json_resp:
        await db.add_messages(model_json_resp)


# Endpoint to receive and process log data:
@app.post("/logs/ingest")
async def log_receiver(request: Request, background_tasks: BackgroundTasks, db: ChatDB = Depends(get_db)):
    
    """
    Receives a log (as string), validates it, and sends it to the LLM agent for analysis in the background. 

    doc for background_tasks: https://fastapi.tiangolo.com/tutorial/background-tasks/#dependency-injection
    """

    request_body = await request.body() # raw bytes

    log_text: str = json.loads(request_body)  # JSON to string

    validated_log: dict = log_to_json(log_text) # log vaidation

    if validated_log.get('valid_log'):
    # log is valid, else get returns None

        unpacked_log = validated_log['valid_log'] # extract log content

        if unpacked_log.get('level') in ('ERROR', 'WARN'):
        # check log lvl (must be at least 'WARN')

            # sent to Agent and DB
            background_tasks.add_task(ask_and_save, unpacked_log, db) 

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

# Endpoint to receive and process log data:
@app.post("/testendpoint")
async def test_me(request: Request, 
                  db: ChatDB = Depends(get_db), 
                  redis_db: Redis = Depends(get_redis_db)):
    return {"status": "received"}


######################################### RUN #######################################################

if __name__ == '__main__':
    import uvicorn

    uvicorn.run("main:app", host = "127.0.0.1", port = 8000, reload = True)



    # in cmd: uvicorn main:app --host 127.0.0.1 --port 8000 --reload
    # Remember to Run Docker mainDBcontainer17 first!



