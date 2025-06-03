# Guard rail?:
# https://medium.com/data-science/safeguarding-llms-with-guardrails-4f5d9f57cff2

from pydantic_ai import Agent
from dotenv import load_dotenv
from typing import Dict

load_dotenv()

#####################################################################################
# Available models configuration
MODEL_CONFIGS: Dict[str, str] = {
    'openai': 'gpt-3.5-turbo',
    # TC(To change): change key to more despritvie 'openai-3.5-turbo'
    'openai-4': 'openai:gpt-4',
    'anthropic': 'anthropic:claude-3-sonnet',
    'deepseek': 'deepseek-ai:deepseek-chat',
    'ollama': 'ollama:llama2'  # Requires local Ollama installation
}

# Default model
DEFAULT_MODEL = 'openai'
# TC(To change): change key to more despritvie 'openai-3.5-turbo'
current_model = MODEL_CONFIGS[DEFAULT_MODEL]

log_agent = Agent(
    model = current_model,
    deps_type = str,
    # describe context type  
    system_prompt = (
        "You are a DevOps expert. Your task is to analyze log messages received from Kafka and provide concise, "
        "actionable explanations or solutions for any detected issues. Focus on identifying errors, warnings, and "
        "abnormal patterns." 
        )
    )


def configure_model(model_name: str) -> None:
    """
    Configure the agent to use a specific model.
    Available models: openai, openai-4, anthropic, deepseek, ollama
    """
    global current_model
    ## !! Important
    # TC(To change): Avoid global var - may trigger some people - find other solution 

    if model_name in MODEL_CONFIGS:
        current_model = MODEL_CONFIGS[model_name]
        log_agent.model = current_model
    else:
        # Fallback to default model if unknown model is requested
        current_model = MODEL_CONFIGS[DEFAULT_MODEL]
        log_agent.model = current_model
