"""Deterministický simulátor jazykového modelu pro testování agenta."""

from collections import deque
from collections.abc import Iterable
from typing import Any

from agent.llm_client import LLMError


class MockLLMClient:
    """Vrací předem připravené odpovědi ve formátu Ollama Chat API.

    Odpovědi se předávají v pořadí, v jakém je má agent obdržet.
    Třída neprovádí žádné síťové požadavky.
    """

    def __init__(self, responses: Iterable[dict[str, Any]]) -> None:
        self._responses = deque(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Zaznamená požadavek a vrátí další připravenou odpověď."""

        self.calls.append(
            {
                "messages": [message.copy() for message in messages],
                "tools": tools,
            }
        )

        if not self._responses:
            raise LLMError("MockLLMClient nemá připravenou další odpověď.")

        return self._responses.popleft()
