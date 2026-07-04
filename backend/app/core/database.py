"""SQLAlchemy engine and session management.

All persistence flows through the ORM's parameterized query compiler —
raw string SQL is never interpolated anywhere in this codebase, which
natively neutralizes SQL injection (OWASP A03).

Connection pooling is configured entirely from environment variables so
capacity can be tuned per deployment without code changes. When
``DATABASE_URL`` points at SQLite (used for local smoke-testing and the
pytest suite — never in production), QueuePool-only kwargs are dropped in
favor of ``check_same_thread=False`` and, for an in-memory URL, a
``StaticPool`` so every connection shares the same in-process database.
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

_connect_args: dict[str, Any] = {}
_engine_kwargs: dict[str, Any] = {"future": True}

if _is_sqlite:
    _connect_args["check_same_thread"] = False
    if ":memory:" in settings.database_url:
        from sqlalchemy.pool import StaticPool

        _engine_kwargs["poolclass"] = StaticPool
else:
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,  # transparently drop dead connections
    )

engine = create_engine(settings.database_url, connect_args=_connect_args, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
