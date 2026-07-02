"""Shared LLM agent used by both the chat and logs services.

`LogAgent` wraps PydanticAI's `Agent` and supports hot-swapping the
underlying model at runtime across OpenAI, Anthropic, DeepSeek, Ollama
and Zhipu (GLM).
"""

from typing import Dict, Union

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from app import config

SYSTEM_PROMPT = (
    "You are a DevOps expert. Your task is to analyze log messages received from Kafka and provide concise, "
    "actionable explanations or solutions for any detected issues. Focus on identifying errors, warnings, and "
    "abnormal patterns."
)


class LogAgent:
    """AI Log Agent for analyzing log messages using various LLM providers."""

    def __init__(self):
        self.model_configs: Dict[str, Union[str, OpenAIModel]] = {
            # Available models: https://ai.pydantic.dev/api/models/base/
            'openai': 'gpt-3.5-turbo',
            'openai-4': 'openai:gpt-4',
            'anthropic': 'anthropic:claude-3-5-sonnet-latest',
            'deepseek': 'deepseek-ai:deepseek-chat',
            'ollama': OpenAIModel(
                model_name=config.LOCAL_LLM,
                provider=OpenAIProvider(base_url=config.LOCAL_MODEL_URL)
            ),
            # Zhipu AI (GLM) — OpenAI-compatible API.
            'zhipu': OpenAIModel(
                model_name=config.ZHIPU_MODEL,
                provider=OpenAIProvider(
                    base_url=config.ZHIPU_BASE_URL,
                    api_key=config.ZHIPU_API_KEY,
                )
            )
        }

        # If the configured DEFAULT_MODEL has no usable credential, fall back
        # to the first provider that does (e.g. zhipu when only ZHIPU_API_KEY
        # is set).
        chosen = config.DEFAULT_MODEL
        if chosen not in self.model_configs:
            chosen = 'zhipu' if config.ZHIPU_API_KEY else 'openai'

        self.current_model_name = chosen

        self.agent = Agent(
            model=self.model_configs[chosen],
            deps_type=str,
            system_prompt=SYSTEM_PROMPT
        )

    def change_model(self, model_name: str) -> None:
        """Change the underlying model used by the agent.

        Falls back to the default if the requested model is unknown.
        """
        selected_model = self.model_configs.get(
            model_name, self.model_configs[config.DEFAULT_MODEL]
        )
        self.current_model_name = (
            model_name if model_name in self.model_configs else config.DEFAULT_MODEL
        )
        self.agent.model = selected_model
