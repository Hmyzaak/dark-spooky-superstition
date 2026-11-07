"""Adaptér pro OpenAI-kompatibilní Groq Chat Completions API."""

import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agent.llm_client import LLMError
from agent.models import ChatMessage, LLMRequest, LLMResponse, ToolCall, ToolDefinition
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_URL


class GroqClient:
    """Klient Groq API implementovaný standardní knihovnou Pythonu."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = GROQ_MODEL,
        url: str = GROQ_URL,
        timeout: int = 60,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key if api_key is not None else GROQ_API_KEY
        if not self.api_key:
            raise ValueError(
                "Chybí GROQ_API_KEY. Nastav API klíč v proměnné prostředí."
            )
        if timeout <= 0 or max_retries < 0:
            raise ValueError("Neplatné nastavení timeout nebo max_retries.")

        self.model = model
        self.url = url
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, request: LLMRequest) -> LLMResponse:
        """Odešle požadavek do Groq a normalizuje odpověď."""

        payload = {
            "model": self.model,
            "messages": [self._message_to_groq(message) for message in request.messages],
        }
        if request.tools:
            payload["tools"] = [self._tool_to_groq(tool) for tool in request.tools]
            payload["tool_choice"] = "auto"

        data = self._post_json(payload)
        try:
            raw_message = data["choices"][0]["message"]
            content = raw_message.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError

            tool_calls: list[ToolCall] = []
            for raw_call in raw_message.get("tool_calls", []):
                function = raw_call["function"]
                arguments = function.get("arguments", "{}")
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict):
                    raise ValueError
                tool_calls.append(
                    ToolCall(
                        id=str(raw_call["id"]),
                        name=function["name"],
                        arguments=arguments,
                    )
                )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LLMError("Groq vrátila odpověď v neplatném formátu.") from exc

        return LLMResponse(content=content, tool_calls=tool_calls)

    @staticmethod
    def _message_to_groq(message: ChatMessage) -> dict:
        result: dict = {"role": message.role}
        if message.content is not None:
            result["content"] = message.content
        if message.name:
            result["name"] = message.name
        if message.tool_call_id:
            result["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        return result

    @staticmethod
    def _tool_to_groq(tool: ToolDefinition) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _post_json(self, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        for attempt in range(self.max_retries + 1):
            http_request = Request(
                self.url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": "dark-spooky-superstition/1.0",
                },
                method="POST",
            )
            try:
                with urlopen(http_request, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise LLMError("Groq vrátila odpověď v neplatném formátu.")
                return result

            except HTTPError as exc:
                # Groq vrací v těle odpovědi podrobnosti o chybě.
                error_body = exc.read().decode("utf-8", errors="replace")

                try:
                    error_data = json.loads(error_body)
                    error_message = error_data.get("error", {}).get(
                        "message",
                        error_body,
                    )
                    error_code = error_data.get("error", {}).get("code")
                except (json.JSONDecodeError, AttributeError):
                    error_message = error_body or "Bez podrobností."
                    error_code = None

                details = f"Groq HTTP chyba {exc.code}: {error_message}"

                if error_code:
                    details += f" (kód: {error_code})"

                # Chyby 5xx mohou být dočasné.
                if exc.code < 500 or attempt >= self.max_retries:
                    raise LLMError(details) from exc

            except OSError as exc:
                if attempt >= self.max_retries:
                    raise LLMError(
                        "Groq není dostupná nebo vypršel časový limit."
                    ) from exc
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise LLMError("Groq vrátila neplatná data.") from exc

            time.sleep(2 ** attempt)

        raise LLMError("Počet pokusů o komunikaci s Groq byl vyčerpán.")
