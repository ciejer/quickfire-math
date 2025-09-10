"""Database engine and session helpers."""

from contextlib import contextmanager
from sqlmodel import SQLModel, Session, create_engine
import os

# Location of the SQLite DB. You can override with APP_DB_PATH env var.
DB_PATH = os.getenv("APP_DB_PATH", "/data/koiahi.sqlite")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db() -> None:
    """Initialise the database schema if it does not exist."""
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session():
    """Provide a transactional context for database operations."""
    with Session(engine) as session:
        yield session