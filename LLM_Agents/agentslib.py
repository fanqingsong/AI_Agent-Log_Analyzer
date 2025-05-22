# Guard rail?:
# https://medium.com/data-science/safeguarding-llms-with-guardrails-4f5d9f57cff2

from pydantic_ai import Agent
from dotenv import load_dotenv

load_dotenv()


#####################################################################################
# model = 'openai:gpt-4o'
model = 'gpt-3.5-turbo'


log_agent = Agent(
    model = model,
    deps_type = str,
    # describe context type  
    system_prompt = """You are a DevOps expert. Your task is to analyze log messages received from Kafka and provide concise, 
                    actionable explanations or solutions for any detected issues. Focus on identifying errors, warnings, and 
                    abnormal patterns."""  
    )
