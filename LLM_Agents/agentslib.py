

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from typing import Dict, Union

load_dotenv()

DEFAULT_MODEL = 'openai'
LOCAL_LLM = 'gemma2:2b'
LOCAL_MODEL_URL = 'http://localhost:11434/v1'
SYSTEM_PROMPT = (
    "You are a DevOps expert. Your task is to analyze log messages received from Kafka and provide concise, "
    "actionable explanations or solutions for any detected issues. Focus on identifying errors, warnings, and "
    "abnormal patterns."
    )


class LogAgent:
    """
    Main AI Log Agent for analyzing Kafka log messages using various LLM providers.
    """

    def __init__(self):
        self.model_configs: Dict[str, Union[str, OpenAIModel]] = {
            # Avaliable models:
            # https://ai.pydantic.dev/api/models/base/
            
            'openai': 'gpt-3.5-turbo',
            'openai-4': 'openai:gpt-4',
            'anthropic': 'anthropic:claude-3-5-sonnet-latest',
            'deepseek': 'deepseek-ai:deepseek-chat',
            'ollama': OpenAIModel(
                model_name=LOCAL_LLM,
                provider=OpenAIProvider(base_url=LOCAL_MODEL_URL)
            )
        }

        self.current_model_name = DEFAULT_MODEL
        
        self.agent = Agent(
            model=self.model_configs[DEFAULT_MODEL],
            # initiate Agent wtih default LLM
            deps_type=str,
            system_prompt=SYSTEM_PROMPT
            )

    def change_model(self, model_name: str) -> None:
        """
        Change the underlying model used by the agent.
        Falls back to the default if the requested model is unknown.
        """
        
        # Changes model to selected model directly in Agent, if not found, sets DEFAULT_MODEL:
        selected_model = self.model_configs.get(model_name, self.model_configs[DEFAULT_MODEL])
        # check keys, if not found return default value
        
        self.current_model_name = model_name if model_name in self.model_configs else DEFAULT_MODEL
        # informational return model key name, e.g.: 'openai'

        self.agent.model = selected_model
        # assing proper technical LLM name, e.g.: 'gpt-3.5-turbo'

        
