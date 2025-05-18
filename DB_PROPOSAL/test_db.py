import psycopg
from pydantic import BaseModel



conn = psycopg.connect("postgresql://user:pass@localhost/db", autocommit=True)

class Msg(BaseModel):
    user_message: str
    llm_response: str

# @app.post("/store")
# def store(msg: Msg):
#     with conn.cursor() as cur:
#         cur.execute(
#             "INSERT INTO messages (user_message, llm_response) VALUES (%s, %s)",
#             (msg.user_message, msg.llm_response)
#         )
#     return {"status": "ok"}
