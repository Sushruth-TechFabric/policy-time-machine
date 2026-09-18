"""Model access through Databricks Model Serving (pay-per-token Claude).

The provider is Databricks, chosen for ecosystem fit over calling the
Anthropic API directly (design spec §8). Every model turn returns one JSON
object, so no tool-calling API is needed and any text endpoint works.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole


class ModelOutputError(RuntimeError):
    """The model's reply did not contain a single JSON object."""


class ModelClient(Protocol):
    def complete(self, system: str, user: str, *, max_tokens: int = 800) -> str: ...


class FoundationModelClient:
    def __init__(self, client: WorkspaceClient, endpoint_name: str) -> None:
        self._client = client
        self.endpoint_name = endpoint_name

    def complete(self, system: str, user: str, *, max_tokens: int = 800) -> str:
        response = self._client.serving_endpoints.query(
            name=self.endpoint_name,
            messages=[
                ChatMessage(role=ChatMessageRole.SYSTEM, content=system),
                ChatMessage(role=ChatMessageRole.USER, content=user),
            ],
            max_tokens=max_tokens,
            temperature=0.0,
        )
        return _text_of(response.choices[0].message.content)


def _text_of(content: str | list | None) -> str:
    # Reasoning models return a list of blocks; the reply is the text blocks,
    # and the reasoning block is never parsed for the JSON object.
    if isinstance(content, list):
        return "".join(block.get("text") or "" for block in content if block.get("type") == "text")
    return content or ""


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_object(text: str) -> dict:
    candidate = text or ""
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1)
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ModelOutputError(f"no JSON object in model output: {text[:120]!r}")
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ModelOutputError(str(exc)) from exc
    if not isinstance(parsed, dict):
        raise ModelOutputError("model output is not a JSON object")
    return parsed
