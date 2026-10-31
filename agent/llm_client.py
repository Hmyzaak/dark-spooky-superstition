import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import MODEL_NAME, OLLAMA_URL


class LLMError(Exception):
    """Chyba při komunikaci s jazykovým modelem."""


class OllamaClient:
    """Klient pro komunikaci s lokální Ollama API."""

    def __init__(
        self,
        model: str = MODEL_NAME,
        timeout: int = 120,
        max_retries: int = 2,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Odešle požadavek na Ollama API."""

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools

        request = Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(
                    request,
                    timeout=self.timeout,
                ) as response:
                    result = json.loads(
                        response.read().decode("utf-8")
                    )

                if not isinstance(result.get("message"), dict):
                    raise LLMError("Ollama vrátila neplatnou odpověď.")

                return result

            except HTTPError as exc:
                # Chyby HTTP 5xx mohou být dočasné.
                if exc.code < 500 or attempt >= self.max_retries:
                    raise LLMError(
                        f"Ollama HTTP chyba: {exc.code}"
                    ) from exc

            except (URLError, TimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise LLMError(
                        "Ollama není dostupná nebo vypršel časový limit."
                    ) from exc

            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise LLMError(
                    "Ollama vrátila neplatná data."
                ) from exc

            time.sleep(2 ** attempt)

        raise LLMError("Počet pokusů byl vyčerpán.")
