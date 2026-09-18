import pytest

from backend.investigations import InvestigationNotFoundError, InvestigationStore
from backend.review.context import set_review_store
from backend.review.store import InMemoryReviewStore


def test_investigation_store_delegates_to_review_store():
    review = InMemoryReviewStore()
    set_review_store(review)
    store = InvestigationStore()
    inv = store.create()
    assert store.get_conversation_id(inv) is None
    store.set_conversation_id(inv, "conv-1")
    assert review.get_conversation(inv) == "conv-1"
    with pytest.raises(InvestigationNotFoundError):
        store.get_conversation_id("nope")
