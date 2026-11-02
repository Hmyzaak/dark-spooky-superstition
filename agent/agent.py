"""Řídicí logika AI agenta a jeho rozhodovací cyklus."""

import json
from dataclasses import asdict, dataclass
from typing import Any, Protocol

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


@dataclass
class AgentResult:
    """Strukturovaný výsledek práce agenta."""

    status: str
    answer: str
    tool_calls: int
    error: str | None = None


class AIAgent:
    """Základní AI agent s podporou nástrojů a paměti."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        memory: AgentMemory | None = None,
    ) -> None:
        # Závislosti lze vložit zvenčí; výchozí chování aplikace zůstává stejné.
        self.llm = llm_client if llm_client is not None else OllamaClient()
        self.memory = memory if memory is not None else AgentMemory()

    def run(self, user_input: str) -> AgentResult:
        """Zpracuje požadavek uživatele prostřednictvím Agent Loop."""

        if not isinstance(user_input, str) or not user_input.strip():
            return AgentResult(
                status="error",
                answer="",
                tool_calls=0,
                error="Požadavek nesmí být prázdný.",
            )

        clean_input = user_input.strip()
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            *self.memory.get_history(),
            {
                "role": "user",
                "content": clean_input,
            },
        ]

        tool_calls_count = 0

        for step in range(MAX_AGENT_STEPS):

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

                self._save_conversation(clean_input, result.answer)
                return result

            assistant_message = response.get("message")
            if not isinstance(assistant_message, dict):
                result = AgentResult(
                    status="error",
                    answer="Jazykový model vrátil neplatnou odpověď.",
                    tool_calls=tool_calls_count,
                    error="Odpověď neobsahuje platný objekt message.",
                )
                self._save_conversation(clean_input, result.answer)
                return result

            # Uložíme kompletní odpověď modelu včetně požadavků na nástroje.
            messages.append(assistant_message)

            # Získá seznam požadovaných nástrojů.
            requested_tools = assistant_message.get("tool_calls", [])
            if not isinstance(requested_tools, list):
                result = AgentResult(
                    status="error",
                    answer="Jazykový model vrátil neplatný seznam požadavků na nástroje.",
                    tool_calls=tool_calls_count,
                    error="Pole tool_calls musí být seznam.",
                )
                self._save_conversation(clean_input, result.answer)
                return result

            # Model již nechce použít žádný nástroj. Považujeme jeho zprávu za finální odpověď.
            if not requested_tools:
                content = assistant_message.get("content", "")
                answer = content.strip() if isinstance(content, str) else ""
                if not answer:
                    answer = "Model vrátil prázdnou odpověď."

                result = AgentResult(
                    status="completed",
                    answer=answer,
                    tool_calls=tool_calls_count,
                )

                self._save_conversation(user_input, answer)
                return result

            # Vykonání požadovaných nástrojů a přidání jejich výsledků do kontextu.
            for tool_call in requested_tools:
                name: str | None = None

                if isinstance(tool_call, dict):
                    function = tool_call.get("function", {})
                    if isinstance(function, dict):
                        name = function.get("name")
                        arguments = function.get("arguments", {})
                    else:
                        arguments = None

                    # Některé klienty předávají argumenty jako JSON text,
                    # jiné (včetně běžné odpovědi Ollama) jako slovník.
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

                tool_calls_count += 1

                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": tool_result,
                    }
                )

        # Agent překročil povolený počet cyklů.
        result = AgentResult(
            status="limit_reached",
            answer="Agent nedokončil úkol v povoleném počtu kroků.",
            tool_calls=tool_calls_count,
            error="Byl dosažen maximální počet cyklů.",
        )

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

    def to_json(self, result: AgentResult) -> str:
        """Převede výsledek agenta na JSON."""

        return json.dumps(
            asdict(result),
            ensure_ascii=False,
            indent=2,
        )
