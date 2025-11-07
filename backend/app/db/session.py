from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Create (or return) the process-wide engine."""
    global _ENGINE  # noqa: PLW0603
    if _ENGINE is None:
        settings = get_settings()
        _ENGINE = create_engine(
            settings.database_url,
            echo=settings.database_echo,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            pool_recycle=settings.database_pool_recycle,
            future=True,
            pool_pre_ping=True,
        )
    return _ENGINE


def get_session_factory() -> sessionmaker[Session]:
    """Return the configured session factory."""
    global _SESSION_FACTORY  # noqa: PLW0603
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
    return _SESSION_FACTORY


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope for DB operations."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
