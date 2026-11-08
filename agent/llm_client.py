"""Společné rozhraní a adaptér pro lokální Ollama API."""

import json
import time
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agent.models import (
    ChatMessage,
    LLMRequest,
    LLMResponse,
    ToolCall,
    ToolDefinition,
)
from agent.retry import (
    get_retry_delay,
    is_retryable_http_status,
    validate_http_settings,
)
from config import MODEL_NAME, OLLAMA_URL


class LLMError(Exception):
    """Chyba při komunikaci s jazykovým modelem nebo při parsování odpovědi."""


class LLMClient(Protocol):
    """Rozhraní společné pro všechny poskytovatele jazykových modelů."""

    def chat(self, request: LLMRequest) -> LLMResponse:
        """Odešle normalizovaný požadavek a vrátí normalizovanou odpověď."""
        ...


def _tool_definition_to_ollama(tool: ToolDefinition) -> dict:
    """Převede interní popis nástroje na formát Ollama."""

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _message_to_ollama(message: ChatMessage) -> dict:
    """Převede interní zprávu na formát Ollama Chat API."""

    result: dict = {"role": message.role}

    if message.content is not None:
        result["content"] = message.content

    if message.name:
        result["tool_name"] = message.name

    if message.tool_calls:
        result["tool_calls"] = [
            {
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                }
            }
            for call in message.tool_calls
        ]

    return result


class OllamaClient:
    """Volitelný klient pro lokální Ollama API."""

    def __init__(
        self,
        model: str = MODEL_NAME,
        url: str = OLLAMA_URL,
        timeout: float = 120,
        max_retries: int = 2,
    ) -> None:
        validate_http_settings(timeout, max_retries)

        self.model = model
        self.url = url
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, request: LLMRequest) -> LLMResponse:
        """Odešle požadavek do Ollama a normalizuje její odpověď."""

        payload = {
            "model": self.model,
            "messages": [_message_to_ollama(item) for item in request.messages],
            "stream": False,
        }
        if request.tools:
            payload["tools"] = [
                _tool_definition_to_ollama(tool) for tool in request.tools
            ]

        response_data = self._post_json(payload)
        message = response_data.get("message")
        if not isinstance(message, dict):
            raise LLMError("Ollama vrátila neplatnou odpověď bez objektu message.")

        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise LLMError("Ollama vrátila neplatný obsah zprávy.")

        raw_tool_calls = message.get("tool_calls", [])
        if not isinstance(raw_tool_calls, list):
            raise LLMError("Ollama vrátila neplatný seznam tool_calls.")

        tool_calls: list[ToolCall] = []
        for index, raw_call in enumerate(raw_tool_calls):
            try:
                function = raw_call["function"]
                name = function["name"]
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    raise ValueError
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise LLMError("Ollama vrátila neplatné volání nástroje.") from exc

            # Některé verze Ollama neposílají ID volání nástroje.
            call_id = raw_call.get("id") or f"ollama-call-{index + 1}"
            tool_calls.append(ToolCall(id=str(call_id), name=name, arguments=arguments))

        return LLMResponse(content=content, tool_calls=tool_calls)

    def _post_json(self, payload: dict) -> dict:
        """Provede HTTP požadavek s opakováním dočasných chyb."""

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        for attempt in range(self.max_retries + 1):
            http_request = Request(
                self.url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(http_request, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise LLMError("Ollama vrátila odpověď v neplatném formátu.")
                return result
            except HTTPError as exc:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                exc.close()
                if (
                    not is_retryable_http_status(exc.code)
                    or attempt >= self.max_retries
                ):
                    raise LLMError(f"Ollama HTTP chyba: {exc.code}") from exc

                time.sleep(get_retry_delay(attempt, retry_after))

            except OSError as exc:
                if attempt >= self.max_retries:
                    raise LLMError(
                        "Ollama není dostupná nebo vypršel časový limit."
                    ) from exc
                time.sleep(get_retry_delay(attempt))

            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                # Chybná data nejsou dočasná síťová chyba; neopakujeme je.
                raise LLMError("Ollama vrátila neplatná data.") from exc

        raise LLMError("Počet pokusů o komunikaci s Ollama byl vyčerpán.")
