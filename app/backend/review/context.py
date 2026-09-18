"""Process-wide review store (app identity, ADR-0019). Lakebase when
configured, in-memory otherwise so local dev and tests need no Postgres."""

from __future__ import annotations

import threading

from ..config import APP_SERVICE_PRINCIPAL_ID, lakebase_configured
from .store import InMemoryReviewStore, ReviewStore

_lock = threading.Lock()
_store = None


def get_review_store():
    global _store
    with _lock:
        if _store is None:
            if lakebase_configured():
                from ..deps import _app_client
                from .lakebase import connect_main
                from .schema import ensure_schema
                conn = connect_main(_app_client())
                ensure_schema(conn, APP_SERVICE_PRINCIPAL_ID)
                _store = ReviewStore(conn)
            else:
                _store = InMemoryReviewStore()
        return _store


def set_review_store(store) -> None:
    global _store
    with _lock:
        _store = store


def reset_review_store() -> None:
    set_review_store(None)
