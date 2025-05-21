# Guard rail?:
# https://medium.com/data-science/safeguarding-llms-with-guardrails-4f5d9f57cff2

from pydantic_ai import Agent, RunContext
from dotenv import load_dotenv

load_dotenv()

# # # sample log:
# log1 = """'level': 'ERROR', 'message': "[ControllerApis nodeId=1] Unexpected error handling request RequestHeader(apiKey=FETCH, apiVersion=15, clientId=raft-client-4, correlationId=1, headerVersion=2) -- FetchRequestData(clusterId='9n09PkoVRJSCcZemHAmm6g', replicaId=-1, replicaState=ReplicaState(replicaId=4, replicaEpoch=-1), maxWaitMs=500, minBytes=0, maxBytes=8388608, isolationLevel=0, sessionId=0, sessionEpoch=-1, topics=[FetchTopic(topic='', topicId=AAAAAAAAAAAAAAAAAAAAAQ, partitions=[FetchPartition(partition=0, currentLeaderEpoch=4372, fetchOffset=125835950, lastFetchedEpoch=4372, logStartOffset=-1, partitionMaxBytes=0)])], forgottenTopicsData=[], rackId='') with context RequestContext(header=RequestHeader(apiKey=FETCH, apiVersion=15, clientId=raft-client-4, correlationId=1, headerVersion=2), connectionId='conn-redacted', clientAddress=ip-redacted, principal=User:anon-user listenerName=ListenerName(CONTROLLER_SSL), securityProtocol=SSL, clientInformation=ClientInformation(softwareName=apache-kafka-java, softwareVersion=3.5.1), fromPrivilegedListener=false, principalSerde=Optional[org.apache.kafka.common.security.authenticator.DefaultKafkaPrincipalBuilder@2d516efa]) (kafka.server.ControllerApis)"}
# org.apache.kafka.common.errors.AuthorizerNotReadyException"""



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

@log_agent.system_prompt
def explain_log(ctx: RunContext[str]) -> str:
    return f"Analyze this log: {ctx.deps}"

# result = log_agent.run_sync('Use system prompt', deps = log1)

# print(result.output)

# #####################################################################################

# class KafkaLogAgent:
#     def __init__(self, model: str):
#         self.log_agent = Agent(
#             model,
#             deps_type=str,
#             system_prompt="""You are a DevOps expert. Your task is to analyze log messages received from Kafka and provide concise, 
#                             actionable explanations or solutions for any detected issues. Focus on identifying errors, warnings, and 
#                             abnormal patterns."""
#         )
#         self._register_prompt()

#     def _register_prompt(self):
#         @self.log_agent.system_prompt
#         def explain_log(ctx: RunContext[str]) -> str:
#             return f"Analyze this log: {ctx.deps}"

#     def analyze(self, log: str):
#         return self.log_agent.run_sync('Use system prompt', deps=log)

# # Usage:
# log_agent = KafkaLogAgent(model)