from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import Base

_ENGINE: Optional[Engine] = None
_SESSION_FACTORY: Optional[sessionmaker[Session]] = None


def _build_engine() -> Engine:
    settings = get_settings()
    database_url = settings.database_url
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args, future=True)


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = _build_engine()
    return _ENGINE


def get_session_factory() -> sessionmaker[Session]:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False, autocommit=False)
    return _SESSION_FACTORY


def get_session() -> Session:
    return get_session_factory()()


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
