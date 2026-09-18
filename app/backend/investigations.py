"""Investigation store: the id-to-Genie-conversation mapping (ADR-0011).

Persisted in Lakebase's review.investigation when configured so an app
restart no longer forgets which conversation a tab belongs to; in-memory
otherwise (local dev, tests)."""

from __future__ import annotations

import uuid

from .review.context import get_review_store
from .review.store import MISSING


class InvestigationNotFoundError(KeyError):
    pass


class InvestigationStore:
    def create(self) -> str:
        investigation_id = str(uuid.uuid4())
        get_review_store().create_investigation(investigation_id)
        return investigation_id

    def get_conversation_id(self, investigation_id: str) -> str | None:
        value = get_review_store().get_conversation(investigation_id)
        if value is MISSING:
            raise InvestigationNotFoundError(investigation_id)
        return value

    def set_conversation_id(self, investigation_id: str, conversation_id: str | None) -> None:
        get_review_store().set_conversation(investigation_id, conversation_id)


store = InvestigationStore()
