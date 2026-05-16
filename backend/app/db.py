from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations() -> None:
    """Keep local SQLite databases usable before Alembic is introduced."""
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    job_columns = {column["name"] for column in inspector.get_columns("jobs")}
    statements: list[str] = []
    if "progress_percent" not in job_columns:
        statements.append("ALTER TABLE jobs ADD COLUMN progress_percent INTEGER DEFAULT 0")
    if "progress_message" not in job_columns:
        statements.append("ALTER TABLE jobs ADD COLUMN progress_message TEXT")
    if "subtitles_enabled" not in job_columns:
        statements.append("ALTER TABLE jobs ADD COLUMN subtitles_enabled BOOLEAN DEFAULT 1")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
