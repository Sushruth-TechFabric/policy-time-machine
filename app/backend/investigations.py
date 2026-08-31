"""In-memory investigation store.

An investigation is just the id-to-Genie-conversation mapping (ADR-0011:
one Genie conversation per investigation, started lazily on the first
message). No persistence is needed — MVP has no saved investigations
(06-ux-specification.md §6) and the app is a single-process demo.
"""

from __future__ import annotations

import uuid


class InvestigationNotFoundError(KeyError):
    pass


class InvestigationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, str | None] = {}

    def create(self) -> str:
        investigation_id = str(uuid.uuid4())
        self._conversations[investigation_id] = None
        return investigation_id

    def get_conversation_id(self, investigation_id: str) -> str | None:
        if investigation_id not in self._conversations:
            raise InvestigationNotFoundError(investigation_id)
        return self._conversations[investigation_id]

    def set_conversation_id(self, investigation_id: str, conversation_id: str | None) -> None:
        self._conversations[investigation_id] = conversation_id


#: Process-wide singleton — fine for a single-instance demo app.
store = InvestigationStore()
