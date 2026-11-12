import logging
import math

from psycopg import Connection
from psycopg.rows import TupleRow
from psycopg_pool import ConnectionPool

from app.config import Settings

log = logging.getLogger("postgres")

def create_postgres_pool(settings: Settings) -> ConnectionPool[Connection[TupleRow]]:
    timeout = settings.postgres_connect_timeout_s
    pool: ConnectionPool[Connection[TupleRow]] = ConnectionPool(
        conninfo=settings.postgres_dsn.get_secret_value(),
        min_size=settings.postgres_pool_min_size,
        max_size=settings.postgres_pool_max_size,
        timeout=timeout,
        kwargs={"connect_timeout": max(1, math.ceil(timeout))},
        name="worker-postgres",
        open=False,
    )
    try:
        pool.open(wait=True, timeout=timeout)
    except Exception:
        pool.close()
        raise
    log.info(
        "postgres pool opened",
        extra={"min_size": pool.min_size, "max_size": pool.max_size},
    )
    return pool
