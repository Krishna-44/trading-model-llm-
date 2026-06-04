"""Database engine + session. SQLite by default; set AIFOS_DATABASE_URL to a
Postgres/TimescaleDB DSN for the durable multi-service deployment."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from ..config import settings


class Base(DeclarativeBase):
    pass


_connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    from . import models  # noqa: F401 - register tables on Base.metadata
    Base.metadata.create_all(engine)
    if settings.is_sqlite:
        _add_missing_columns()  # lightweight migration: add new columns to existing tables


def _add_missing_columns() -> None:
    """SQLite create_all doesn't add columns to existing tables — bridge that for
    new scalar columns (e.g. trades.strategy) so upgrades don't need a manual migrate."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                default = ""
                arg = getattr(col.default, "arg", None)
                if isinstance(arg, str):
                    default = f" DEFAULT '{arg}'"
                elif isinstance(arg, (int, float)) and not isinstance(arg, bool):
                    default = f" DEFAULT {arg}"
                try:
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN "
                                      f"{col.name} {col.type.compile(engine.dialect)}{default}"))
                except Exception:  # noqa: BLE001 - already exists / unsupported default
                    pass


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
