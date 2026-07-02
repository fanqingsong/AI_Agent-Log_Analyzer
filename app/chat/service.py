"""Chat business logic: message conversion and streaming LLM responses."""

import json
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import logfire
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart,
)

from app.chat.repository import ChatDB
from app.chat.schemas import ChatMessage
from app.llm.agent import LogAgent


def to_chat_message(input_msg: ModelMessage) -> ChatMessage:
    """Convert a PydanticAI message into the dict format the browser expects."""
    if isinstance(input_msg, ModelRequest):
        for part in input_msg.parts:
            if isinstance(part, UserPromptPart):
                assert isinstance(part.content, str)
                return {
                    'role': 'user',
                    'timestamp': part.timestamp.isoformat(),
                    'content': part.content,
                    'chatId': getattr(part, 'chat_id', None)
                }

    elif isinstance(input_msg, ModelResponse):
        msg_text_content = input_msg.parts[0]
        if isinstance(msg_text_content, TextPart):
            # Ensure the ModelResponse timestamp is always later than the request.
            later_timestamp = input_msg.timestamp + timedelta(seconds=1)
            return {
                'role': 'model',
                'timestamp': later_timestamp.isoformat(),
                'content': msg_text_content.content,
                'chatId': getattr(msg_text_content, 'chat_id', None)
            }

    raise UnexpectedModelBehavior(f'Unexpected message type for chat app: {input_msg}')


async def stream_chat_response(
    prompt: str, db: ChatDB, log_agent: LogAgent
) -> AsyncGenerator[bytes, None]:
    """Stream a chat response from the LLM agent.

    Accepts either a JSON string ``{"content": ..., "chatId": ...}`` or a
    plain-text prompt (fallback). Emits NDJSON lines the browser renders
    incrementally.
    """
    try:
        message_data = json.loads(prompt)
        chat_id = message_data.get('chatId')
        content = message_data.get('content')

        if not content:
            raise ValueError("Message content is required")

        user_message = {
            'role': 'user',
            'timestamp': datetime.now(tz=timezone.utc).isoformat(),
            'content': content,
            'chatId': chat_id
        }
        yield json.dumps(user_message).encode('utf-8') + b'\n'

        messages = await db.get_messages()

        try:
            async with log_agent.agent.run_stream(
                content, message_history=messages, model=log_agent.agent.model
            ) as result:
                async for text in result.stream(debounce_by=0.01):
                    model_response = ModelResponse(
                        parts=[TextPart(text)],
                        timestamp=result.timestamp()
                    )
                    response_message = to_chat_message(model_response)
                    response_message['chatId'] = chat_id
                    yield json.dumps(response_message).encode('utf-8') + b'\n'

            messages_json = result.new_messages_json()
            messages_data = json.loads(messages_json)
            for msg in messages_data:
                msg['chatId'] = chat_id
            await db.add_messages(json.dumps(messages_data))

        except Exception as e:
            print(f"An error occurred with model {log_agent.agent.model}: ", e)
            error_response = ModelResponse(
                parts=[TextPart(
                    f"Sorry, there was an error with the {log_agent.agent.model} "
                    "model. Please try another model or try again later."
                )],
                timestamp=datetime.now(tz=timezone.utc)
            )
            error_message = to_chat_message(error_response)
            error_message['chatId'] = chat_id
            yield json.dumps(error_message).encode('utf-8') + b'\n'

    except json.JSONDecodeError:
        # Fallback: treat prompt as plain text.
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
                    model_response = ModelResponse(
                        parts=[TextPart(text)], timestamp=result.timestamp()
                    )
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
