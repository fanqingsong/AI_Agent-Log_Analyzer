# Based on:
# https://ai.pydantic.dev/examples/chat-app/#example-code

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import asyncio
# async needed for direct use of connection to db (probably)

import logfire

from fastapi import FastAPI, Form, Depends, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, StreamingResponse, RedirectResponse

from schemas import ChatMessage, MockKafkaLogEntry

from typing import Annotated, AsyncGenerator
from pathlib import Path
from pydantic_ai import RunContext
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from DBlib import ChatDB
from utilslib import log_to_json
from LLM_Agents.agentslib import log_agent


# temp:
from pydantic import BaseModel

# 'if-token-present' means nothing will be sent (and the example will work) if you don't have logfire configured
logfire.configure(send_to_logfire='if-token-present')
logfire.instrument_pydantic_ai()
# still needed for db apparently

############### AGENT DEF ###############
# Temp unused
model = 'openai:gpt-3.5-turbo'
# 'openai:gpt-4o'

agent = Agent(model)
#########################################



THIS_DIR = Path(__file__).parent
# still needed for db apparently

@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with ChatDB.connect() as db:
        yield {'db': db}


app = FastAPI(lifespan = lifespan)

app.mount("/static", StaticFiles(directory = "Mock_UI"), name = "static")


logfire.instrument_fastapi(app)
# still needed for db apparently

########################### SIMPLIEFIED SENT TO UI #################################################

@app.get('/')
async def index() -> FileResponse:
    """Get the UI html page."""
    return RedirectResponse(url = "/static/chat_app.html")


@app.get('/chat_app.ts')
async def main_ts() -> FileResponse:
    """Get the raw typescript code."""
    return RedirectResponse(url = "/static/chat_app.ts")

####################################################################################################


async def get_db(request: Request) -> ChatDB:
    return request.state.db


@app.get('/chat/')
async def get_chat(database: ChatDB = Depends(get_db)) -> Response:
    msgs = await database.get_messages()
    return Response(
        b'\n'.join(json.dumps(to_chat_message(m)).encode('utf-8') for m in msgs),
        media_type='text/plain',
    )


def to_chat_message(m: ModelMessage) -> ChatMessage:

    first_part = m.parts[0]

    if isinstance(m, ModelRequest):
        if isinstance(first_part, UserPromptPart):
            assert isinstance(first_part.content, str)
            return {
                'role': 'user',
                'timestamp': first_part.timestamp.isoformat(),
                'content': first_part.content,
            }
    elif isinstance(m, ModelResponse):
        if isinstance(first_part, TextPart):
            return {
                'role': 'model',
                'timestamp': m.timestamp.isoformat(),
                'content': first_part.content,
            }
        
    raise UnexpectedModelBehavior(f'Unexpected message type for chat app: {m}')



async def stream_chat_response(prompt: str, db: ChatDB) -> AsyncGenerator[bytes, None]:

    yield json.dumps(
        {
        'role': 'user',
        'timestamp': datetime.now(tz = timezone.utc).isoformat(),
        'content': prompt,
        }
        ).encode('utf-8') + b'\n'

    messages = await db.get_messages()

    try:
        async with agent.run_stream(prompt, message_history = messages) as result:
            async for text in result.stream(debounce_by = 0.01):

                model_response = ModelResponse(parts = [TextPart(text)], timestamp = result.timestamp())

                yield json.dumps(to_chat_message(model_response)).encode('utf-8') + b'\n'

        await db.add_messages(result.new_messages_json())
        
    except Exception as e:
        print("An error occured: ", e)


@app.post('/chat/')
async def post_chat(prompt: Annotated[str, Form()], database: ChatDB = Depends(get_db)
                    ) -> StreamingResponse:

    return StreamingResponse(stream_chat_response(prompt, database), media_type='text/plain')







# # THIS IS WORKING!
# ## pure sync with Json model and response:
# def process_log_async(log):

