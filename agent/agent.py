"""Řídicí logika AI agenta a jeho rozhodovací cyklus."""

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from typing import Literal

from agent.llm_client import LLMClient, LLMError
from agent.memory import AgentMemory
from agent.models import ChatMessage, LLMRequest, LLMResponse, ToolCall
from agent.tools import TOOL_DEFINITIONS, execute_tool
from config import MAX_AGENT_STEPS, MAX_TOOL_CALLS, SYSTEM_PROMPT


logger = logging.getLogger(__name__)

AgentStatus = Literal["completed", "error", "limit_reached"]

_MEMORY_INIT_WARNING = (
    "Paměť konverzace není dostupná. Agent pokračuje bez ukládání historie."
)
_MEMORY_READ_WARNING = (
    "Historii konverzace se nepodařilo načíst. Agent pokračoval bez předchozí historie."
)
_MEMORY_SAVE_WARNING = (
    "Odpověď byla vytvořena, ale nepodařilo se ji uložit do historie konverzace."
)
_LLM_ERROR_ANSWER = "Nepodařilo se získat odpověď od jazykového modelu."
_LLM_ERROR_DETAILS = "Komunikace s jazykovým modelem selhala."
_UNEXPECTED_LLM_ERROR_DETAILS = "Nastala neočekávaná interní chyba LLM klienta."
_TOOL_ERROR = "Nástroj selhal kvůli neočekávané interní chybě."


@dataclass
class AgentResult:
    """Strukturovaný výsledek práce agenta."""

    status: AgentStatus
    answer: str
    tool_calls: int
    error: str | None = None
    memory_warning: str | None = None


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
        self.memory = memory
        self._memory_initialization_warning: str | None = None

        if self.memory is None:
            try:
                self.memory = AgentMemory()
            except (sqlite3.Error, OSError):
                logger.debug("Inicializace SQLite paměti selhala.", exc_info=True)
                self._memory_initialization_warning = _MEMORY_INIT_WARNING

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
        messages, memory_warning = self._build_messages(clean_input)
        tool_calls_count = 0

        for _ in range(MAX_AGENT_STEPS):
            try:
                response = self.llm.chat(
                    LLMRequest(messages=messages, tools=TOOL_DEFINITIONS)
                )
                self._validate_llm_response(response)
            except LLMError as exc:
                # Podrobnosti zůstávají v logu; uživateli neposíláme surovou
                # odpověď poskytovatele, která může obsahovat interní údaje.
                logger.warning("Požadavek na jazykový model selhal: %s", exc)
                return self._finalize_result(
                    clean_input,
                    AgentResult(
                        status="error",
                        answer=_LLM_ERROR_ANSWER,
                        tool_calls=tool_calls_count,
                        error=_LLM_ERROR_DETAILS,
                    ),
                    memory_warning=memory_warning,
                )
            except Exception:
                # Poslední ochranná hranice pro chyby neznámého LLM klienta.
                logger.exception("Neočekávaná chyba LLM klienta.")
                return self._finalize_result(
                    clean_input,
                    AgentResult(
                        status="error",
                        answer=_LLM_ERROR_ANSWER,
                        tool_calls=tool_calls_count,
                        error=_UNEXPECTED_LLM_ERROR_DETAILS,
                    ),
                    memory_warning=memory_warning,
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
                    return self._limit_result(
                        clean_input, tool_calls_count, memory_warning=memory_warning
                    )

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
                    return self._limit_result(
                        clean_input, tool_calls_count, memory_warning=memory_warning
                    )
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
                    memory_warning=memory_warning,
                )

            return self._finalize_result(
                clean_input,
                AgentResult(
                    status="completed",
                    answer=answer,
                    tool_calls=tool_calls_count,
                ),
                memory_warning=memory_warning,
            )

        return self._limit_result(
            clean_input,
            tool_calls_count,
            steps=True,
            memory_warning=memory_warning,
        )

    @staticmethod
    def _validate_llm_response(response: LLMResponse) -> None:
        """Ověří základní tvar odpovědi podle interního kontraktu LLM."""

        if not isinstance(response, LLMResponse):
            raise LLMError("LLM klient vrátil neočekávaný typ odpovědi.")
        if response.content is not None and not isinstance(response.content, str):
            raise LLMError("LLM klient vrátil neplatný obsah zprávy.")
        if not isinstance(response.tool_calls, list):
            raise LLMError("LLM klient vrátil neplatný seznam volání nástrojů.")
        for tool_call in response.tool_calls:
            if not isinstance(tool_call, ToolCall):
                raise LLMError("LLM klient vrátil neplatné volání nástroje.")
            if (
                not isinstance(tool_call.id, str)
                or not tool_call.id
                or not isinstance(tool_call.name, str)
                or not tool_call.name
                or not isinstance(tool_call.arguments, dict)
            ):
                raise LLMError("LLM klient vrátil neplatné údaje volání nástroje.")

    @staticmethod
    def _execute_tool_call(tool_call: ToolCall) -> str:
        """Bezpečně předá normalizované volání do registru nástrojů."""

        if (
            not isinstance(tool_call.id, str)
            or not tool_call.id
            or not isinstance(tool_call.name, str)
            or not isinstance(tool_call.arguments, dict)
        ):
            return json.dumps(
                {"error": "Neplatný požadavek na nástroj."}, ensure_ascii=False
            )

        try:
            return execute_tool(tool_call.name, tool_call.arguments)
        except Exception:
            # Chrání Agent Loop i před chybou mimo běžné ošetření registru.
            logger.exception("Neočekávaná chyba při volání nástroje %s.", tool_call.name)
            return json.dumps({"error": _TOOL_ERROR}, ensure_ascii=False)

    def _build_messages(
        self, user_input: str
    ) -> tuple[list[ChatMessage], str | None]:
        """Sestaví kontext; při chybě paměti pokračuje bez uložené historie."""

        memory_warning = self._memory_initialization_warning
        history: list[ChatMessage] = []

        if self.memory is not None:
            try:
                history = [
                    ChatMessage(role=item["role"], content=item["content"])
                    for item in self.memory.get_history()
                ]
            except (sqlite3.Error, OSError):
                logger.debug("Načtení historie SQLite selhalo.", exc_info=True)
                memory_warning = _MEMORY_READ_WARNING

        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            *history,
            ChatMessage(role="user", content=user_input),
        ]
        return messages, memory_warning

    def _limit_result(
        self,
        user_input: str,
        tool_calls_count: int,
        *,
        steps: bool = False,
        memory_warning: str | None = None,
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
            memory_warning=memory_warning,
        )

    def _finalize_result(
        self,
        user_input: str,
        result: AgentResult,
        *,
        memory_warning: str | None = None,
    ) -> AgentResult:
        """Uloží výměnu do paměti; chyba ukládání neovlivní odpověď agenta."""

        if self.memory is not None:
            try:
                self.memory.save_exchange(user_input, result.answer)
            except (sqlite3.Error, OSError):
                logger.debug("Uložení historie SQLite selhalo.", exc_info=True)
                memory_warning = self._combine_warnings(
                    memory_warning, _MEMORY_SAVE_WARNING
                )

        result.memory_warning = memory_warning
        return result

    @staticmethod
    def _combine_warnings(first: str | None, second: str) -> str:
        """Spojí upozornění bez duplicitního prázdného řádku."""

        if not first:
            return second
        if second in first:
            return first
        return f"{first} {second}"
