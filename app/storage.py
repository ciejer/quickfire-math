from contextlib import contextmanager
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.engine import URL
import os
import pathlib

DB_PATH = os.getenv("APP_DB_PATH", "/data/quickfiremath.sqlite")
# Ensure directory exists
db_dir = os.path.dirname(DB_PATH) or "."
os.makedirs(db_dir, exist_ok=True)

# Build a safe SQLite URL for Windows and POSIX paths
db_url = URL.create(
    "sqlite",
    database=str(pathlib.Path(DB_PATH))
)
engine = create_engine(db_url, connect_args={"check_same_thread": False})


def init_db():
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session