#     try:
#         result = log_agent.run_sync('Use system prompt', deps = log)

#         @log_agent.system_prompt
#         def explain_log(ctx: RunContext[str]) -> str:
#             return f"Analyze this log: {ctx.deps}"

#         model_response = ModelResponse(parts = [TextPart(result.output)], timestamp = datetime.now())

#         rdy_json = json.dumps(to_chat_message(model_response)).encode('utf-8') + b'\n'

#         print(rdy_json)

#         return rdy_json
    
#     except Exception as e:
#         print("An error occured: ", e)

#         return None

# This is now async since the call is actually async
async def process_log_async(log) -> bytes:
    try:
        result = await log_agent.run('Use system prompt', deps=log)  # await the real method

        @log_agent.system_prompt
        def explain_log(ctx: RunContext[str]) -> str:
            return f"Analyze this log: {ctx.deps}"

        model_response = ModelResponse(parts=[TextPart(result.output)], timestamp=datetime.now())

        rdy_json = json.dumps(to_chat_message(model_response)).encode('utf-8') + b'\n'

        print(rdy_json)
        return rdy_json

    except Exception as e:
        print("An error occurred: ", e)
        return None




# # Async wrapper that calls sync processing and saves to DB
# async def process_log_and_store(log, db: ChatDB):

#     rdy_json = process_log_sync(log)

#     if rdy_json:
#         await db.add_messages(rdy_json)


# # Async wrapper that calls sync processing and saves to DB
# Combines processing + DB store
async def process_log_and_store(log, db: ChatDB):
    rdy_json = await process_log_async(log)
    if rdy_json:
        await db.add_messages(rdy_json)



# Endpoint to receive and process log data:
@app.post("/logs/ingest")
async def log_receiver(request: Request, background_tasks: BackgroundTasks, db: ChatDB = Depends(get_db)):

    request_body = await request.body() # raw bytes

    log_text: str = json.loads(request_body)  # JSON to string

    validated_log: dict = log_to_json(log_text) # log vaidation

    unpacked_log = validated_log['valid_log']

    print(unpacked_log)

    background_tasks.add_task(process_log_and_store, unpacked_log, db)

    return {"status": "received"}



# doc:
# https://fastapi.tiangolo.com/tutorial/background-tasks/#dependency-injection

# ##########################################################################################
# # working TEMPLATE to save things to db:
#
# @app.post('/add_message')
# async def add_message_endpoint(
#     request: Request,  
#     db: ChatDB = Depends(get_db)
#     ):

#     print("fn activated!")

#     raw_body = await request.body()
    
#     log_text: str = raw_body.decode("utf-8")

#     # Prepare your message in the format expected by add_messages
#     # For example, if add_messages expects bytes:
#     await db.add_messages(log_text)

#     # # add message directly
#     # await add_message_directly()

#     return {"status": "ok", "message": "Message added"}
# ##########################################################################################

# # Connect directly to database:
# #########################################################################################
# # working TEMPLATE to save things to db:
# async def add_message_directly():
#     async with ChatDB.connect() as db:
#         await db.add_messages("Hello, this is a new message2!")
# #########################################################################################


if __name__ == '__main__':
    import uvicorn

    uvicorn.run("main:app", host = "127.0.0.1", port = 8000, reload = True)
    # In cmd: uvicorn main:app --host 127.0.0.1 --port 8000 --reload



    
######################################################################
# LUZNE NOTKI 
# otrzymaj loga
# obrób go
# jesli jest własciwy to:
    # jeśli jest error to wyśli go do LLMa
    # jeśli jest error lub normalny to zrob embeding w VDB
# odbierz odpowiedź od LLMA i streamuj ją na /Chat endpoint
# zapisz odpowiedź do bazy danych

# https://fastapi.tiangolo.com/tutorial/background-tasks/#dependency-injection
# https://ai.pydantic.dev/agents/#introduction
######################################################################