"""
db.py — shared connection pool
==============================
Initialised once at FastAPI startup. All modules fetch/return
connections through get_conn() instead of opening a new socket
per query.
"""

from contextlib import contextmanager
import psycopg2
from psycopg2 import pool as pgpool

_pool: pgpool.SimpleConnectionPool | None = None


def init_pool(dsn: str, minconn: int = 1, maxconn: int = 10) -> None:
    global _pool
    _pool = pgpool.SimpleConnectionPool(minconn, maxconn, dsn)


def close_pool() -> None:
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


@contextmanager
def get_conn():
    """Yield a connection from the pool; commit on success, rollback on error."""
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_pool() first")
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
