

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from typing import Dict, Union

load_dotenv()

class LogAgent:
    """
    Main AI Log Agent for analyzing Kafka log messages using various LLM providers.
    """

    def __init__(self):
        self.model_configs: Dict[str, Union[str, OpenAIModel]] = {
            'openai': 'gpt-3.5-turbo',
            'openai-4': 'openai:gpt-4',
            'anthropic': 'anthropic:claude-3-sonnet',
            'deepseek': 'deepseek-ai:deepseek-chat',
            'ollama': OpenAIModel(
                model_name='gemma2:2b',
                provider=OpenAIProvider(base_url='http://localhost:11434/v1')
            )
        }

        self.default_model_name = 'openai'
        
        self.agent = Agent(
            model=self.model_configs[self.default_model_name],
            deps_type=str,
            system_prompt=(
                "You are a DevOps expert. Your task is to analyze log messages received from Kafka and provide concise, "
                "actionable explanations or solutions for any detected issues. Focus on identifying errors, warnings, and "
                "abnormal patterns."
            )
        )

    def configure_model(self, model_name: str) -> None:
        """
        Change the underlying model used by the agent.
        Falls back to the default if the requested model is unknown.
        """
        selected_model = self.model_configs.get(model_name, self.model_configs[self.default_model_name])
        self.agent.model = selected_model
