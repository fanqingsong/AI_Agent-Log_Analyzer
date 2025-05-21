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