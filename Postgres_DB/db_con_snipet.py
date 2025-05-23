from sqlalchemy.engine import URL
from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

db_url = URL.create(
    drivername = "postgresql+psycopg",
    username = "postgres",
    password = "password",
    host = "localhost",
    port = 5555,
    database = "chat_hist_db"
)

engine = create_engine(db_url)

try:
    # Try connecting to the DB and list tables
    inspector = inspect(engine)

    tables = inspector.get_table_names()
    print("Connected successfully.")
    print("Tables in the database:", tables)

except OperationalError as e:
    print("Connection failed:", e)