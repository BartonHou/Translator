from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.settings import settings
from domain.models import Base

# Engine/session factory are created lazily so that merely importing this module
# (e.g. in tests or tooling) does not require a DB driver or a live database.
_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _session_factory


def SessionLocal():
    """Return a new Session. Kept as a callable for backward compatibility with
    call sites that did ``SessionLocal()`` against the old sessionmaker."""
    return get_session_factory()()


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
