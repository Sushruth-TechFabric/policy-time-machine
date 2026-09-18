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
            _store = _build_store()
        return _store


def _build_store():
    """Lakebase when configured. If the first connection or the migration
    fails the app degrades to the in-memory twin rather than 500ing every
    review and investigation call — the investigation surface must keep
    working without the review record (see main.py's lifespan)."""
    if not lakebase_configured():
        return InMemoryReviewStore()
    from ..deps import _app_client
    from .lakebase import connect_main
    from .schema import ensure_schema
    try:
        conn = connect_main(_app_client())
        ensure_schema(conn, APP_SERVICE_PRINCIPAL_ID)
    except Exception as exc:  # noqa: BLE001
        print(f"[review] Lakebase unavailable, falling back to the in-memory review record: {exc}", flush=True)
        return InMemoryReviewStore()
    # Free Edition Lakebase scales to zero and drops idle connections; the
    # store re-dials through this factory rather than failing the request.
    return ReviewStore(conn, reconnect=lambda: connect_main(_app_client()))


def set_review_store(store) -> None:
    global _store
    with _lock:
        _store = store


def reset_review_store() -> None:
    set_review_store(None)
