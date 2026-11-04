"""Řídicí logika AI agenta a jeho rozhodovací cyklus."""

import json
from dataclasses import asdict, dataclass
from typing import Literal

from agent.llm_client import LLMClient, LLMError
from agent.memory import AgentMemory
from agent.models import ChatMessage, LLMRequest, ToolCall
from agent.tools import TOOL_DEFINITIONS, execute_tool
from config import MAX_AGENT_STEPS, MAX_TOOL_CALLS, SYSTEM_PROMPT


AgentStatus = Literal["completed", "error", "limit_reached"]


@dataclass
class AgentResult:
    """Strukturovaný výsledek práce agenta."""

    status: AgentStatus
    answer: str
    tool_calls: int
    error: str | None = None


def to_json(result: AgentResult) -> str:
    """Převede výsledek agenta na JSON."""

    return json.dumps(asdict(result), ensure_ascii=False, indent=2)


class AIAgent:
    """Agent s provider-neutrálním rozhraním, nástroji a SQLite pamětí."""

    def __init__(
        self,
        llm_client: LLMClient,
        memory: AgentMemory | None = None,
    ) -> None:
        if llm_client is None:
            raise ValueError("AIAgent vyžaduje explicitně předaného LLM klienta.")
        self.llm = llm_client
        self.memory = memory if memory is not None else AgentMemory()

    def run(self, user_input: str) -> AgentResult:
        """Zpracuje uživatelský požadavek prostřednictvím Agent Loop."""

        if not isinstance(user_input, str) or not user_input.strip():
            return AgentResult(
                status="error",
                answer="Požadavek nesmí být prázdný.",
                tool_calls=0,
                error="Uživatelský vstup je prázdný nebo neplatný.",
            )

        clean_input = user_input.strip()
        messages = self._build_messages(clean_input)
        tool_calls_count = 0

        for _ in range(MAX_AGENT_STEPS):
            try:
                response = self.llm.chat(
                    LLMRequest(messages=messages, tools=TOOL_DEFINITIONS)
                )
            except LLMError as exc:
                return self._finalize_result(
                    clean_input,
                    AgentResult(
                        status="error",
                        answer="Nepodařilo se komunikovat s jazykovým modelem.",
                        tool_calls=tool_calls_count,
                        error=str(exc),
                    ),
                )

            if response.tool_calls:
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )

                remaining_calls = MAX_TOOL_CALLS - tool_calls_count
                if remaining_calls <= 0:
                    return self._limit_result(clean_input, tool_calls_count)

                calls_to_execute = response.tool_calls[:remaining_calls]
                for tool_call in calls_to_execute:
                    tool_result = self._execute_tool_call(tool_call)
                    messages.append(
                        ChatMessage(
                            role="tool",
                            content=tool_result,
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                        )
                    )
                    tool_calls_count += 1

                # Nepovolíme vykonání dalších volání nad nastavený limit.
                if len(calls_to_execute) < len(response.tool_calls):
                    return self._limit_result(clean_input, tool_calls_count)
                continue

            answer = response.content.strip() if isinstance(response.content, str) else ""
            if not answer:
                return self._finalize_result(
                    clean_input,
                    AgentResult(
                        status="error",
                        answer="Jazykový model vrátil prázdnou odpověď.",
                        tool_calls=tool_calls_count,
                        error="Finální odpověď modelu neobsahuje žádný text.",
                    ),
                )

            return self._finalize_result(
                clean_input,
                AgentResult(
                    status="completed",
                    answer=answer,
                    tool_calls=tool_calls_count,
                ),
            )

        return self._limit_result(clean_input, tool_calls_count, steps=True)

    @staticmethod
    def _execute_tool_call(tool_call: ToolCall) -> str:
        """Bezpečně předá normalizované volání do registru nástrojů."""

        if not isinstance(tool_call.name, str) or not isinstance(
            tool_call.arguments, dict
        ):
            return json.dumps(
                {"error": "Neplatný požadavek na nástroj."}, ensure_ascii=False
            )
        return execute_tool(tool_call.name, tool_call.arguments)

    def _build_messages(self, user_input: str) -> list[ChatMessage]:
        """Sestaví kontext z instrukcí, uložené historie a aktuálního vstupu."""

        history = [
            ChatMessage(role=item["role"], content=item["content"])
            for item in self.memory.get_history()
        ]
        return [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            *history,
            ChatMessage(role="user", content=user_input),
        ]

    def _limit_result(
        self,
        user_input: str,
        tool_calls_count: int,
        *,
        steps: bool = False,
    ) -> AgentResult:
        reason = (
            "Byl dosažen maximální počet rozhodovacích cyklů."
            if steps
            else "Byl dosažen maximální počet volání nástrojů."
        )
        answer = (
            "Agent nedokončil úkol v povoleném počtu kroků."
            if steps
            else "Agent nedokončil úkol, protože dosáhl limitu volání nástrojů."
        )
        return self._finalize_result(
            user_input,
            AgentResult(
                status="limit_reached",
                answer=answer,
                tool_calls=tool_calls_count,
                error=reason,
            ),
        )

    def _finalize_result(self, user_input: str, result: AgentResult) -> AgentResult:
        """Uloží uživatelský vstup a finální odpověď do dlouhodobé paměti."""

        self.memory.save_message("user", user_input)
        self.memory.save_message("assistant", result.answer)
        return result
