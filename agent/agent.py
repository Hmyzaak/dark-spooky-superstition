import json
from dataclasses import asdict, dataclass
from typing import Any

from agent.llm_client import LLMError, OllamaClient
from agent.memory import AgentMemory
from agent.tools import TOOL_SCHEMAS, execute_tool
from config import MAX_AGENT_STEPS, SYSTEM_PROMPT


@dataclass
class AgentResult:
    """Strukturovaný výsledek práce agenta."""

    status: str
    answer: str
    tool_calls: int
    error: str | None = None


class AIAgent:
    """Základní AI agent s podporou nástrojů a paměti."""

    def __init__(self) -> None:
        self.llm = OllamaClient()
        self.memory = AgentMemory()

    def run(self, user_input: str) -> AgentResult:
        """Zpracuje požadavek uživatele prostřednictvím Agent Loop."""

        if not isinstance(user_input, str) or not user_input.strip():
            return AgentResult(
                status="error",
                answer="",
                tool_calls=0,
                error="Požadavek nesmí být prázdný.",
            )

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            *self.memory.get_history(),
            {
                "role": "user",
                "content": user_input.strip(),
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

                self._save_conversation(user_input, result.answer)
                return result

            assistant_message = response["message"]
            requested_tools = assistant_message.get("tool_calls", [])

            # Uložíme kompletní odpověď modelu včetně požadavků na nástroje.
            messages.append(assistant_message)

            # Model již nechce použít žádný nástroj.
            if not requested_tools:
                answer = assistant_message.get("content", "").strip()

                if not answer:
                    answer = "Model vrátil prázdnou odpověď."

                result = AgentResult(
                    status="completed",
                    answer=answer,
                    tool_calls=tool_calls_count,
                )

                self._save_conversation(user_input, answer)
                return result

            # Vykonání požadovaných nástrojů.
            for tool_call in requested_tools:
                function = tool_call.get("function", {})
                name = function.get("name")
                arguments = function.get("arguments", {})

                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = None

                tool_result = execute_tool(name, arguments)
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
        """Uloží dokončenou konverzaci."""

        self.memory.save_message("user", user_input)
        self.memory.save_message("assistant", answer)

    def to_json(self, result: AgentResult) -> str:
        """Převede výsledek agenta na JSON."""

        return json.dumps(
            asdict(result),
            ensure_ascii=False,
            indent=2,
        )
