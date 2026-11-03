# agent/agent.py
"""Řídicí logika AI agenta a jeho rozhodovací cyklus."""

import json
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from agent.llm_client import LLMError, OllamaClient
from agent.memory import AgentMemory
from agent.tools import TOOL_SCHEMAS, execute_tool
from config import MAX_AGENT_STEPS, SYSTEM_PROMPT


class LLMClient(Protocol):
    """Rozhraní klienta, který komunikuje s jazykovým modelem."""

    def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Odešle konverzaci modelu a vrátí jeho odpověď."""
        ...


AgentStatus = Literal["completed", "error", "limit_reached"]


@dataclass
class AgentResult:
    """Strukturovaný výsledek práce agenta."""

    status: AgentStatus
    answer: str
    tool_calls: int
    error: str | None = None


@dataclass
class ToolCallsRequest:
    """Požadavek jazykového modelu na provedení nástrojů."""

    assistant_message: dict[str, Any]
    tool_calls: list[Any]


def to_json(result: AgentResult) -> str:
    """Převede výsledek agenta na JSON."""

    return json.dumps(
        asdict(result),
        ensure_ascii=False,
        indent=2,
    )


def _process_llm_response(
    response: Any,
    tool_calls_count: int,
) -> AgentResult | ToolCallsRequest:
    """Vyhodnotí odpověď modelu a určí další postup agenta."""

    if not isinstance(response, dict):
        return AgentResult(
            status="error",
            answer="Jazykový model vrátil neplatnou odpověď.",
            tool_calls=tool_calls_count,
            error="Odpověď modelu musí být slovník.",
        )

    assistant_message = response.get("message")

    if not isinstance(assistant_message, dict):
        return AgentResult(
            status="error",
            answer="Jazykový model vrátil neplatnou odpověď.",
            tool_calls=tool_calls_count,
            error="Odpověď neobsahuje platný objekt message.",
        )

    requested_tools = assistant_message.get("tool_calls", [])

    if not isinstance(requested_tools, list):
        return AgentResult(
            status="error",
            answer="Jazykový model vrátil neplatný seznam požadavků na nástroje.",
            tool_calls=tool_calls_count,
            error="Pole tool_calls musí být seznam.",
        )

    # Model požaduje provedení nástrojů.
    if requested_tools:
        return ToolCallsRequest(
            assistant_message=assistant_message,
            tool_calls=requested_tools,
        )

    # Model již nepožaduje žádné nástroje.
    content = assistant_message.get("content", "")
    answer = content.strip() if isinstance(content, str) else ""

    if not answer:
        return AgentResult(
            status="error",
            answer="Jazykový model vrátil prázdnou odpověď.",
            tool_calls=tool_calls_count,
            error="Finální odpověď modelu neobsahuje žádný text.",
        )

    return AgentResult(
        status="completed",
        answer=answer,
        tool_calls=tool_calls_count,
    )


def _handle_tool_calls(
        tool_calls: list[Any],
        messages: list[dict[str, Any]],
) -> int:
    """Provede požadované nástroje a přidá výsledky do kontextu."""

    executed_count = 0

    for tool_call in tool_calls:
        name: str | None = None
        arguments: Any = None

        if isinstance(tool_call, dict):
            function = tool_call.get("function", {})

            if isinstance(function, dict):
                name = function.get("name")
                arguments = function.get("arguments", {})

            # Argumenty mohou být slovník nebo JSON text.
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = None

            tool_result = execute_tool(name, arguments)

        else:
            tool_result = json.dumps(
                {"error": "Neplatný požadavek na nástroj."},
                ensure_ascii=False,
            )

        messages.append(
            {
                "role": "tool",
                "tool_name": name,
                "content": tool_result,
            }
        )

        # Počítáme také neplatné požadavky, které agent obdržel.
        executed_count += 1

    return executed_count


class AIAgent:
    """Základní AI agent s podporou nástrojů a paměti."""

    def __init__(
            self,
            llm_client: LLMClient | None = None,
            memory: AgentMemory | None = None,
    ) -> None:
        # Dependency Injection umožňuje předat vlastního klienta a paměť.
        self.llm = llm_client if llm_client is not None else OllamaClient()
        self.memory = memory if memory is not None else AgentMemory()

    def run(self, user_input: str) -> AgentResult:
        """Zpracuje požadavek uživatele prostřednictvím Agent Loop."""

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
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                )
            except LLMError as exc:
                result = AgentResult(
                    status="error",
                    answer="Nepodařilo se komunikovat s jazykovým modelem.",
                    tool_calls=tool_calls_count,
                    error=str(exc),
                )
                return self._finalize_result(clean_input, result)

            outcome = _process_llm_response(
                response=response,
                tool_calls_count=tool_calls_count,
            )

            # Finální odpověď nebo chyba znamená ukončení běhu.
            if isinstance(outcome, AgentResult):
                return self._finalize_result(clean_input, outcome)

            messages.append(outcome.assistant_message)

            # Seznam požadavků znamená, že agent má provést nástroje.
            tool_calls_count += _handle_tool_calls(
                outcome.tool_calls,
                messages,
            )

        result = AgentResult(
            status="limit_reached",
            answer="Agent nedokončil úkol v povoleném počtu kroků.",
            tool_calls=tool_calls_count,
            error="Byl dosažen maximální počet cyklů.",
        )
        return self._finalize_result(clean_input, result)

    def _build_messages(
            self,
            user_input: str,
    ) -> list[dict[str, Any]]:
        """Sestaví kontext předávaný jazykovému modelu."""

        return [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            *self.memory.get_history(),
            {
                "role": "user",
                "content": user_input,
            },
        ]

    def _finalize_result(
            self,
            user_input: str,
            result: AgentResult,
    ) -> AgentResult:
        """Uloží výsledek běhu agenta a vrátí jej."""

        self._save_conversation(user_input, result.answer)
        return result

    def _save_conversation(
            self,
            user_input: str,
            answer: str,
    ) -> None:
        """Uloží uživatelský požadavek a výslednou odpověď do paměti."""

        self.memory.save_message("user", user_input)
        self.memory.save_message("assistant", answer)
