"""Deterministický simulátor normalizovaného LLM rozhraní pro testování."""

from collections import deque
from collections.abc import Iterable
from copy import deepcopy

from agent.llm_client import LLMError
from agent.models import LLMRequest, LLMResponse


class MockLLMClient:
    """Vrací předem připravené LLMResponse bez síťové komunikace."""

    def __init__(self, responses: Iterable[LLMResponse]) -> None:
        self._responses = deque(responses)
        self.calls: list[LLMRequest] = []

    def chat(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(deepcopy(request))
        if not self._responses:
            raise LLMError("MockLLMClient nemá připravenou další odpověď.")
        return deepcopy(self._responses.popleft())
