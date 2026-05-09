"""Microsoft Fabric SQL client for the POS Service.

The POS Service is the first service in the Hightower stack to query Fabric SQL
directly. Sentry-WMS receives Fabric data via its inbound mapping framework but
does not call out to Fabric, so there is no client to lift -- this module is
written fresh against the SQLAlchemy + pyodbc + Microsoft ODBC Driver 18 stack
recommended for Fabric SQL endpoints. See
/Users/michaelhightower/Desktop/fabric-integration-notes.md for the
investigation that informed this shape.

v1 surface:
    fetch_price_catalog() -> list[(sku, unit_price_cents)]
        Pulled every 4 hours by pos_service.services.fabric_price_sync into
        the local pos_prices SQLite cache. The cashier path
        (pos_service.routes.items.lookup) reads only the cache, so a Fabric
        outage never blocks a sale -- it just lets prices drift.

write_sales_order() lands in Phase C alongside the fabric_outbox table.

Mock mode: an empty FABRIC_CONNECTION_STRING leaves the engine unconstructed
and turns fetch_price_catalog() into a no-op returning []. This is the same
opt-out posture the Sentry and Windcave clients use so dev machines without
Azure credentials don't error on startup or churn the price cache.
"""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from pos_service.config import Settings

log = logging.getLogger(__name__)

# TODO(integration): confirm the active price catalog table and column names
# with the Fabric team before this query points at the real environment. The
# caller expects rows shaped (sku: str, unit_price_cents: int).
PRICE_CATALOG_QUERY = """
    SELECT sku, unit_price_cents
    FROM gl.dbo.items
    WHERE is_active = 1
"""


class FabricClientError(Exception):
    """Raised when a Fabric SQL call fails after the engine is constructed."""


class FabricClient:
    def __init__(self, connection_string: str, query_timeout_s: int = 30) -> None:
        self._connection_string = connection_string
        self._query_timeout_s = query_timeout_s
        self._engine: Engine | None = None
        if connection_string:
            self._engine = create_engine(
                connection_string,
                pool_size=4,
                pool_pre_ping=True,
                pool_recycle=600,
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> "FabricClient":
        return cls(
            connection_string=settings.fabric_connection_string,
            query_timeout_s=settings.fabric_query_timeout_s,
        )

    @property
    def is_mock(self) -> bool:
        return self._engine is None

    def fetch_price_catalog(self) -> list[tuple[str, int]]:
        if self._engine is None:
            return []
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(PRICE_CATALOG_QUERY))
                return [(str(row[0]), int(row[1])) for row in result]
        except Exception as exc:
            raise FabricClientError(
                f"price catalog fetch failed: {exc}"
            ) from exc

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
