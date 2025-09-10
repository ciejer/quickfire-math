from contextlib import contextmanager
from sqlmodel import SQLModel, Session, create_engine
import os

DB_PATH = os.getenv("APP_DB_PATH", "/data/quickfiremath.sqlite")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db():
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session
